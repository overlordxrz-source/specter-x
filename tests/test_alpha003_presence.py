"""Tests for the Alpha 003 offline presence infrastructure.

These are synthetic/code tests only. They do not contain human data and do
not establish presence detection.
"""
from __future__ import annotations

import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.presence import (  # noqa: E402
    FEATURE_SETS, attach_iq_from_raw, differential_phase, evaluate,
    leave_one_session_out, phase_features, stationary_recall_by_posture,
    trial_features, trial_qc)
from specter.sensors.esp32.presence_synthetic import (  # noqa: E402
    PresenceSyntheticLink)


def _trial(label: str, seconds: float = 4.0, seed: int = 1):
    link = PresenceSyntheticLink(seed=1, rate_hz=20)
    profile = link._profile()
    return link._trial(label, seconds, 0, "synthetic", profile, seed)


def _line(seq: int, iq: list[int]) -> str:
    fields = ["CSI_DATA", str(seq), "aa:bb:cc:dd:ee:ff", "-50",
              "11", "1", "6", "0", "1", "1", "0", "0", "0", "1",
              "-94", "0", "6", "0", str(1000000 + seq), "0", "138",
              "1", "128", "0"]
    return ",".join(fields) + ',"[' + ",".join(str(v) for v in iq) + ']"'


def test_differential_phase_cancels_a_common_offset():
    k = np.arange(64)
    phase = 0.3 + 0.11 * k + 0.02 * np.sin(k / 3.0)
    iq = np.exp(1j * phase)
    d0 = differential_phase(iq)
    d1 = differential_phase(iq * np.exp(1j * 2.7))
    assert d0.size > 0
    assert np.allclose(d0, d1, atol=1e-10)


def test_attach_iq_from_raw_matches_ids(tmp_path):
    iq = [((i % 7) - 3) for i in range(128)]
    raw = "\n".join(_line(seq, iq) for seq in (1, 2, 3)) + "\n"
    p = tmp_path / "raw.bin"
    p.write_text(raw)
    trials = [{"samples": [{"id": 1}, {"id": 2}, {"id": 3}]}]
    stats = attach_iq_from_raw(trials, str(p))
    assert stats["attached"] == 3
    assert stats["missing"] == 0
    assert all("iq" in s for s in trials[0]["samples"])
    assert phase_features(trials[0]["samples"])["phase_frames"] == 3


def test_moving_has_more_temporal_change_than_empty():
    empty = _trial("empty", seed=4)
    moving = _trial("moving", seed=4)
    fe = trial_features(empty)
    fm = trial_features(moving)
    assert fm["roughness_used"] > fe["roughness_used"]
    assert fm["phase_roughness"] > fe["phase_roughness"]
    assert fm["phase_std"] > fe["phase_std"]


def test_phase_features_are_nan_without_iq():
    empty = _trial("empty")
    samples = [{k: v for k, v in s.items() if k != "iq"}
               for s in empty["samples"]]
    fe = trial_features({"samples": samples})
    # trial_features does not invent phase from amplitudes
    assert fe["phase_frames"] == 0
    assert np.isnan(fe["phase_roughness"])


def test_trial_features_do_not_read_the_label():
    a = _trial("stationary")
    b = dict(a)
    b["label"] = "moving"
    fa = trial_features(a)
    fb = trial_features(b)
    for key in ("roughness_used", "amp_volatility", "phase_roughness",
                "phase_std", "phase_resp_ratio", "rssi_mean"):
        assert (np.isnan(fa[key]) and np.isnan(fb[key])) or \
            abs(fa[key] - fb[key]) < 1e-12


def test_folds_hold_out_every_session():
    trials = [{"session_id": s, "label": "empty"} for s in ("a", "b", "c")]
    folds = leave_one_session_out(trials)
    assert len(folds) == 3
    for train, test, session in folds:
        assert test
        assert all(trials[i]["session_id"] != session for i in train)
        assert all(trials[i]["session_id"] == session for i in test)


def test_synthetic_moving_is_learnable_and_null_is_not_evidence():
    link = PresenceSyntheticLink(seed=3, rate_hz=20)
    data = link.make_dataset(n_sessions=4, blocks=3, seconds=4.0)
    r = evaluate(data, ("empty", "moving"), FEATURE_SETS["all"],
                 n_perm=20, seed=5, n_boot=50)
    assert r["n_sessions"] == 4
    assert r["balanced_accuracy"] > 0.8
    assert r["auc"] > 0.8
    assert r["null"]["p"] < 0.2
    assert r["empty_false_positive_rate"] <= 0.25


def test_stationary_benchmark_is_reported_without_a_claim():
    link = PresenceSyntheticLink(seed=4, rate_hz=20)
    data = link.make_dataset(n_sessions=3, blocks=3, seconds=4.0)
    r = evaluate(data, ("empty", "stationary"), FEATURE_SETS["all"],
                 n_perm=0, seed=3, n_boot=20)
    assert 0.0 <= r["balanced_accuracy"] <= 1.0
    assert "empty_false_positive_rate" in r
    assert r["ci"]["balanced_accuracy"][0] <= r["balanced_accuracy"] + 1e-9


def test_rssi_only_ablation_is_explicit():
    link = PresenceSyntheticLink(seed=5, rate_hz=20)
    data = link.make_dataset(n_sessions=3, blocks=2, seconds=3.0)
    r = evaluate(data, ("empty", "moving"), FEATURE_SETS["rssi_only"],
                 n_perm=0, seed=2, n_boot=10)
    assert r["features"] == ["rssi_mean"]
    assert "balanced_accuracy" in r


def test_calibrated_analysis_is_explicitly_labelled():
    link = PresenceSyntheticLink(seed=6, rate_hz=20)
    data = link.make_dataset(n_sessions=3, blocks=2, seconds=3.0)
    r = evaluate(data, ("empty", "stationary"), FEATURE_SETS["all"],
                 n_perm=0, seed=2, n_boot=10,
                 calibration="session_empty")
    assert r["calibration"] == "session_empty"
    assert "balanced_accuracy" in r


def test_posture_recall_is_reported_separately():
    preds = [
        {"true": "stationary", "posture": "standing",
         "pred": "stationary"},
        {"true": "stationary", "posture": "standing", "pred": "empty"},
        {"true": "stationary", "posture": "sitting",
         "pred": "stationary"},
        {"true": "empty", "posture": None, "pred": "empty"},
    ]
    r = stationary_recall_by_posture(preds)
    assert r["standing"]["n"] == 2 and r["standing"]["recall"] == 0.5
    assert r["sitting"]["n"] == 1 and r["sitting"]["recall"] == 1.0


def test_trial_qc_rejects_short_or_invalid_trials():
    good = {"label": "empty", "active_s": 30.0,
            "max_sensor_gap_s": 0.1, "boundary_uncertainty_s": 0.03,
            "clock_resets": 0, "late_frames": 0,
            "samples": [{"sig_len": 138}] * 270}
    assert trial_qc(good) == []
    bad = dict(good)
    bad["active_s"] = 25.0
    bad["samples"] = [{"sig_len": 138}] * 10
    problems = trial_qc(bad)
    assert any("payload" in p for p in problems)
    assert any("active window" in p for p in problems)
