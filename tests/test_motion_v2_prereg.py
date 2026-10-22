"""The v2 preregistration must be enforceable, not decorative.

Each test builds a synthetic 10-block session and checks that the frozen
analysis says exactly what the preregistration says it will: PASS only for a
large consistent paired effect in the pre-registered direction, FAIL for a
null, INVALID for any broken validity rule, INCONCLUSIVE for a traffic/PHY
confound. The bypasses the final review found are tested explicitly.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "alpha002c_motion_v2", os.path.join(REPO, "tools", "alpha002c_motion_v2.py"))
v2 = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v2
_spec.loader.exec_module(v2)

IQ = ",".join(["0", "0"] * 64)          # 128 values, len=128


def _raw_line(seq):
    return (f'CSI_DATA,{seq},aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,'
            f'-94,0,6,0,{1000000 + seq},0,138,1,128,0,"[{IQ}]"\n').encode()


def _trial(label, block, sigma, seed, n=None, rate=10.0, index=None):
    if n is None:
        n = int(round(v2.TRIAL_S * rate))       # rate is varied by frame count
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
    span = v2.TRIAL_S
    return {"label": label, "block": block, "valid": True, "samples": samples,
            "sensor_span_s": span, "active_s": span, "sample_span_s": span,
            "max_sensor_gap_s": 0.1, "boundary_uncertainty_s": 0.03,
            "clock_resets": 0, "late_frames": 0, "index": index}


def _session(tmp_path, hand_sigma=0.30, stationary_sigma=0.02,
             rate_hand=10.0, rate_stationary=10.0, invalid_block=None,
             raw=None):
    trials = []
    idx = 0
    for b in range(10):
        # alternate which condition comes first, so the order is not fixed
        order = [("stationary", stationary_sigma, 100 + b, rate_stationary),
                 ("hand", hand_sigma, 200 + b, rate_hand)]
        if b % 2:
            order.reverse()
        for label, sigma, seed, rate in order:
            idx += 1
            trials.append(_trial(label, b, sigma, seed, rate=rate, index=idx))
    if invalid_block is not None:
        for t in trials:
            if t["block"] == invalid_block and t["label"] == "hand":
                t["valid"] = False
                t["invalid_reason"] = "sensor gap"
    n_lines = sum(len(t["samples"]) for t in trials)
    raw_path = tmp_path / "r.bin"
    if raw is None:
        raw_path.write_bytes(b"".join(_raw_line(i) for i in range(n_lines)))
    else:
        raw_path.write_bytes(raw)
    return {"trials": trials, "raw": str(raw_path),
            "design": {"seed": 7, "trial_order": [], "blocks": []},
            "geometry": {
                "distance_m": 1.50, "phone_height_m": 0.80,
                "esp32_height_m": 0.80,
                "spot_longitudinal_m": 0.0, "spot_lateral_m": 0.30,
                "s_phone_m": 0.808, "s_esp32_m": 0.808,
                "phone_orientation": "screen facing the board",
                "recorded_utc": "2026-10-22T00:00:00Z",
                "confirmed_by": "operator",
            },
            "malformed": 0, "clock_resets": 0, "late_frames": {}}


def test_a_large_consistent_paired_effect_passes(tmp_path):
    r = v2.analyse(_session(tmp_path))
    assert r["verdict"] == "PASS", (r["verdict"], r.get("reason"))
    assert r["primary"]["p"] == 1 / 1024
    assert r["primary"]["dz"] >= v2.D_GATE


def test_a_null_session_fails(tmp_path):
    r = v2.analyse(_session(tmp_path, hand_sigma=0.02))
    assert r["verdict"] == "FAIL", r.get("reason")
    assert r["primary"]["p"] > 0.01


def test_one_invalid_trial_invalidates_the_session(tmp_path):
    r = v2.analyse(_session(tmp_path, invalid_block=3))
    assert r["verdict"] == "INVALID"
    assert any("trial" in p for p in r["trial_problems"])


def test_a_payload_rate_confound_is_inconclusive(tmp_path):
    r = v2.analyse(_session(tmp_path, rate_hand=10.6,
                            rate_stationary=9.5))
    assert r["verdict"] == "INCONCLUSIVE", r.get("reason")
    assert r["confounds"]["rate_ok"] is False


def test_a_malformed_line_after_the_first_record_invalidates(tmp_path):
    s = _session(tmp_path)
    raw = b"".join(_raw_line(i) for i in range(3))
    raw += (b'CSI_DATA,9,aa:bb:cc:dd:ee:ff,-50,11,1,6,0,1,1,0,0,0,1,-94,0,'
            b'SPECTER_STAT,role=softap\n')
    s["raw"] = str(tmp_path / "bad.bin")
    open(s["raw"], "wb").write(raw)
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
    assert v2.TRIAL_S == 25.0
    assert v2.P_GATE == 0.01
    assert v2.D_GATE == 0.8
    assert v2.PRIMARY == "roughness_used"
    assert 1 / (1 << v2.BLOCKS) < v2.P_GATE


def test_a_modal_phy_difference_is_not_hidden_by_set_equality(tmp_path):
    """9/10 frames at 11 vs 9/10 at 3 used to look identical as sets."""
    s = _session(tmp_path)
    for t in s["trials"]:
        if t["label"] == "stationary":
            for i, x in enumerate(t["samples"]):
                x["rate"] = 11 if i < 225 else 3
        else:
            for i, x in enumerate(t["samples"]):
                x["rate"] = 3 if i < 225 else 11
    r = v2.analyse(s)
    assert r["verdict"] == "INCONCLUSIVE", r.get("reason")
    assert r["confounds"]["phy_ok"] is False


def test_a_missing_phy_rate_invalidates(tmp_path):
    s = _session(tmp_path)
    for x in s["trials"][0]["samples"]:
        x["rate"] = None
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"


def test_nan_or_missing_validity_fields_invalidate(tmp_path):
    for field, value in (("boundary_uncertainty_s", float("nan")),
                         ("max_sensor_gap_s", None),
                         ("sample_span_s", None)):
        s = _session(tmp_path)
        s["trials"][2][field] = value
        r = v2.analyse(s)
        assert r["verdict"] == "INVALID", (field, r["verdict"])


def test_clock_resets_and_late_frames_invalidate(tmp_path):
    s = _session(tmp_path)
    s["trials"][1]["clock_resets"] = 1
    assert v2.analyse(s)["verdict"] == "INVALID"
    s = _session(tmp_path)
    s["trials"][1]["late_frames"] = 3
    assert v2.analyse(s)["verdict"] == "INVALID"


def test_an_empty_raw_invalidates(tmp_path):
    s = _session(tmp_path, raw=b"")
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("empty" in p for p in r["raw_problems"])


def test_a_short_trial_invalidates(tmp_path):
    s = _session(tmp_path)
    for t in s["trials"]:
        t["active_s"] = t["sensor_span_s"] = t["sample_span_s"] = 20.0
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("active" in p for p in r["trial_problems"])


def test_a_sample_span_mismatch_invalidates(tmp_path):
    s = _session(tmp_path)
    s["trials"][0]["sample_span_s"] = 10.0
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("sample span" in p for p in r["trial_problems"])


def test_the_direction_is_frozen_and_negative_effects_fail(tmp_path):
    """H1 is hand > stationary; a negative effect is not a two-sided PASS."""
    assert v2.signflip_p([1.0] * 10)[0] == 1 / 1024
    assert v2.signflip_p([-1.0] * 10)[0] == 1.0
    r = v2.analyse(_session(tmp_path, hand_sigma=0.02, stationary_sigma=0.30))
    assert r["verdict"] == "FAIL"
    assert r["primary"]["dz"] < 0


def test_the_geometry_record_is_required(tmp_path):
    s = _session(tmp_path)
    del s["geometry"]
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("geometry" in p for p in r["geometry_problems"])


def test_out_of_range_geometry_is_invalid(tmp_path):
    s = _session(tmp_path)
    s["geometry"]["distance_m"] = 1.70
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("distance_m" in p for p in r["geometry_problems"])


def test_inconsistent_spot_distances_are_rejected(tmp_path):
    """The measured S-to-antenna distances must follow from L, long and lat."""
    s = _session(tmp_path)
    # 0.90 m would be a 0.40 m lateral offset, not the recorded 0.30 m
    s["geometry"]["s_phone_m"] = 0.90
    s["geometry"]["s_esp32_m"] = 0.90
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("disagrees" in p for p in r["geometry_problems"])


def test_a_longitudinal_offset_outside_the_amendment_is_rejected(tmp_path):
    s = _session(tmp_path)
    s["geometry"]["spot_longitudinal_m"] = 0.30
    r = v2.analyse(s)
    assert r["verdict"] == "INVALID"
    assert any("spot_longitudinal_m" in p for p in r["geometry_problems"])
