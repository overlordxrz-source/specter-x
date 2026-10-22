"""The v2 preregistration must be enforceable, not decorative.

Each test builds a synthetic 10-block session and checks that the frozen
analysis says exactly what the preregistration says it will: PASS only for a
large consistent paired effect, FAIL for a null, INVALID for any broken
validity rule, INCONCLUSIVE for a traffic/PHY confound.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "alpha002c_motion_v2", os.path.join(REPO, "tools", "alpha002c_motion_v2.py"))
v2 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v2
_spec.loader.exec_module(v2)


def _trial(label, block, sigma, seed, n=220, rate=10.0):
    rng = np.random.default_rng(seed)
    base = np.full((n, 64), 20.0)
    amps = base + np.cumsum(rng.normal(0.0, sigma, (n, 64)), axis=0)
    samples = [{
        "id": i, "rssi": -55, "channel": 6, "rate": 11, "mcs": 0,
        "sig_mode": 0, "noise_floor": -94,
        "local_timestamp": i * 100000, "sig_len": 138,
        "first_word_invalid": False,
        "amplitudes": [round(float(a), 2) for a in row],
    } for i, row in enumerate(amps)]
    span = max(1.0, n / rate)
    return {"label": label, "block": block, "valid": True, "samples": samples,
            "sensor_span_s": span, "active_s": span,
            "max_sensor_gap_s": 0.1, "boundary_uncertainty_s": 0.03}


def _session(tmp_path, hand_sigma=0.30, stationary_sigma=0.02,
             rate_hand=10.0, rate_stationary=10.0, invalid_block=None):
    trials = []
    for b in range(10):
        trials.append(_trial("stationary", b, stationary_sigma, 100 + b,
                             rate=rate_stationary))
        trials.append(_trial("hand", b, hand_sigma, 200 + b, rate=rate_hand))
    if invalid_block is not None:
        for t in trials:
            if t["block"] == invalid_block and t["label"] == "hand":
                t["valid"] = False
                t["invalid_reason"] = "sensor gap"
    raw = tmp_path / "r.bin"
    raw.write_bytes(b'CSI_DATA,1,aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,'
                    b'-94,0,6,0,1000000,0,138,1,128,0,"[0,0]"\n')
    return {"trials": trials, "raw": str(raw)}


def test_a_large_consistent_paired_effect_passes(tmp_path):
    r = v2.analyse(_session(tmp_path))
    assert r["verdict"] == "PASS", (r["verdict"], r.get("reason"))
    assert r["primary"]["p"] == 2 / 1024
    assert abs(r["primary"]["dz"]) >= v2.D_GATE


def test_a_null_session_fails(tmp_path):
    r = v2.analyse(_session(tmp_path, hand_sigma=0.02))
    assert r["verdict"] == "FAIL", r.get("reason")
    assert r["primary"]["p"] > 0.01


def test_one_invalid_trial_invalidates_the_session(tmp_path):
    r = v2.analyse(_session(tmp_path, invalid_block=3))
    assert r["verdict"] == "INVALID"
    assert any("trial" in p for p in r["trial_problems"])


def test_a_payload_rate_confound_is_inconclusive(tmp_path):
    # both rates inside the 9-11 validity band, but >10% apart
    r = v2.analyse(_session(tmp_path, rate_hand=10.6,
                            rate_stationary=9.5))
    assert r["verdict"] == "INCONCLUSIVE", r.get("reason")
    assert r["confounds"]["rate_ok"] is False


def test_a_malformed_line_after_the_first_record_invalidates(tmp_path):
    s = _session(tmp_path)
    raw = tmp_path / "bad.bin"
    raw.write_bytes(b'CSI_DATA,1,aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,'
                    b'-94,0,6,0,1000000,0,138,1,128,0,"[0,0]"\n'
                    b'CSI_DATA,2,aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,'
                    b'-94,0,SPECTER_STAT,role=softap\n')
    s["raw"] = str(raw)
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("malformed CSI line" in p for p in r["raw_problems"])


def test_a_wrong_design_invalidates(tmp_path):
    s = _session(tmp_path)
    s["trials"] = s["trials"][:-1]
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("expected 20" in p or "blocks" in p for p in r["design_problems"])


def test_the_preregistered_constants_are_frozen():
    assert v2.BLOCKS == 10
    assert (1 << v2.BLOCKS) == 1024
    assert v2.P_GATE == 0.01
    assert v2.D_GATE == 0.8
    assert v2.PRIMARY == "roughness_used"
    assert v2.TRIAL_S == 25.0
