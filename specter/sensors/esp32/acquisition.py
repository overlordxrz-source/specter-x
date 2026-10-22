"""Trial acquisition that cannot absorb a backlog, and can prove it.

Revised after the independent adversarial review of checkpoint 020, which
falsified two claims in the first version:

* a delivery **burst** before GO skewed the median delay estimate and pulled
  23 pre-GO frames into the window;
* a device **reset** (as opposed to a uint32 wrap) was never detected.

The rules now, each with a regression test:

1. **Continuous drain.** The reader runs for the whole session - cues,
   lead-ins, pauses, final drain - so no backlog can build.
2. **Sensor-time windows.** A frame belongs to a trial by the device's own
   ``local_timestamp``. The host cue is mapped into that clock through the
   measured host-sensor offset.
3. **One-sided delay.** ``host_t - sensor_t`` is a constant offset plus a
   *non-negative* delivery delay. The offset is therefore estimated from the
   **minimum** over the last 60 s, not the median: a burst raises the delay
   and cannot move the estimate. The spread (median minus minimum) is the
   boundary uncertainty, and a trial whose uncertainty exceeds the guard is
   invalid.
4. **Clock discontinuities.** A genuine uint32 wrap is identified by the
   top-half/bottom-half transition; a backwards jump that is not a wrap is a
   **reset**, which invalidates the trial. Out-of-order frames smaller than
   1 s are dropped and counted, never allowed to move the clock.
5. **Explicit accounting.** Per window: payload, null, pre-GO, post-STOP,
   guard, **late** (in-window frames delivered after assignment), the largest
   sensor gap, and the boundary uncertainty. Nothing is silently lost.
6. **Evidence.** Raw serial bytes are written and flushed per chunk; each
   trial is appended to ``<out>.trials.jsonl`` as it completes, so a crash
   loses at most the trial in flight. Samples carry the device timestamp and
   the PHY fields needed to audit them later.
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

SENSOR_WRAP = 1 << 32
SENSOR_WRAP_HALF = 1 << 31
#: a backwards jump larger than this (in microseconds) may be a reset
RESET_THRESHOLD_US = 1_000_000
#: a reset must be confirmed by the next frame inside the new epoch
RESET_CONFIRM_US = 1_000_000
#: a genuine uint32 wrap starts this close to 2^32
WRAP_GUARD_US = 2_000_000
#: how far back the clock offset is estimated
OFFSET_WINDOW_S = 60.0


@dataclass
class Frame:
    host_t: float
    wall_t: float
    sensor_t: float
    seq: int
    rssi: int
    channel: int
    rate: int
    mcs: int
    sig_mode: int
    noise_floor: int
    local_timestamp: int
    sig_len: int
    first_word_invalid: bool
    amplitudes: np.ndarray
    record: object = None


@dataclass
class CueEvent:
    name: str
    host_t: float
    wall_t: float
    sensor_t: Optional[float]
    uncertainty_s: Optional[float] = None


@dataclass
class TrialResult:
    label: str
    block: int
    index: int
    active_s: float
    sensor_span_s: float
    sample_span_s: float
    delivery_span_s: float
    payload_frames: int
    null_frames: int
    excluded_pre: int
    excluded_post: int
    excluded_guard: int
    late_frames: int
    max_sensor_gap_s: float
    boundary_uncertainty_s: float
    clock_resets: int
    valid: bool
    invalid_reason: Optional[str]
    cues: List[Dict]
    samples: List[Dict] = field(default_factory=list)


class TrialRecorder:
    def __init__(self, source, parser: Optional[CsiParser] = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 guard_s: float = 0.10,
                 max_gap_s: float = 1.0,
                 payload_min_sig_len: int = 33,
                 raw_out: Optional[str] = None,
                 span_tolerance_s: float = 0.5,
                 startup_timeout_s: float = 3.0,
                 min_startup_frames: int = 10):
        self.source = source
        self.parser = parser or CsiParser()
        self.clock = clock
        self.wall = wall
        self.sleep = sleep
        self.guard_s = float(guard_s)
        self.max_gap_s = float(max_gap_s)
        self.payload_min_sig_len = int(payload_min_sig_len)
        self.span_tolerance_s = float(span_tolerance_s)
        self.startup_timeout_s = float(startup_timeout_s)
        self.min_startup_frames = int(min_startup_frames)
        self.raw_out = raw_out

        self.frames: List[Frame] = []
        self.malformed = 0
        self.other_lines = 0
        self.out_of_order = 0
        self.clock_resets = 0
        self.cues: List[CueEvent] = []
        self.windows: List[Dict] = []
        self._buf = b""
        self._last_raw_ts: Optional[int] = None
        self._wrap_offset = 0
        self._pending_reset: Optional[tuple] = None
        self._cursor = 0
        self._raw_fh = open(raw_out, "wb") if raw_out else None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # --- reading ---------------------------------------------------------

    def _emit(self, rec, host_t: float, sensor_t: float) -> bool:
        f = Frame(host_t=host_t, wall_t=self.wall(), sensor_t=sensor_t,
                  seq=rec.seq, rssi=rec.rssi, channel=rec.channel,
                  rate=rec.rate, mcs=int(getattr(rec, "mcs", 0) or 0),
                  sig_mode=int(getattr(rec, "sig_mode", 0) or 0),
                  noise_floor=rec.noise_floor,
                  local_timestamp=int(rec.local_timestamp),
                  sig_len=rec.sig_len,
                  first_word_invalid=bool(rec.first_word_invalid),
                  amplitudes=subcarrier_amplitudes(rec.iq), record=rec)
        with self._lock:
            self.frames.append(f)
            for w in self.windows:
                if w["go_s"] <= sensor_t <= w["stop_s"]:
                    w["late"] += 1
        return True

    def _append(self, rec, host_t: float) -> bool:
        """Accept a frame, or settle a clock event.

        A straggler is **kept**: it is appended with its own sensor time and
        sorted into the window later, so a frame that arrives behind newer
        frames is not silently lost. A large backwards jump is held as a
        *candidate* reset and decided by the next frame; one late frame can
        never move the clock epoch. A genuine uint32 wrap must start within
        ``WRAP_GUARD_US`` of 2^32, otherwise a reset is the correct reading.
        """
        raw = int(rec.local_timestamp)
        if self._pending_reset is not None:
            prec, phost, pbase = self._pending_reset
            self._pending_reset = None
            if raw >= pbase and raw - pbase < RESET_CONFIRM_US:
                self._wrap_offset = 0
                self.clock_resets += 1
                self.out_of_order += 1        # the pre-reset frame is dropped
                self._last_raw_ts = raw
                return self._emit(rec, host_t, raw / 1e6)
            # not a reset: the held frame was a straggler, keep it
            self.out_of_order += 1
            self._emit(prec, phost, (pbase + self._wrap_offset) / 1e6)

        if self._last_raw_ts is not None:
            prev = self._last_raw_ts
            if raw < prev:
                back = prev - raw
                if (back > SENSOR_WRAP_HALF and raw < SENSOR_WRAP_HALF
                        and prev > SENSOR_WRAP - WRAP_GUARD_US):
                    self._wrap_offset += SENSOR_WRAP
                elif back > RESET_THRESHOLD_US:
                    self._pending_reset = (rec, host_t, raw)
                    return False
                else:
                    self.out_of_order += 1
                    return self._emit(rec, host_t,
                                      (raw + self._wrap_offset) / 1e6)
            elif (self._wrap_offset > 0 and raw > SENSOR_WRAP_HALF
                  and prev < SENSOR_WRAP_HALF
                  and raw - prev > RESET_THRESHOLD_US):
                # a frame from just before the wrap, delivered after it
                self.out_of_order += 1
                return self._emit(rec, host_t,
                                  (raw + self._wrap_offset - SENSOR_WRAP) / 1e6)
        self._last_raw_ts = raw
        return self._emit(rec, host_t, (raw + self._wrap_offset) / 1e6)

    def _consume(self, chunk: bytes) -> None:
        if not chunk:
            return
        if self._raw_fh is not None:
            self._raw_fh.write(chunk)
            self._raw_fh.flush()
        self._buf += chunk
        while b"\n" in self._buf:
            raw, _, self._buf = self._buf.partition(b"\n")
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if not line.startswith("CSI_DATA"):
                self.other_lines += 1
                continue
            host_t = self.clock()
            outcome = self.parser.feed_resilient(line)
            if outcome.malformed:
                self.malformed += 1
            if not outcome.records:
                continue
            for rec in outcome.records:
                self._append(rec, host_t)

    def pump_once(self) -> int:
        try:
            waiting = int(getattr(self.source, "in_waiting", 0) or 0)
        except Exception:
            waiting = 0
        chunk = self.source.read(max(waiting, 4096))
        if chunk:
            self._consume(chunk)
            return len(chunk)
        return 0

    def pump_for(self, seconds: float) -> None:
        end = self.clock() + float(seconds)
        while self.clock() < end:
            if self._thread is None:
                self.pump_once()
            self.sleep(0.005)
        if self._thread is None:
            self.pump_once()

    def start_background(self) -> None:
        def run():
            while not self._stop.is_set():
                try:
                    self.pump_once()
                except Exception:
                    pass
                self.sleep(0.005)
        self._stop.clear()
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._raw_fh is not None:
            self._raw_fh.flush()
            self._raw_fh.close()
            self._raw_fh = None

    # --- clocks ----------------------------------------------------------

    def _offset(self) -> tuple:
        """(offset, uncertainty) from the one-sided delivery delay.

        ``host - sensor = constant + delay``, and delay >= 0. The minimum
        over the last minute estimates the constant; a burst only raises the
        delay, so it cannot move the estimate. The median-minus-minimum is
        how uncertain the boundary really is.
        """
        now = self.clock()
        with self._lock:
            recent = [f for f in self.frames if f.host_t >= now - OFFSET_WINDOW_S]
        if not recent:
            return None, None
        deltas = [f.host_t - f.sensor_t for f in recent]
        lo = float(min(deltas))
        med = float(np.median(deltas))
        return lo, max(0.0, med - lo)

    def _cue(self, name: str) -> CueEvent:
        host = self.clock()
        off, unc = self._offset()
        ev = CueEvent(name=name, host_t=host, wall_t=self.wall(),
                      sensor_t=None if off is None else host - off,
                      uncertainty_s=unc)
        with self._lock:
            self.cues.append(ev)
        return ev

    # --- trials ----------------------------------------------------------

    def run_trial(self, label: str, duration_s: float, block: int,
                  index: int, lead_in_s: float = 0.0,
                  on_cue: Optional[Callable[[str], None]] = None) -> TrialResult:
        resets_before = self.clock_resets
        if on_cue:
            on_cue("lead_in")
        self._cue("lead_in_start")
        if lead_in_s > 0:
            self.pump_for(lead_in_s)

        # The reader runs in a thread, so with a zero lead-in GO could be
        # taken before the first frame exists and the trial would have no
        # sensor marker at all. Wait a bounded time for the stream to start.
        deadline = self.clock() + self.startup_timeout_s
        while (len(self.frames) < self.min_startup_frames
               and self.clock() < deadline):
            if self._thread is None:
                self.pump_once()
            self.sleep(0.01)

        go = self._cue("go")
        if on_cue:
            on_cue("go")
        self.pump_for(duration_s)
        stop = self._cue("stop")
        if on_cue:
            on_cue("stop")
        self.pump_for(max(self.guard_s * 2.0, 0.2))

        go_s, stop_s = go.sensor_t, stop.sensor_t
        pre = post = guard = 0
        sel: List[Frame] = []
        if go_s is None or stop_s is None or stop_s <= go_s:
            reason = "no sensor clock at the boundaries"
            return TrialResult(
                label=label, block=block, index=index,
                active_s=0.0, sensor_span_s=0.0, sample_span_s=0.0,
                delivery_span_s=0.0, payload_frames=0, null_frames=0,
                excluded_pre=0, excluded_post=0, excluded_guard=0,
                late_frames=None, max_sensor_gap_s=0.0,
                boundary_uncertainty_s=0.0, clock_resets=0, valid=False,
                invalid_reason=reason,
                cues=[e.__dict__ for e in self.cues[-3:]])

        with self._lock:
            pending = self.frames[self._cursor:]
        for f in pending:
            if f.sensor_t < go_s:
                pre += 1
            elif f.sensor_t > stop_s:
                post += 1
            elif (f.sensor_t < go_s + self.guard_s
                  or f.sensor_t > stop_s - self.guard_s):
                guard += 1
            else:
                sel.append(f)
        with self._lock:
            upto = [i for i, f in enumerate(self.frames) if f.sensor_t <= stop_s]
            if upto:
                self._cursor = max(self._cursor, max(upto) + 1)

        sel.sort(key=lambda f: f.sensor_t)
        gaps = [b.sensor_t - a.sensor_t for a, b in zip(sel, sel[1:])]
        max_gap = max(gaps) if gaps else 0.0
        payload = [f for f in sel if f.sig_len >= self.payload_min_sig_len]
        null = len(sel) - len(payload)
        unc = max(go.uncertainty_s or 0.0, stop.uncertainty_s or 0.0)
        active = stop.host_t - go.host_t
        span = stop_s - go_s
        sample_span = (sel[-1].sensor_t - sel[0].sensor_t) if sel else 0.0

        valid, reason = True, None
        if not payload:
            valid, reason = False, "no payload frames in the window"
        elif self.clock_resets != resets_before:
            valid, reason = False, "device clock reset inside the window"
        elif max_gap > self.max_gap_s:
            valid, reason = False, f"sensor gap {max_gap:.3f}s > {self.max_gap_s}s"
        elif unc > self.guard_s:
            valid, reason = False, f"boundary uncertainty {unc:.3f}s > guard"
        elif abs(sample_span - active) > self.span_tolerance_s:
            # the selected frames must actually cover the active window; a
            # clock jump inside it shows up here and nowhere else
            valid, reason = (False,
                             f"sample span {sample_span:.3f}s deviates from "
                             f"active {active:.3f}s")

        window = {"index": index, "go_s": go_s, "stop_s": stop_s, "late": 0}
        with self._lock:
            self.windows.append(window)

        samples = [{
            "t_host": round(f.host_t - go.host_t, 6),
            "t_sensor": round(f.sensor_t - go_s, 6),
            "id": f.seq,
            "rssi": f.rssi,
            "channel": f.channel,
            "rate": f.rate,
            "mcs": f.mcs,
            "sig_mode": f.sig_mode,
            "noise_floor": f.noise_floor,
            "local_timestamp": f.local_timestamp,
            "sig_len": f.sig_len,
            "first_word_invalid": f.first_word_invalid,
            "amplitudes": [round(float(a), 2) for a in f.amplitudes],
        } for f in sel]

        return TrialResult(
            label=label, block=block, index=index,
            active_s=round(active, 4), sensor_span_s=round(span, 6),
            sample_span_s=round(sample_span, 6),
            delivery_span_s=round(sel[-1].host_t - sel[0].host_t, 4) if sel else 0.0,
            payload_frames=len(payload), null_frames=null,
            excluded_pre=pre, excluded_post=post, excluded_guard=guard,
            late_frames=None, max_sensor_gap_s=round(max_gap, 6),
            boundary_uncertainty_s=round(unc, 6),
            clock_resets=self.clock_resets - resets_before,
            valid=valid, invalid_reason=reason,
            cues=[{"name": e.name, "host_t": round(e.host_t - go.host_t, 6),
                   "wall_t": e.wall_t,
                   "sensor_t": (round(e.sensor_t - go_s, 6)
                                if e.sensor_t is not None else None)}
                  for e in self.cues[-3:]],
            samples=samples)

    def settle(self) -> Dict[int, int]:
        """Late in-window frames, per trial index, after the session ends.

        A frame acquired inside a closed window but delivered after the drain
        is counted here. It is not silently dropped and it is not re-labelled
        into another trial: the exclusion counters of the next trial must not
        absorb it.
        """
        with self._lock:
            pending = self._pending_reset
        if pending is not None:
            prec, phost, pbase = pending
            self.out_of_order += 1
            self._emit(prec, phost, (pbase + self._wrap_offset) / 1e6)
            self._pending_reset = None
        with self._lock:
            return {w["index"]: w["late"] for w in self.windows if w["late"]}


def trial_to_json(t: TrialResult, **meta) -> Dict:
    d = {
        "label": t.label, "block": t.block, "index": t.index,
        "requested_s": meta.get("requested_s"),
        "active_s": t.active_s, "sensor_span_s": t.sensor_span_s,
        "sample_span_s": t.sample_span_s,
        "delivery_span_s": t.delivery_span_s,
        "payload_frames": t.payload_frames, "null_frames": t.null_frames,
        "excluded_pre_go": t.excluded_pre, "excluded_post_stop": t.excluded_post,
        "excluded_guard": t.excluded_guard, "late_frames": t.late_frames,
        "max_sensor_gap_s": t.max_sensor_gap_s,
        "boundary_uncertainty_s": t.boundary_uncertainty_s,
        "clock_resets": t.clock_resets,
        "valid": t.valid, "invalid_reason": t.invalid_reason,
        "cues": t.cues, "samples": t.samples,
    }
    d.update({k: v for k, v in meta.items() if k != "requested_s"})
    return d
