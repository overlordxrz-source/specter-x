"""Turning a stream of CSI packets into something a person can read.

The HUD needs three things the raw packet does not give it:

* a **history**. A single packet is a snapshot; the interesting thing about
  Wi-Fi CSI is how it *changes*.
* a **baseline**. "Changed" is only meaningful against what the channel was
  doing when nothing was happening.
* an honest separation of **signal change** from **human detection**. This
  module measures the radio path and nothing else. It never claims that a
  person is present - only that the radio path moved, and by how much.

The signal model
----------------
Each packet carries 128 raw interleaved I/Q samples = 64 complex
subcarriers. The ESP32-S3 leaves some of them unpopulated - subcarrier 0 is
DC and 27..37 are the guard band - and those read as exactly zero. They are
detected from the data rather than assumed, and they are excluded from every
statistic: including them would dilute every measure with twelve carriers
that are supposed to be silent.

The change metric
-----------------
The total amplitude of a packet is almost proportional to the received
power, so it mostly measures the radio, not the room. The metric here is
therefore computed on the **normalised** spectrum - each packet divided by
its own total - and compared against a **baseline** that is a slow moving
average of the normalised spectrum. The result is a dimensionless "how far
the multipath profile is from the recent past", which is what a body in the
path changes.

Time base
---------
A waterfall at one column per packet would scroll past in under two
seconds. The state therefore *buckets* packets into columns (6 packets by
default, so a column is about 34 ms) and the waterfall scrolls at roughly
30 columns a second - about twenty seconds of history in a 640 column
buffer. The change trace shares the same buckets, so the two views are
always in step.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Sequence

import numpy as np

from .dispatcher import CsiRecord

#: The ESP32-S3's 802.11n 20 MHz layout, as measured on this board. The
#: null set is *also* detected from the data, so this is only the starting
#: expectation, never the authority.
EXPECTED_SUBCARRIERS = 64
EXPECTED_NULL = (0,) + tuple(range(27, 38))

#: A carrier is considered unused after this many consecutive zero readings.
NULL_CONFIRM_PACKETS = 5


def complex_subcarriers(iq: Sequence[int]) -> np.ndarray:
    """The complex subcarriers, as (I, Q) pairs.

    The upstream payload is a flat list of interleaved I/Q samples, so
    subcarrier *n* is ``(iq[2n], iq[2n+1])``. A trailing odd sample has no
    partner and is reported by the caller, not silently dropped.
    """
    if not iq:
        return np.zeros((0, 2), np.float32)
    usable = len(iq) - (len(iq) % 2)
    return np.asarray(iq[:usable], dtype=np.float32).reshape(-1, 2)


def subcarrier_amplitudes_np(iq: Sequence[int]) -> np.ndarray:
    """Per-subcarrier amplitude from the complex samples."""
    c = complex_subcarriers(iq)
    if c.size == 0:
        return np.zeros(0, np.float32)
    return np.hypot(c[:, 0], c[:, 1])


class CsiViewState:
    """The rolling state behind the CSI view.

    Memory is bounded by construction: the waterfall and the trace are
    fixed-size ring buffers, and the source history is a short deque.
    """

    def __init__(self, columns: int = 640, carriers: int = EXPECTED_SUBCARRIERS,
                 baseline_s: float = 12.0, packet_rate: float = 178.0,
                 packets_per_column: int = 6):
        self.columns = int(columns)
        self.carriers = int(carriers)
        self.baseline_s = float(baseline_s)
        self.packet_rate = float(packet_rate)
        self.packets_per_column = max(1, int(packets_per_column))

        #: the amplitude history, one column per bucket of packets
        self._amp = np.zeros((self.carriers, self.columns), np.float32)
        self._head = 0
        self._filled = 0

        #: the baseline-relative change, one value per column
        self._trace = np.zeros(self.columns, np.float32)
        self._trace_head = 0

        #: the running bucket
        self._bucket = np.zeros(self.carriers, np.float64)
        self._bucket_n = 0
        self._bucket_change = 0.0

        #: the slow moving average of the normalised spectrum
        self._baseline = np.zeros(self.carriers, np.float32)
        self._baseline_ready = False
        self._baseline_samples = 0
        self._alpha = 1.0 / max(self.baseline_s * self.packet_rate, 1.0)

        #: null-carrier detection
        self._zero_run = np.zeros(self.carriers, np.int32)
        self._null = np.zeros(self.carriers, bool)
        self._null_seen = 0

        self._last_amps = np.zeros(self.carriers, np.float32)
        self._last_iq_count = 0
        self._last_odd = False

        self._source_mac = ""
        self._source_channel: Optional[int] = None
        self._source_changes = 0
        self._source_history: Deque[str] = deque(maxlen=8)

        self._rssi = 0
        self._noise_floor = 0
        self._local_timestamp = 0
        self._packets = 0
        self._peak = 1.0
        self._change = 0.0
        self._change_max = 0.0
        self._change_ema = 0.0

    # -- feeding ------------------------------------------------------------

    def push(self, record: CsiRecord) -> None:
        """Fold one CSI packet into the state."""
        amps = subcarrier_amplitudes_np(record.iq)
        if amps.size == 0:
            return
        self.push_amplitudes(
            amps, rssi=record.rssi, noise_floor=record.noise_floor,
            local_timestamp=record.local_timestamp, source_mac=record.mac,
            source_channel=record.channel)

    def push_amplitudes(self, amps: np.ndarray, rssi: int = 0,
                        noise_floor: int = 0, local_timestamp: int = 0,
                        source_mac: str = "", source_channel=None) -> None:
        """Fold one packet's subcarrier amplitudes into the state.

        Split out from :meth:`push` so a **recorded** session can be replayed
        into the view without the complex samples - the amplitudes are all
        the view needs.
        """
        amps = np.asarray(amps, dtype=np.float32)
        if amps.size == 0:
            return
        if amps.size != self.carriers:
            amps = self._fit(amps)

        # null-carrier detection: a carrier that has read exactly zero for
        # several packets in a row is not being populated by the radio.
        zero = amps <= 0.0
        self._zero_run = np.where(zero, self._zero_run + 1, 0)
        self._null = self._zero_run >= NULL_CONFIRM_PACKETS
        self._null_seen += 1

        used = ~self._null
        total = float(amps[used].sum()) if used.any() else float(amps.sum())
        norm = amps / total if total > 0 else amps * 0.0

        # baseline: an exponential moving average of the normalised profile
        if not self._baseline_ready:
            self._baseline = norm.copy()
            self._baseline_ready = True
        else:
            self._baseline += self._alpha * (norm - self._baseline)
        self._baseline_samples += 1

        # the change metric: mean absolute deviation from the baseline over
        # the carriers that are actually in use.
        if used.any():
            dev = np.abs(norm[used] - self._baseline[used])
            change = float(dev.mean())
            self._change_max = max(self._change_max, float(dev.max()))
        else:
            change = 0.0
        self._change = change
        self._change_ema = (0.9 * self._change_ema + 0.1 * change
                            if self._baseline_samples > 1 else change)

        # accumulate into the current column
        self._bucket += amps
        self._bucket_n += 1
        self._bucket_change += change
        if self._bucket_n >= self.packets_per_column:
            self._amp[:, self._head] = (self._bucket / self._bucket_n).astype(np.float32)
            self._trace[self._trace_head] = self._bucket_change / self._bucket_n
            self._head = (self._head + 1) % self.columns
            self._trace_head = (self._trace_head + 1) % self.columns
            self._filled = min(self._filled + 1, self.columns)
            self._bucket[:] = 0.0
            self._bucket_n = 0
            self._bucket_change = 0.0

        # the display scale follows the data, but slowly, so the picture does
        # not flicker when one packet is loud.
        self._peak = max(float(amps.max()), self._peak * 0.995, 1.0)

        self._last_amps = amps
        self._last_iq_count = int(amps.size) * 2
        self._last_odd = False
        self._rssi = rssi
        self._noise_floor = noise_floor
        self._local_timestamp = local_timestamp
        self._packets += 1

        # The CSI source is the transmitter of the frame the board heard. It
        # is not necessarily the AP the board is associated with: a guest
        # network has several, and the board roams between them. A change is
        # therefore worth recording, not smoothing over.
        mac = (source_mac or "").lower()
        if mac and mac != self._source_mac:
            if self._source_mac:
                self._source_changes += 1
                self._source_history.append(
                    f"{self._source_mac} ch{self._source_channel} -> {mac} "
                    f"ch{source_channel}")
            self._source_mac = mac
        self._source_channel = source_channel

    def _fit(self, amps: np.ndarray) -> np.ndarray:
        """Fit a packet's carrier count onto the fixed grid."""
        out = np.zeros(self.carriers, np.float32)
        n = min(amps.size, self.carriers)
        out[:n] = amps[:n]
        return out

    # -- reading ------------------------------------------------------------

    def waterfall(self) -> np.ndarray:
        """The amplitude history, oldest column first."""
        if self._filled < self.columns:
            buf = np.zeros((self.carriers, self.columns), np.float32)
            buf[:, :self._filled] = self._amp[:, :self._filled]
            return buf
        return np.roll(self._amp, -self._head, axis=1)

    def trace(self) -> np.ndarray:
        """The change history, oldest first."""
        if self._filled < self.columns:
            buf = np.zeros(self.columns, np.float32)
            buf[:self._filled] = self._trace[:self._filled]
            return buf
        return np.roll(self._trace, -self._trace_head)

    def used_mask(self) -> np.ndarray:
        return ~self._null

    def null_indices(self) -> List[int]:
        return [int(i) for i in np.flatnonzero(self._null)]

    def history_seconds(self) -> float:
        """How much time the visible history covers."""
        cols = max(self._filled, 1)
        return cols * self.packets_per_column / max(self.packet_rate, 1.0)

    def view(self, health=None) -> Dict:
        """The view dictionary the HUD draws from."""
        amps = self._last_amps
        used = self.used_mask()
        view = {
            "amplitudes": [round(float(a), 1) for a in amps],
            "used_carriers": int(used.sum()),
            "total_carriers": int(self.carriers),
            "null_carriers": self.null_indices(),
            "iq_samples": self._last_iq_count,
            "odd_trailing_sample": self._last_odd,
            "complex_iq": True,
            "source_mac": self._source_mac,
            "source_channel": self._source_channel,
            "source_changes": self._source_changes,
            "source_history": list(self._source_history),
            "rssi": self._rssi,
            "noise_floor": self._noise_floor,
            "local_timestamp": self._local_timestamp,
            "packets_seen": self._packets,
            "change": round(self._change, 6),
            "change_ema": round(self._change_ema, 6),
            "change_max": round(self._change_max, 6),
            "baseline_ready": bool(self._baseline_ready
                                   and self._baseline_samples > 30),
            "baseline_samples": self._baseline_samples,
            "history_s": round(self.history_seconds(), 2),
            "peak": round(self._peak, 2),
        }
        if health is not None:
            view.update({
                "link_state": getattr(getattr(health, "state", None), "value", None),
                "link_detail": getattr(health, "detail", ""),
                "packets": getattr(health, "packets", 0),
                "packets_per_s": round(getattr(health, "packets_per_s", 0.0), 2),
                "first_id": getattr(health, "first_id", None),
                "last_id": getattr(health, "last_id", None),
                "gaps": getattr(health, "gaps", 0),
                "missing_packets": getattr(health, "missing_packets", 0),
                "malformed": getattr(health, "malformed", 0),
                "dropped": getattr(health, "dropped", 0),
                "unknown_lines": getattr(health, "unknown_lines", 0),
                "silence_s": round(getattr(health, "silence_s", 0.0), 3),
                "reconnects": getattr(health, "reconnects", 0),
                "uptime_s": round(getattr(health, "uptime_s", 0.0), 1),
                "bytes": getattr(health, "bytes", 0),
            })
        return view
