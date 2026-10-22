"""The whole repaired pipeline must detect a known signal and reject its null.

This is the audit's third gate, deliberately end-to-end: synthetic raw CSI
lines go through the *recorder* (continuous drain, sensor-time window,
payload selection), into the JSON schema, through ``trials_from_json`` and
``analyse_blinded``. Nothing is handed to the statistics directly.

Two sessions share the same timing, blocks and noise:

* **positive** - ``hand`` trials carry a per-carrier temporal modulation, so
  ``roughness_used`` must separate them and the permutation test must fire;
* **null** - ``hand`` trials use the stationary generator, so the same
  pipeline must not fire.

Passing means a physical signal of this shape would be detectable by the
apparatus *as now instrumented*. It says nothing about whether a real hand
produces it.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.acquisition import TrialRecorder  # noqa: E402
from specter.sensors.esp32.analysis import analyse_blinded  # noqa: E402
from specter.sensors.esp32.experiment import trials_from_json  # noqa: E402

LEAD_IN = 0.10
SECONDS = 2.0
GAP = 0.28          # the recorder's post-window drain (0.2) plus a pause


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, d):
        self.t += d

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


def _line(seq: int, ts_us: int, amps) -> bytes:
    iq = []
    for a in amps:
        iq.extend([0, int(round(a))])          # (imag, real); hypot = amplitude
    body = ",".join(str(v) for v in iq)
    return (f'CSI_DATA,{seq},de:1c:7e:d8:26:70,-50,11,1,6,0,1,1,0,0,0,1,'
            f'-94,0,6,0,{ts_us},0,138,1,128,0,"[{body}]"\n').encode()


def _plan(blocks: int = 3, n_per_block: int = 4):
    rng = np.random.default_rng(7)
    plan = []
    for b in range(blocks):
        block = (["stationary"] * (n_per_block // 2)
                 + ["hand"] * (n_per_block // 2))
        rng.shuffle(block)
        plan.extend((lab, b) for lab in block)
    return plan


def _schedule(plan, moving: bool, rate_hz: float = 10.0):
    rng = np.random.default_rng(11)
    schedule = []
    clock = 0.0
    seq = 1
    for label, _block in plan:
        clock += LEAD_IN
        n = int(SECONDS * rate_hz)
        for k in range(n):
            t = k / rate_hz
            amps = 20.0 + rng.normal(0.0, 0.4, 64)
            if moving and label == "hand":
                amps = amps + 6.0 * np.sin(
                    2 * math.pi * 1.2 * t + np.arange(64) * 0.1)
            schedule.append((clock + t,
                             _line(seq, int(round((clock + t) * 1e6)),
                                   np.clip(amps, 1, 127))))
            seq += 1
        clock += SECONDS + GAP
    return schedule


def _run(moving: bool):
    plan = _plan()
    schedule = _schedule(plan, moving)
    clock = FakeClock()
    rec = TrialRecorder(FakeSource(clock, schedule), clock=clock,
                        wall=clock.wall, sleep=clock.sleep,
                        guard_s=0.02, max_gap_s=1.0)
    trials = []
    for label, block in plan:
        rec.pump_for(LEAD_IN)
        t = rec.run_trial(label, SECONDS, block=block,
                          index=len(trials) + 1, lead_in_s=0.0)
        trials.append({"label": t.label, "block": block,
                       "requested_s": SECONDS, "active_s": t.active_s,
                       "sensor_span_s": t.sensor_span_s,
                       "valid": t.valid, "samples": t.samples})
        rec.pump_for(GAP - 0.2)
    return {"trials": trials}


def test_the_pipeline_detects_an_injected_signature_and_rejects_its_null():
    pos = _run(moving=True)
    labels = [t["label"] for t in pos["trials"]]
    assert labels.count("stationary") == 6 and labels.count("hand") == 6
    assert all(t["valid"] for t in pos["trials"]), \
        [(t["label"], t["valid"], t["sensor_span_s"]) for t in pos["trials"]]

    res = analyse_blinded(trials_from_json(pos), seed=3, n_perm=200)
    prim = res["permutation"]["roughness_used"]
    assert prim["empirical_p"] is not None
    assert prim["empirical_p"] < 0.05, prim
    assert prim["block_preserving"] is True
    assert res["held_out"]["roughness_used"]["held_out_auc"] >= 0.8

    nul = _run(moving=False)
    resn = analyse_blinded(trials_from_json(nul), seed=3, n_perm=200)
    pn = resn["permutation"]["roughness_used"]
    assert pn["empirical_p"] is not None
    assert pn["empirical_p"] > 0.05, pn
