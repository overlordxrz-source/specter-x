"""Permanent gates for the defects the adversarial review found.

Each test fails against the implementation that the review falsified. The
names say what is being prevented, so a future regression is legible from
the test list alone.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import specter.sensors.esp32.analysis as A  # noqa: E402
from specter.sensors.esp32.acquisition import TrialRecorder  # noqa: E402


# --- helpers ---------------------------------------------------------------

class FakeClock:
    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, d):
        self.t += float(d)

    def wall(self):
        return 1_700_000_000.0 + self.t


class FakeSource:
    def __init__(self, clock, schedule):
        self.clock = clock
        self.schedule = sorted(schedule, key=lambda x: x[0])
        self.i = 0
        self.buf = b""

    @property
    def in_waiting(self):
        return len(self.buf)

    def read(self, n):
        while self.i < len(self.schedule) and self.schedule[self.i][0] <= self.clock.t:
            self.buf += self.schedule[self.i][1]
            self.i += 1
        out, self.buf = self.buf, b""
        return out


def _line(seq, ts_us, sig_len=138, noise=-94):
    iq = ",".join(["0", "0", "3", "4"] * 32)
    return (f'CSI_DATA,{seq},de:1c:7e:d8:26:70,-50,11,1,6,0,1,1,0,0,0,1,'
            f'{noise},0,6,0,{ts_us},0,{sig_len},1,128,0,"[{iq}]"\n').encode()


def _rec(clock, schedule, **kw):
    return TrialRecorder(FakeSource(clock, schedule), clock=clock,
                         wall=clock.wall, sleep=clock.sleep, **kw)


def make_trial(label, sigma, seed, block=0, n=200, carriers=64):
    rng = np.random.default_rng(seed)
    base = np.full((n, carriers), 20.0)
    walk = np.cumsum(rng.normal(0.0, sigma, (n, carriers)), axis=0)
    return {"label": label, "block": block, "amplitudes": base + walk,
            "used": np.ones(carriers, bool)}


# --- C1: blocks must be shuffled with the trials ---------------------------

def test_a_passed_block_list_is_shuffled_with_the_trials():
    trials = [make_trial("stationary" if i % 2 == 0 else "hand", 0.02, i,
                         block=i // 2) for i in range(6)]
    blocks = [t["block"] for t in trials]
    res = A.analyse_blinded(trials, seed=5, n_perm=5, blocks=blocks)
    assert res["blocks"] == [trials[i]["block"] for i in res["order"]]


# --- C2: a delivery burst must not move the GO marker ----------------------

def test_a_delivery_burst_before_go_does_not_pull_in_old_frames():
    """The burst must be the MAJORITY of the offset window, as in the review."""
    clock = FakeClock()
    sched = []
    # 40 normal 10 Hz frames, sensor == host, zero delivery delay
    for i in range(40):
        sched.append((i * 0.1, _line(1 + i, int(i * 0.1 * 1e6))))
    # the reader stalls; 60 frames acquired at sensor 4.0..9.9 arrive in one
    # burst at host 10.0 (delay 6.0 .. 0.1) - now the majority of the window
    for k in range(60):
        sensor = 4.0 + k * 0.1
        sched.append((10.0, _line(300 + k, int(sensor * 1e6))))
    # frames acquired after GO, delivered on time
    for k in range(9):
        sensor = 10.1 + k * 0.1
        sched.append((10.1 + k * 0.1, _line(400 + k, int(sensor * 1e6))))

    rec = _rec(clock, sched, guard_s=0.05)
    rec.pump_for(10.0)
    t = rec.run_trial("hand", 1.0, block=0, index=0, lead_in_s=0.05)
    ids = {s["id"] for s in t.samples}
    assert ids and min(ids) >= 400, sorted(ids)[:8]
    assert len(ids) <= 10


# --- M1: a device reset is detected and invalidates the trial -------------

def test_a_device_clock_reset_invalidates_the_trial():
    clock = FakeClock()
    sched = []
    for i in range(20):                       # sensor 0.0 .. 1.9
        sched.append((i * 0.1, _line(i, int(i * 0.1 * 1e6))))
    for i in range(10):                       # reset: sensor restarts at 0
        sched.append((2.0 + i * 0.1, _line(100 + i, int(i * 0.1 * 1e6))))
    rec = _rec(clock, sched, guard_s=0.01)
    rec.pump_for(0.05)
    t = rec.run_trial("hand", 3.0, block=0, index=0, lead_in_s=0.0)
    assert rec.clock_resets >= 1
    assert t.clock_resets >= 1
    assert t.valid is False
    assert "reset" in (t.invalid_reason or "")


# --- M2: late in-window frames are counted, not silently lost -------------

def test_late_in_window_frames_are_counted_by_settle():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]              # prime offset = 0
    for i in range(5):                        # on-time in-window frames
        sched.append((5.40 + i * 0.01, _line(10 + i, int((5.40 + i * 0.01) * 1e6))))
    # later frames of the SAME window arrive only after the drain
    for i in range(5):
        sched.append((7.5 + i * 0.01, _line(80 + i, int((5.45 + i * 0.01) * 1e6))))
    rec = _rec(clock, sched, guard_s=0.02, min_startup_frames=1)
    rec.pump_for(5.0)
    t = rec.run_trial("stationary", 1.0, block=0, index=1, lead_in_s=0.15)
    assert t.payload_frames == 5
    rec.pump_for(3.0)                         # the late frames arrive
    late = rec.settle()
    assert late.get(1, 0) >= 3, late


# --- M3: held-out features are fitted per fold ----------------------------

def test_a_test_block_trial_cannot_change_another_test_trial():
    trials = [make_trial("stationary", 0.02, 10, block=0),
              make_trial("hand", 0.30, 11, block=0),
              make_trial("stationary", 0.02, 12, block=1),
              make_trial("hand", 0.30, 13, block=1)]
    labels = [t["label"] for t in trials]
    blocks = [t["block"] for t in trials]
    before = A.cross_validate_trials(trials, labels, "shape_shift",
                                     blocks=blocks, positive="hand")
    p_before = [p for p in before["predictions"] if p["index"] == 3][0]

    changed = [dict(t) for t in trials]
    changed[2] = make_trial("stationary", 0.40, 99, block=1)   # same block
    after = A.cross_validate_trials(changed, labels, "shape_shift",
                                    blocks=blocks, positive="hand")
    p_after = [p for p in after["predictions"] if p["index"] == 3][0]
    assert p_before["predicted"] == p_after["predicted"]


# --- M5: NaN / tiny folds are reported, not silently skipped ---------------

def test_a_short_trial_produces_a_reason_not_a_silent_zero():
    trials = [make_trial("stationary", 0.02, 20, block=0),
              make_trial("hand", 0.30, 21, block=0)]
    trials.append({"label": "stationary", "block": 1,
                   "amplitudes": np.zeros((2, 64)), "used": np.ones(64, bool)})
    trials.append(make_trial("hand", 0.30, 23, block=1))
    res = A.cross_validate_trials(trials, [t["label"] for t in trials],
                                  "change_rate", blocks=[t["block"] for t in trials])
    assert res["n_scored"] < 4
    assert res["skipped_folds"], "a skipped fold must carry a reason"
    assert all("reason" in s for s in res["skipped_folds"])


def test_all_nan_groups_do_not_make_a_number():
    f = A._f_statistic({"a": [float("nan")] * 3, "b": [1.0, 2.0, 3.0]})
    assert f != f, "an undefined contrast must stay undefined"


# --- M6: out-of-order timestamps must not wedge the cursor ----------------

def test_out_of_order_frames_do_not_wedge_the_cursor():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]
    for i in range(10):
        sched.append((1.0 + i * 0.01, _line(10 + i, int((1.0 + i * 0.01) * 1e6))))
    sched.append((1.2, _line(90, int(1.05 * 1e6))))   # reordered, older
    for i in range(10):
        sched.append((1.3 + i * 0.01, _line(20 + i, int((1.3 + i * 0.01) * 1e6))))
    rec = _rec(clock, sched, guard_s=0.02)
    rec.pump_for(0.05)
    t1 = rec.run_trial("stationary", 0.6, block=0, index=1, lead_in_s=0.05)
    t2 = rec.run_trial("stationary", 0.2, block=0, index=2, lead_in_s=0.2)
    assert rec.out_of_order >= 1
    assert t2.excluded_pre <= 12, t2.excluded_pre


# --- m1: the permutation p cannot be finer than the design ----------------

def test_permutation_p_never_goes_below_its_floor():
    trials = [make_trial("stationary", 0.02, 30 + i, block=i // 2)
              for i in range(6)]
    for i, t in enumerate(trials):
        t["label"] = "stationary" if i % 2 == 0 else "hand"
    parts = [A._trial_parts(t) for t in trials]
    labels = [t["label"] for t in trials]
    blocks = [t["block"] for t in trials]
    r = A.permutation_test_crossfit(parts, labels, blocks, "roughness_used",
                                    n_perm=30, seed=25)
    assert r["min_attainable_p"] is not None
    assert r["empirical_p"] >= r["min_attainable_p"]


# --- m2: a spliced line yields both records; unknown lines are counted ----

def test_a_lost_newline_yields_both_records_and_other_lines_are_counted():
    clock = FakeClock()
    a = _line(1, 0)[:-1]          # strip the newline
    b = _line(2, 100_000)
    sched = [(0.0, a + b), (0.1, b"HELLO,2,esp32s3,x,aa:bb,1,2\n")]
    rec = _rec(clock, sched)
    rec.pump_for(0.5)
    assert len(rec.frames) == 2
    assert rec.other_lines == 1
    assert rec.malformed == 0


# --- m4: a reordered frame across the wrap must not double the offset -----

def test_a_reordered_frame_does_not_double_the_wrap_offset():
    clock = FakeClock()
    base = (1 << 32) - 100_000
    sched = []
    for i in range(5):
        sched.append((i * 0.01, _line(i, (base + i * 10_000) % (1 << 32))))
    # a frame from just before the wrap, delivered after it
    sched.append((0.06, _line(99, (base + 35_000) % (1 << 32))))
    rec = _rec(clock, sched)
    rec.pump_for(0.2)
    spans = [f.sensor_t for f in rec.frames]
    assert max(spans) - min(spans) < 1.0
    assert rec.out_of_order >= 1


# --- m5: the multivariate held-out score exists ---------------------------

def test_multivariate_held_out_evaluation_scores_trials():
    trials = [make_trial("stationary", 0.02, 40 + i, block=i // 2)
              for i in range(4)]
    for i, t in enumerate(trials):
        t["label"] = "stationary" if i % 2 == 0 else "hand"
    res = A.cross_validate_trials(trials, [t["label"] for t in trials],
                                  list(A.FEATURE_NAMES),
                                  blocks=[t["block"] for t in trials])
    assert res["n_scored"] > 0
    assert res["held_out_accuracy"] is not None


# --- m6: stop_background clears the thread -------------------------------

def test_stop_background_clears_the_thread_reference():
    clock = FakeClock()
    rec = _rec(clock, [(0.0, _line(0, 0))])
    rec.start_background()
    rec.stop_background()
    assert rec._thread is None


# --- m7: the 52-wide layout is not re-masked -----------------------------

def test_a_52_wide_array_keeps_all_52_carriers():
    assert A.lltf_used_mask(52).sum() == 52
    assert A.lltf_used_mask(64).sum() == 52


# --- m3: the raw stream is flushed while the recorder is still open ------

def test_raw_stream_is_readable_before_close(tmp_path):
    clock = FakeClock()
    path = str(tmp_path / "raw.bin")
    rec = _rec(clock, [(0.0, _line(1, 0))], raw_out=path)
    rec.pump_for(0.1)
    on_disk = open(path, "rb").read()
    assert b"CSI_DATA" in on_disk
    rec.stop_background()


# --- T2: the offset probe used the wrong reference ------------------------

def test_a_constant_delivery_lag_maps_to_the_cue_acquisition_time():
    """A constant lag is not a defect: it is the clock offset.

    The critic measured 'pre-GO' against host time. The cue's *acquisition*
    time is host - lag, and that is what the window must start at.
    """
    clock = FakeClock()
    sched = []
    acq = {}
    for k in range(400):
        t = k * 0.1
        sched.append((t + 2.0, _line(k, int(round(t * 1e6)))))
        acq[k] = t
    rec = _rec(clock, sched, guard_s=0.1)
    rec.pump_for(10.0)
    t = rec.run_trial("hand", 20.0, block=0, index=0, lead_in_s=0.0)
    go_s = rec.cues[-2].sensor_t
    assert abs(go_s - 8.0) < 0.15, go_s          # host 10, lag 2 -> acq 8
    assert t.samples
    assert all(acq[s["id"]] >= go_s - 0.02 for s in t.samples)


# --- T3: reset after half an hour is not a wrap ---------------------------

def test_a_reset_after_half_an_hour_is_not_mistaken_for_a_wrap():
    clock = FakeClock()
    base = 2_160_000_000                       # 36 minutes of uptime
    sched = []
    for i in range(20):
        sched.append((i * 0.1, _line(i, base + int(i * 0.1 * 1e6))))
    for i in range(20):                        # device resets to zero
        sched.append((2.0 + i * 0.1, _line(100 + i, int(i * 0.1 * 1e6))))
    rec = _rec(clock, sched, guard_s=0.01)
    rec.pump_for(0.05)
    t = rec.run_trial("hand", 4.0, block=0, index=0, lead_in_s=0.0)
    assert rec.clock_resets >= 1
    assert t.clock_resets >= 1
    assert t.valid is False
    assert "reset" in (t.invalid_reason or "")


def test_one_late_frame_does_not_reset_the_clock_and_is_kept():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]
    sched += [(2.0, _line(10, 2_000_000)), (2.1, _line(11, 2_100_000))]
    sched += [(2.15, _line(99, 500_000))]      # 1.6 s behind: a straggler
    sched += [(2.2, _line(12, 2_200_000)), (2.3, _line(13, 2_300_000))]
    rec = _rec(clock, sched, guard_s=0.02, min_startup_frames=1)
    rec.pump_for(0.05)
    t = rec.run_trial("hand", 3.0, block=0, index=0, lead_in_s=0.0)
    assert rec.clock_resets == 0
    assert rec.out_of_order >= 1
    assert 99 in {s["id"] for s in t.samples}, "the straggler must be kept"


def test_a_pre_wrap_straggler_does_not_double_the_offset():
    clock = FakeClock()
    base = (1 << 32) - 300_000
    sched = []
    for i in range(5):
        sched.append((i * 0.1, _line(i, (base + i * 50_000) % (1 << 32))))
    for i in range(5):                         # after the wrap
        sched.append((0.5 + i * 0.1,
                      _line(10 + i, (base + 300_000 + i * 50_000) % (1 << 32))))
    # a frame from before the wrap, delivered last
    sched.append((1.1, _line(99, (base + 100_000) % (1 << 32))))
    rec = _rec(clock, sched, guard_s=0.02)
    rec.pump_for(2.0)
    spans = [f.sensor_t for f in rec.frames]
    assert max(spans) - min(spans) < 1.5
    assert rec.out_of_order >= 1


# --- T6 gaps: the two validity checks need tests of their own -------------

def test_high_boundary_uncertainty_invalidates_the_trial():
    clock = FakeClock()
    sched = [(k * 0.1, _line(k, int(k * 0.1 * 1e6))) for k in range(40)]
    rec = _rec(clock, sched, guard_s=0.10)
    rec._offset = lambda: (0.0, 0.20)         # uncertainty above the guard
    rec.pump_for(0.2)
    t = rec.run_trial("hand", 1.0, block=0, index=0, lead_in_s=0.0)
    assert t.valid is False
    assert "uncertainty" in (t.invalid_reason or "")


def test_an_incomplete_window_invalidates_the_trial():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]
    # nothing acquired for the first 2 s of a 4 s window
    for i in range(20):
        ts = 2.1 + i * 0.1
        sched.append((ts, _line(10 + i, int(round(ts * 1e6)))))
    rec = _rec(clock, sched, guard_s=0.02)
    rec.pump_for(0.05)
    t = rec.run_trial("hand", 4.0, block=0, index=0, lead_in_s=0.0)
    assert t.valid is False
    assert "sample span" in (t.invalid_reason or "")


def test_offset_uses_the_minimum_delay_and_reports_the_spread():
    clock = FakeClock()
    sched = [(0.0, _line(0, 0))]               # one fast frame
    for k in range(49):                        # many frames delayed 0.2 s
        sensor = 0.1 + k * 0.1
        sched.append((sensor + 0.2, _line(1 + k, int(round(sensor * 1e6)))))
    rec = _rec(clock, sched)
    rec.pump_for(6.0)
    off, unc = rec._offset()
    assert off < 0.05, off                      # min, not the 10th percentile
    assert unc > 0.1, unc


def test_a_silent_link_returns_a_result_not_a_crash():
    """The no-sensor-clock path must be a TrialResult, not a TypeError."""
    rec = _rec(FakeClock(), [])
    t = rec.run_trial("bench", 0.2, block=0, index=0, lead_in_s=0.0)
    assert t.valid is False
    assert "sensor clock" in (t.invalid_reason or "")


def test_a_trial_with_zero_lead_in_waits_for_the_first_frame():
    """Regression: GO was taken before the reader thread had any frame."""
    clock = FakeClock()
    sched = [(0.30 + i * 0.05, _line(i, int((0.30 + i * 0.05) * 1e6)))
             for i in range(12)]
    rec = _rec(clock, sched, guard_s=0.01, min_startup_frames=1)
    # synchronous path: the warm-up loop is what must wait for a frame
    t = rec.run_trial("bench", 0.6, block=0, index=0, lead_in_s=0.0)
    assert t.valid is True, t.invalid_reason
    assert t.payload_frames > 0


def test_a_torn_first_line_is_counted_and_does_not_poison_the_next():
    """The observed splice: one torn record at line 0, then a clean stream."""
    clock = FakeClock()
    torn = (b"CSI_DATA,2,de:1c:7e:d8:26:70,-50,11,1,6,0,1,1,0,0,0,1,-94,0,"
            b"SPECTER_STAT,role=softap,peer=de:1c:7e:d8:26:70,ch=6\n")
    good = _line(3, 100_000)
    rec = _rec(clock, [(0.0, torn + good)])
    rec.pump_for(0.1)
    assert rec.malformed == 1
    assert [f.seq for f in rec.frames] == [3], [f.seq for f in rec.frames]


def test_go_waits_for_the_startup_frame_floor():
    """The offset estimate needs several frames, not just one."""
    clock = FakeClock()
    sched = [(0.02 * i, _line(i, int(0.02 * i * 1e6))) for i in range(30)]
    rec = _rec(clock, sched, guard_s=0.01, min_startup_frames=10)
    t = rec.run_trial("bench", 0.5, block=0, index=0, lead_in_s=0.0)
    # GO is taken only once ten frames exist, so none of them are guessed
    assert rec.cues[-2].sensor_t is not None
    assert rec.cues[-2].sensor_t >= 0.18 - 0.02
    assert t.valid is True
