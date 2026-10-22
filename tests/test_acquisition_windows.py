"""Trial windows must exclude what was acquired outside them.

The audit reproduced the defect with a mock that held only pre-trial bytes:
the old recorder labelled one packet as ``hand``. These tests reproduce that
failure against the new recorder and show it is fixed - pre-GO excluded,
post-STOP excluded, late-but-in-window kept, a sensor wrap handled, and a
silence gap marked invalid. No hardware: source and clocks are injected.
"""
from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.acquisition import TrialRecorder  # noqa: E402


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def sleep(self, d: float) -> None:
        self.t += float(d)

    def wall(self) -> float:
        return 1_700_000_000.0 + self.t


class FakeSource:
    """Delivers scheduled chunks when the fake clock passes their host time."""

    def __init__(self, clock: FakeClock, schedule):
        self.clock = clock
        self.schedule = sorted(schedule, key=lambda x: x[0])
        self.i = 0
        self.buf = b""

    @property
    def in_waiting(self) -> int:
        return len(self.buf)

    def read(self, n: int) -> bytes:
        while self.i < len(self.schedule) and self.schedule[self.i][0] <= self.clock.t:
            self.buf += self.schedule[self.i][1]
            self.i += 1
        out, self.buf = self.buf, b""
        return out


def _line(seq: int, ts_us: int, sig_len: int = 138) -> bytes:
    iq = ",".join(["0", "0", "3", "4"] * 32)
    return (f'CSI_DATA,{seq},de:1c:7e:d8:26:70,-50,11,1,6,0,1,1,0,0,0,1,'
            f'-94,0,6,0,{ts_us},0,{sig_len},1,128,0,"[{iq}]"\n').encode()


def _recorder(clock, source, **kw):
    return TrialRecorder(source, clock=clock, wall=clock.wall,
                         sleep=clock.sleep, **kw)


def test_only_pre_trial_bytes_are_excluded():
    """The audit's probe: pre-trial bytes must never become a trial."""
    clock = FakeClock()
    sched = [(i * 0.1, _line(i, int(i * 0.1 * 1e6))) for i in range(10)]
    rec = _recorder(clock, FakeSource(clock, sched))
    rec.pump_for(1.0)
    t = rec.run_trial("hand", 1.0, block=0, index=0, lead_in_s=0.2)
    assert t.excluded_pre == 10, t.excluded_pre
    assert t.payload_frames == 0
    assert t.samples == []
    assert t.valid is False


def test_frames_inside_the_window_are_kept_by_sensor_time():
    """A frame acquired inside the window is kept even when delivered late."""
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]                     # prime the clock offset
    # acquired at sensor 1.00..1.09 but delivered 0.2 s late
    sched += [(1.2 + i * 0.001, _line(100 + i, int((1.0 + i * 0.01) * 1e6)))
              for i in range(10)]
    rec = _recorder(clock, FakeSource(clock, sched))
    rec.pump_for(0.05)
    t = rec.run_trial("stationary", 1.5, block=0, index=0, lead_in_s=0.05)
    assert t.payload_frames == 10, (t.payload_frames, t.excluded_guard,
                                    t.excluded_pre, t.invalid_reason)
    assert {s["id"] for s in t.samples} == set(range(100, 110))


def test_post_stop_frames_are_excluded():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]                     # prime offset = 0
    for i in range(10):                              # inside 5.4..5.49
        sched.append((5.4 + i * 0.01, _line(10 + i, int((5.4 + i * 0.01) * 1e6))))
    for i in range(3):                               # after the window
        sched.append((9.0 + i * 0.1, _line(50 + i, int((9.0 + i * 0.1) * 1e6))))
    rec = _recorder(clock, FakeSource(clock, sched))
    rec.pump_for(5.0)
    t = rec.run_trial("stationary", 1.0, block=0, index=0, lead_in_s=0.15)
    assert {s["id"] for s in t.samples} == set(range(10, 20)), [s["id"] for s in t.samples]
    assert all(s["id"] < 50 for s in t.samples), "post-STOP frames must not be labelled"
    # and they are not silently lost: the next trial counts them as pre-GO
    rec.pump_for(4.0)
    t2 = rec.run_trial("hand", 1.0, block=0, index=1, lead_in_s=0.1)
    assert t2.excluded_pre >= 3, t2.excluded_pre


def test_sensor_clock_wrap_is_unwrapped():
    """local_timestamp is a uint32 of microseconds; it wraps every 71.6 min."""
    clock = FakeClock()
    base = (1 << 32) - 50_000
    sched = [(i * 0.01, _line(i, (base + i * 10_000) % (1 << 32)))
             for i in range(10)]
    rec = _recorder(clock, FakeSource(clock, sched))
    rec.pump_for(0.2)
    spans = [f.sensor_t for f in rec.frames]
    assert spans == sorted(spans), "sensor time must stay monotonic across the wrap"
    assert spans[-1] - spans[0] < 1.0


def test_a_sensor_gap_invalidates_the_trial():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]                     # prime offset = 0
    for i, ts in enumerate((1.2, 1.21, 4.2, 4.21)):
        sched.append((ts, _line(10 + i, int(ts * 1e6))))
    rec = _recorder(clock, FakeSource(clock, sched), max_gap_s=1.0)
    rec.pump_for(0.5)
    t = rec.run_trial("hand", 4.0, block=0, index=0, lead_in_s=0.6)
    assert t.max_sensor_gap_s > 1.0, t.max_sensor_gap_s
    assert t.valid is False
    assert "gap" in (t.invalid_reason or "")
