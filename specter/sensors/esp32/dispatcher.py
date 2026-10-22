"""One USB serial reader, many record types.

The ESP32-S3 emits several kinds of record on the *same* CDC link:

    CSI_DATA,<id>,<mac>,<rssi>,...,"[<i,q>,...]"     CSI capture
    HELLO,<proto>,<board>,<chip>,<mac>,<fw>,<build>    supervisor identity
    STAT,<uptime>,<heap_free>,<heap_min>,<health>      supervisor telemetry
    HB,<seq>,<uptime>                                   supervisor heartbeat

A single reader therefore has to classify each line and hand it to the right
consumer, without one noisy stream being able to starve the other.

Design rules
------------
* **Independent parsing.** Each record type has its own parser and its own
  error accounting. A malformed CSI line must not make a supervisor heartbeat
  look bad, and vice versa.
* **Independent counters.** Every line is accounted for: parsed, malformed,
  unknown, dropped.
* **Bounded queues.** Each consumer gets a fixed-capacity queue that keeps the
  *newest* records and counts what it dropped. A consumer that stops reading
  can never make the reader block or grow memory without limit.
* **Transport agnostic.** The dispatcher consumes bytes, not a serial port, so
  it can be driven by the simulator, a file, or a real port.

The CSI field names below are the ones the upstream ``csi_recv_router``
example prints in its CSV header, in order.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Sequence

from .protocol import (SupervisorHeartbeat, SupervisorIdentity,
                        SupervisorStatus, parse_line)

#: Record type tags, as emitted by the firmware.
CSI_TAG = "CSI_DATA"

#: The device's own status line. It is not a CSI record, but a damaged line
#: often has one spliced into it, and the fragment is worth recovering.
STAT_TAG = "SPECTER_STAT"


def _split_records(text: str) -> List[str]:
    """Split a line at every record start it contains.

    A line that holds two records is a line whose newline was lost, and
    splitting it is what lets both records be recovered instead of one
    being thrown away with the other.
    """
    starts = [i for i in range(len(text)) if text.startswith(CSI_TAG + ",", i)]
    if not starts:
        return [text]
    out: List[str] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(text)
        out.append(text[start:end])
    return out


@dataclass
class ResilientResult:
    """What one line produced.

    ``records`` are the CSI records the line yielded - more than one when a
    lost newline joined two of them. ``malformed`` says a piece of the line
    could not be parsed, which means data was lost. ``spliced`` says the
    line held more than one record, which means a newline was lost but no
    data was. ``salvaged`` is a fragment of another record that was cut out
    of a damaged line, if there was one.
    """
    records: List["CsiRecord"] = field(default_factory=list)
    malformed: bool = False
    spliced: bool = False
    salvaged: Optional[str] = None

    @property
    def record(self) -> Optional["CsiRecord"]:
        """The first record, for callers that expect at most one."""
        return self.records[0] if self.records else None
SUPERVISOR_TAGS = ("HELLO", "STAT", "HB")

#: The CSV header the upstream example prints before its packets. Used to
#: label fields when the header is seen on the wire.
CSI_FIELD_NAMES = (
    "type", "id", "mac", "rssi", "rate", "sig_mode", "mcs", "bandwidth",
    "smoothing", "not_sounding", "aggregation", "stbc", "fec_coding", "sgi",
    "noise_floor", "ampdu_cnt", "channel", "secondary_channel",
    "local_timestamp", "ant", "sig_len", "rx_format", "len", "first_word",
    "data",
)


class BoundedQueue:
    """A fixed-capacity queue that keeps the newest items and counts drops."""

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._items: Deque = deque()
        self.dropped = 0

    def push(self, item) -> None:
        if len(self._items) >= self.capacity:
            self._items.popleft()
            self.dropped += 1
        self._items.append(item)

    def drain(self) -> List:
        out = list(self._items)
        self._items.clear()
        return out

    def peek(self) -> List:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)


@dataclass
class CsiRecord:
    """One CSI packet, with the upstream field names where they are known."""

    seq: int
    mac: str
    rssi: int
    rate: int
    noise_floor: int
    channel: int
    local_timestamp: int
    sig_len: int
    fields: Dict[str, object] = field(default_factory=dict)
    iq: List[int] = field(default_factory=list)
    received_at: float = 0.0
    #: The ESP-IDF header says of ``wifi_csi_info_t.first_word_invalid``:
    #: "first four bytes of the CSI data is invalid or not, true indicates
    #: the first four bytes is invalid due to hardware limitation". The
    #: bytes are still printed, so they must be *marked*, not silently
    #: dropped - dropping them would shift every subcarrier index.
    first_word_invalid: bool = False
    #: how many subcarriers the flag invalidates (4 bytes = 2 carriers)
    invalid_subcarriers: int = 0
    #: the received frame's PHY rate code. The CSI is measured on the
    #: preamble of a frame received at this rate, and the amplitude scale
    #: follows the rate, so this is a confound and not a detail.
    rate_code: int = 0
    sig_mode: int = 0

    @property
    def has_iq(self) -> bool:
        return bool(self.iq)


@dataclass
class DispatcherCounters:
    """Everything that happened on the link, per record type."""

    lines: int = 0
    csi_parsed: int = 0
    csi_malformed: int = 0
    csi_dropped: int = 0
    csi_sequence_gaps: int = 0
    csi_missing_packets: int = 0
    supervisor_parsed: int = 0
    supervisor_malformed: int = 0
    supervisor_dropped: int = 0
    unknown_lines: int = 0
    headers_seen: int = 0
    bytes: int = 0

    def as_dict(self) -> Dict:
        return dict(self.__dict__)


class CsiParser:
    """Parses ``CSI_DATA`` lines and tracks sequence continuity.

    The upstream packet is 24 comma-separated fields followed by a quoted IQ
    tail. Field names come from the upstream CSV header; the ones that are
    positionally fixed are named here so a consumer never has to guess.
    """

    def __init__(self):
        self.first_seq: Optional[int] = None
        self.last_seq: Optional[int] = None
        self.gaps = 0
        self.missing = 0
        self.field_names = list(CSI_FIELD_NAMES)

    def feed(self, line: str) -> Optional[CsiRecord]:
        text = line.strip()
        if not text.startswith(CSI_TAG + ","):
            return None
        head, _, tail = text.partition('"')
        parts = head.rstrip(",").split(",")
        if len(parts) < 24:
            raise ValueError(f"CSI packet has {len(parts)} fields, expected >= 24")
        try:
            seq = int(parts[1])
            mac = parts[2].strip()
            rssi = int(parts[3])
            rate = int(parts[4])
            noise_floor = int(parts[14])
            channel = int(parts[16])
            # The IDF declares `unsigned timestamp:32` in microseconds, but
            # the example prints it with %d, so a counter that has passed
            # 2^31 arrives as a NEGATIVE number. Masking to 32 bits
            # recovers the true counter - which still wraps every 71.6
            # minutes, and any analysis that differences it must account
            # for that.
            local_ts = int(parts[18]) & 0xFFFFFFFF
            sig_len = int(parts[20])
            # Index 21 is sig_mode printed a second time (the upstream
            # header calls it "rx_format"), index 22 is info->len - the
            # valid CSI length in BYTES - and index 23 is
            # first_word_invalid, a flag, not a value.
            sig_mode = int(parts[21]) if len(parts) > 21 else 0
            csi_len = int(parts[22]) if len(parts) > 22 else 0
            first_word_invalid = bool(int(parts[23])) if len(parts) > 23 else False
        except (ValueError, IndexError) as exc:
            raise ValueError(f"CSI field parse failed: {exc}") from exc

        iq: List[int] = []
        if tail:
            blob = tail[1:] if tail.startswith("[") else tail
            blob = blob.rsplit("]", 1)[0] if "]" in blob else blob
            for tok in blob.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                try:
                    iq.append(int(tok))
                except ValueError:
                    raise ValueError("IQ blob is not numeric") from None

        # The tail holds exactly ``info->len`` values: one per BYTE of the
        # CSI buffer. A mismatch means the line was cut or the format
        # changed, and the packet must not be used for a spectrum.
        if csi_len and len(iq) != csi_len:
            raise ValueError(
                f"CSI tail has {len(iq)} values but len says {csi_len}")

        if self.first_seq is None:
            self.first_seq = seq
        if self.last_seq is not None and seq != self.last_seq + 1:
            self.gaps += 1
            if seq > self.last_seq:
                self.missing += seq - self.last_seq - 1
        self.last_seq = seq

        fields: Dict[str, object] = {}
        for idx, name in enumerate(self.field_names):
            if idx >= len(parts):
                break
            fields[name] = parts[idx]

        return CsiRecord(seq=seq, mac=mac, rssi=rssi, rate=rate,
                         noise_floor=noise_floor, channel=channel,
                         local_timestamp=local_ts, sig_len=sig_len,
                         fields=fields, iq=iq, received_at=time.time(),
                         first_word_invalid=first_word_invalid,
                         invalid_subcarriers=2 if first_word_invalid else 0,
                         rate_code=rate, sig_mode=sig_mode)

    def feed_resilient(self, line: str) -> "ResilientResult":
        """Feed one line, tolerating a damaged one.

        The captured evidence contains lines that were cut in the middle
        and had another record spliced into the gap, and a line that had a
        second copy of its own text repeated inside it. When a line like
        that arrives, the right response is **not** to abandon the stream:
        the records after it are perfectly good, and the damaged one often
        contains records that can be recovered.

        The line is therefore split at every record start it contains and
        each piece is parsed on its own:

        * one piece that parses - an ordinary line;
        * several pieces that all parse - a lost newline joined two
          records, and **no data was lost**; both are recovered;
        * a piece that does not parse - real damage, and the piece is
          counted as malformed.

        A limitation worth stating plainly: a splice that lands exactly at
        the boundary between a record's metadata and its IQ tail cannot be
        detected by this format, because the wire format carries no
        checksum. Such a record would carry one frame's metadata and
        another's spectrum. Detecting it needs a checksummed format, which
        is a separate piece of work and not a change to make inside a
        hardening pass.
        """
        text = (line or "").strip()
        if not text.startswith(CSI_TAG + ","):
            return ResilientResult(records=[])

        pieces = _split_records(text)
        records: List["CsiRecord"] = []
        malformed = False
        for piece in pieces:
            try:
                records.append(self.feed(piece))
            except ValueError:
                malformed = True

        spliced = len(pieces) > 1
        salvaged = None
        if malformed:
            stat = text.find(STAT_TAG + ",", 1)
            if stat > 0:
                salvaged = text[stat:]
        return ResilientResult(records=records, malformed=malformed,
                               spliced=spliced, salvaged=salvaged)


class SerialDispatcher:
    """Routes interleaved records to independent, bounded consumers.

    Feed it bytes; it splits lines, classifies them, parses them with the
    right parser, and pushes the result into that consumer's bounded queue.
    """

    def __init__(self, csi_capacity: int = 512, supervisor_capacity: int = 64):
        self.counters = DispatcherCounters()
        self.csi = BoundedQueue(csi_capacity)
        self.supervisor = BoundedQueue(supervisor_capacity)
        self.csi_parser = CsiParser()
        self._buf = b""
        self._lock = threading.Lock()

    # -- feeding -----------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Consume a chunk of bytes from the link."""
        if not data:
            return
        with self._lock:
            self.counters.bytes += len(data)
            self._buf += data
            # a CSI packet's IQ tail is quoted and never contains a newline
            while True:
                idx = self._buf.find(b"\n")
                if idx < 0:
                    break
                line = self._buf[:idx]
                self._buf = self._buf[idx + 1:]
                self._feed_line(line.decode("utf-8", "replace"))

    def feed_line(self, line: str) -> None:
        """Consume one already-split line (for tests and replay)."""
        with self._lock:
            self._feed_line(line)

    def _feed_line(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        self.counters.lines += 1
        tag = text.split(",", 1)[0].strip().upper()

        if tag == CSI_TAG:
            try:
                record = self.csi_parser.feed(text)
            except ValueError:
                self.counters.csi_malformed += 1
                return
            if record is None:
                self.counters.csi_malformed += 1
                return
            self.counters.csi_parsed += 1
            self.csi.push(record)
            return

        if tag in SUPERVISOR_TAGS:
            packet = parse_line(text)
            if packet is None:
                self.counters.supervisor_malformed += 1
                return
            self.counters.supervisor_parsed += 1
            self.supervisor.push(packet)
            return

        # the upstream example prints a CSV header before its packets
        if tag == "TYPE" and text.lower().startswith("type,id,mac"):
            self.counters.headers_seen += 1
            names = [f.strip() for f in text.split(",")]
            if len(names) == len(CSI_FIELD_NAMES):
                self.csi_parser.field_names = names
            return

        self.counters.unknown_lines += 1

    # -- consuming ---------------------------------------------------------

    def drain_csi(self) -> List[CsiRecord]:
        with self._lock:
            return self.csi.drain()

    def drain_supervisor(self) -> List:
        with self._lock:
            return self.supervisor.drain()

    def snapshot(self) -> Dict:
        with self._lock:
            data = self.counters.as_dict()
            data["csi_dropped"] = self.csi.dropped
            data["supervisor_dropped"] = self.supervisor.dropped
            data["csi_sequence_gaps"] = self.csi_parser.gaps
            data["csi_missing_packets"] = self.csi_parser.missing
            data["csi_queued"] = len(self.csi)
            data["supervisor_queued"] = len(self.supervisor)
            data["csi_last_seq"] = self.csi_parser.last_seq
            data["csi_first_seq"] = self.csi_parser.first_seq
            return data


def classify(line: str) -> str:
    """Which consumer a line belongs to: ``csi`` / ``supervisor`` / ``unknown``."""
    text = line.strip()
    if not text:
        return "unknown"
    tag = text.split(",", 1)[0].strip().upper()
    if tag == CSI_TAG:
        return "csi"
    if tag in SUPERVISOR_TAGS:
        return "supervisor"
    return "unknown"
