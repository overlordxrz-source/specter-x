"""Trial acquisition that cannot absorb a backlog, and can prove it.

The Alpha 002-C audit found that a nominal 20-second trial contained 43-55
seconds of *sensor* history: acquisition stopped while cues were spoken and
while the operator waited, the USB/CDC path buffered, and the next trial read
the backlog and labelled it with its own condition. Every number computed
from those trials inherited the defect.

This module replaces that design with three rules, each of which is tested:

1. **The stream is drained continuously.** A reader runs for the whole
   session - through lead-ins, cues, between trials and through the final
   drain - so no backlog can build. Reading is never paused to speak or to
   wait.

2. **A frame belongs to a trial by its own acquisition time on the device.**
   Every frame carries the device's ``local_timestamp``, which advances with
   acquisition, not with delivery. A trial is the half-open interval
   ``[go_sensor, stop_sensor]`` in that clock, so a frame that was acquired
   before GO is excluded even if it arrives during the window.

3. **The boundary is treated as uncertain.** The GO and STOP markers are the
   freshest sensor timestamp seen at the cue, so each is up to one frame
   interval old. Frames within ``guard_s`` of either boundary are excluded
   and counted, rather than assigned on a coin flip.

Everything the analysis needs to check the rules is recorded: cue events in
both clocks, per-trial sensor span and delivery span, excluded counts, the
largest sensor gap, and a validity flag with its reason. The raw serial bytes
are written beside the JSON so IQ, PHY metadata and validity flags survive.

The module has no hardware dependency: ``source`` is anything with
``read(n)`` and ``in_waiting``, and ``clock``/``sleep`` are injectable, so the
contamination defect is reproduced and refuted in tests without a board.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np

from .csi import subcarrier_amplitudes
from .dispatcher import CsiParser

SENSOR_WRAP = 1 << 32          # local_timestamp is a uint32 of microseconds
SENSOR_WRAP_HALF = 1 << 31


@dataclass
class Frame:
    """One parsed CSI frame, with both clocks."""
    host_t: float              # monotonic seconds at read
    wall_t: float              # wall-clock seconds at read
    sensor_t: float            # unwrapped device acquisition seconds
    seq: int
    rssi: int
    channel: int
    rate: int
    sig_len: int
    first_word_invalid: bool
    amplitudes: np.ndarray
    record: object = None


@dataclass
class CueEvent:
    """A cue, recorded in both clocks, with the sensor marker at that moment."""
    name: str
    host_t: float
    wall_t: float
    sensor_t: Optional[float]


@dataclass
class TrialResult:
    label: str
    block: int
    index: int
    active_s: float
    sensor_span_s: float
    delivery_span_s: float
    payload_frames: int
    null_frames: int
    excluded_pre: int
    excluded_post: int
    excluded_guard: int
    max_sensor_gap_s: float
    valid: bool
    invalid_reason: Optional[str]
    cues: List[Dict]
    samples: List[Dict] = field(default_factory=list)


class TrialRecorder:
    """Continuously drain a CSI source and cut trials by sensor time."""

    def __init__(self, source, parser: Optional[CsiParser] = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 guard_s: float = 0.10,
                 max_gap_s: float = 1.0,
                 payload_min_sig_len: int = 33,
                 raw_out: Optional[str] = None):
        self.source = source
        self.parser = parser or CsiParser()
        self.clock = clock
        self.wall = wall
        self.sleep = sleep
        self.guard_s = float(guard_s)
        self.max_gap_s = float(max_gap_s)
        self.payload_min_sig_len = int(payload_min_sig_len)
        self.raw_out = raw_out

        self.frames: List[Frame] = []
        self.malformed = 0
        self.cues: List[CueEvent] = []
        self._buf = b""
        self._last_raw_ts: Optional[int] = None
        self._wrap_offset = 0
        #: frames before this index have already been assigned to a trial
        self._cursor = 0
        self._raw_fh = open(raw_out, "wb") if raw_out else None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # --- reading ---------------------------------------------------------

    def _consume(self, chunk: bytes) -> None:
        if not chunk:
            return
        if self._raw_fh is not None:
            self._raw_fh.write(chunk)
        self._buf += chunk
        while b"\n" in self._buf:
            raw, _, self._buf = self._buf.partition(b"\n")
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("CSI_DATA"):
                continue
            try:
                rec = self.parser.feed(line)
            except ValueError:
                self.malformed += 1
                continue
            raw_ts = int(rec.local_timestamp)
            if (self._last_raw_ts is not None
                    and raw_ts < self._last_raw_ts - SENSOR_WRAP_HALF):
                self._wrap_offset += SENSOR_WRAP
            self._last_raw_ts = raw_ts
            sensor_t = (raw_ts + self._wrap_offset) / 1e6
            with self._lock:
                self.frames.append(Frame(
                    host_t=self.clock(), wall_t=self.wall(), sensor_t=sensor_t,
                    seq=rec.seq, rssi=rec.rssi, channel=rec.channel,
                    rate=rec.rate, sig_len=rec.sig_len,
                    first_word_invalid=bool(rec.first_word_invalid),
                    amplitudes=subcarrier_amplitudes(rec.iq), record=rec))

    def pump_once(self) -> int:
        """Read whatever is available now. Returns the number of bytes read."""
        n = 0
        try:
            waiting = int(getattr(self.source, "in_waiting", 0) or 0)
        except Exception:
            waiting = 0
        chunk = self.source.read(max(waiting, 4096))
        if chunk:
            n = len(chunk)
            self._consume(chunk)
        return n

    def pump_for(self, seconds: float) -> None:
        """Drain continuously for a wall-clock duration.

        When the background reader is running it is the only reader: two
        threads must never read the same port.
        """
        end = self.clock() + float(seconds)
        while self.clock() < end:
            if self._thread is None:
                self.pump_once()
            self.sleep(0.005)
        if self._thread is None:
            self.pump_once()

    def start_background(self) -> None:
        """Drain in a thread, for the CLI where cues may block."""
        def run():
            while not self._stop.is_set():
                try:
                    self.pump_once()
                except Exception:
                    pass
                self.sleep(0.005)
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._raw_fh is not None:
            self._raw_fh.close()
            self._raw_fh = None

    # --- trials ----------------------------------------------------------

    def _last_sensor(self) -> Optional[float]:
        with self._lock:
            return self.frames[-1].sensor_t if self.frames else None

    def _host_to_sensor_offset(self) -> Optional[float]:
        """The device-to-host clock offset, from recent delivery delays.

        ``host_t - sensor_t`` is a constant (the two clocks start at
        different epochs) plus a small, positive delivery delay. The median
        over recent frames estimates the constant, so a host-time boundary
        can be mapped into the device's acquisition clock even when no frame
        happens to arrive exactly at the cue. Using the *last frame* instead
        would leave the marker stale whenever the stream pauses.
        """
        with self._lock:
            recent = self.frames[-50:]
        if not recent:
            return None
        return float(np.median([f.host_t - f.sensor_t for f in recent]))

    def _cue(self, name: str) -> CueEvent:
        host = self.clock()
        off = self._host_to_sensor_offset()
        ev = CueEvent(name=name, host_t=host, wall_t=self.wall(),
                      sensor_t=None if off is None else host - off)
        self.cues.append(ev)
        return ev

    def run_trial(self, label: str, duration_s: float, block: int,
                  index: int, lead_in_s: float = 0.0,
                  on_cue: Optional[Callable[[str], None]] = None) -> TrialResult:
        """Record one trial, assigning frames by device acquisition time.

        Imports the audit's rule directly: the window is
        ``[go_sensor, stop_sensor]``, boundaries within ``guard_s`` are
        excluded, and a window whose largest sensor gap exceeds
        ``max_gap_s`` is marked invalid rather than silently analysed.
        """
        if on_cue:
            on_cue("lead_in")
        self._cue("lead_in_start")
        if lead_in_s > 0:
            self.pump_for(lead_in_s)

        go = self._cue("go")
        if on_cue:
            on_cue("go")
        self.pump_for(duration_s)
        stop = self._cue("stop")
        if on_cue:
            on_cue("stop")
        # let frames that were acquired just before STOP arrive
        self.pump_for(max(self.guard_s * 2.0, 0.2))

        go_s = go.sensor_t
        stop_s = stop.sensor_t
        pre = post = guard = 0
        sel: List[Frame] = []
        if go_s is None or stop_s is None or stop_s <= go_s:
            reason = "no sensor clock at the boundaries"
            return TrialResult(label, block, index, 0.0, 0.0, 0.0, 0, 0,
                               0, 0, 0, 0.0, False, reason,
                               [e.__dict__ for e in self.cues[-3:]])

        # only frames since the previous trial can belong to this one, so a
        # long session does not re-count earlier trials as "pre-GO backlog"
        with self._lock:
            pending = self.frames[self._cursor:]
        for f in pending:
            if f.sensor_t < go_s:
                pre += 1
            elif f.sensor_t > stop_s:
                post += 1
            elif f.sensor_t < go_s + self.guard_s or \
                    f.sensor_t > stop_s - self.guard_s:
                guard += 1
            else:
                sel.append(f)
        # consume everything up to and including this window
        with self._lock:
            idx = self._cursor
            while idx < len(self.frames) and self.frames[idx].sensor_t <= stop_s:
                idx += 1
            self._cursor = idx

        sel.sort(key=lambda f: f.sensor_t)
        gaps = [b.sensor_t - a.sensor_t for a, b in zip(sel, sel[1:])]
        max_gap = max(gaps) if gaps else 0.0
        payload = [f for f in sel if f.sig_len >= self.payload_min_sig_len]
        null = len(sel) - len(payload)

        valid = True
        reason = None
        if not payload:
            valid, reason = False, "no payload frames in the window"
        elif max_gap > self.max_gap_s:
            valid, reason = False, f"sensor gap {max_gap:.3f}s > {self.max_gap_s}s"

        samples = [{
            "t_host": round(f.host_t - go.host_t, 6),
            "t_sensor": round(f.sensor_t - go_s, 6),
            "id": f.seq,
            "rssi": f.rssi,
            "channel": f.channel,
            "rate": f.rate,
            "sig_len": f.sig_len,
            "first_word_invalid": f.first_word_invalid,
            "amplitudes": [round(float(a), 2) for a in f.amplitudes],
        } for f in sel]

        return TrialResult(
            label=label, block=block, index=index,
            active_s=round(stop.host_t - go.host_t, 4),
            sensor_span_s=round(stop_s - go_s, 6),
            delivery_span_s=round(sel[-1].host_t - sel[0].host_t, 4) if sel else 0.0,
            payload_frames=len(payload), null_frames=null,
            excluded_pre=pre, excluded_post=post, excluded_guard=guard,
            max_sensor_gap_s=round(max_gap, 6), valid=valid,
            invalid_reason=reason,
            cues=[{"name": e.name, "host_t": round(e.host_t - go.host_t, 6),
                   "wall_t": e.wall_t,
                   "sensor_t": (round(e.sensor_t - go_s, 6)
                                if e.sensor_t is not None else None)}
                  for e in self.cues[-3:]],
            samples=samples)


def trial_to_json(t: TrialResult, **meta) -> Dict:
    d = {
        "label": t.label, "block": t.block, "index": t.index,
        "requested_s": meta.get("requested_s"),
        "active_s": t.active_s, "sensor_span_s": t.sensor_span_s,
        "delivery_span_s": t.delivery_span_s,
        "payload_frames": t.payload_frames, "null_frames": t.null_frames,
        "excluded_pre_go": t.excluded_pre, "excluded_post_stop": t.excluded_post,
        "excluded_guard": t.excluded_guard,
        "max_sensor_gap_s": t.max_sensor_gap_s,
        "valid": t.valid, "invalid_reason": t.invalid_reason,
        "cues": t.cues, "samples": t.samples,
    }
    d.update({k: v for k, v in meta.items() if k != "requested_s"})
    return d
