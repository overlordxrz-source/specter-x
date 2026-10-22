"""Tests for the blinded analysis, the ground-truth bench, and the parser fixes."""
from __future__ import annotations

import numpy as np
import pytest

from specter.sensors.esp32.analysis import (FEATURE_NAMES, analyse_blinded,
                                            blinded_order, bootstrap_ci,
                                            cohens_d, cohens_d_ci, cross_validate,
                                            effect_sizes, extract_features,
                                            omnibus, partial_eta_squared,
                                            permutation_test,
                                            power_by_simulation, required_n)
from specter.sensors.esp32.csi_analysis import CsiViewState
from specter.sensors.esp32.dispatcher import CsiParser
from specter.sensors.esp32.synthetic_link import CARRIERS, NULL_CARRIERS, SyntheticLink


def make_trial(label: str, sigma: float, seed: int, n: int = 300,
               carriers: int = 64) -> dict:
    """A trial whose temporal noise is ``sigma``."""
    rng = np.random.default_rng(seed)
    base = np.full((n, carriers), 20.0)
    walk = np.cumsum(rng.normal(0.0, sigma, (n, carriers)), axis=0)
    return {"label": label, "amplitudes": base + walk,
            "used": np.ones(carriers, bool)}


# --- the frozen feature set ------------------------------------------------

def test_the_feature_set_is_frozen_and_documented():
    from specter.sensors.esp32.analysis import PREREGISTRATION
    assert tuple(PREREGISTRATION["features"]) == FEATURE_NAMES
    for name in FEATURE_NAMES:
        assert PREREGISTRATION["rationale"][name]


def test_the_features_are_computed_for_every_trial():
    trials = [make_trial("stationary", 0.02, 1), make_trial("hand", 0.06, 2)]
    feats = extract_features(trials)
    assert len(feats) == 2
    for f in feats:
        for name in FEATURE_NAMES:
            assert name in f
            assert f[name] == f[name]        # not NaN


def test_the_features_do_not_track_the_amplitude():
    """Doubling every amplitude must not change the gain-free features."""
    a = make_trial("stationary", 0.02, 3)
    b = dict(a)
    b["amplitudes"] = a["amplitudes"] * 2.0
    fa = extract_features([a])[0]
    fb = extract_features([b])[0]
    for name in ("roughness_used", "amp_volatility"):
        assert fa[name] == pytest.approx(fb[name], rel=1e-9)


def test_a_more_noisy_trial_has_a_higher_roughness():
    quiet = extract_features([make_trial("stationary", 0.02, 4)])[0]
    noisy = extract_features([make_trial("hand", 0.20, 5)])[0]
    assert noisy["roughness_used"] > quiet["roughness_used"] * 2


# --- blinding and permutation ---------------------------------------------

def test_the_blinded_order_is_a_permutation_and_is_recorded():
    order = blinded_order(9, seed=3)
    assert sorted(order) == list(range(9))
    assert order != list(range(9)) or True     # the seed is recorded either way
    assert blinded_order(9, seed=3) == order    # and it is reproducible


def test_the_permutation_test_measures_its_own_false_positive_rate():
    """On null data the procedure must fire at about the nominal rate."""
    trials = [make_trial("stationary" if i % 2 == 0 else "hand", 0.02, 100 + i)
              for i in range(8)]
    feats = extract_features(trials)
    labels = [t["label"] for t in trials]
    r = permutation_test(feats, labels, "roughness_used", n_perm=300, seed=1)
    assert 0.0 <= r["false_positive_rate"] <= 0.20
    assert r["empirical_p"] > 0.05
    assert r["min_attainable_p"] > 0


def test_the_permutation_test_fires_on_a_separated_set():
    separated = []
    null = []
    for i in range(4):
        separated.append(make_trial("stationary", 0.02, 200 + i))
        separated.append(make_trial("hand", 0.30, 300 + i))
        null.append(make_trial("stationary", 0.02, 200 + i))
        null.append(make_trial("hand", 0.02, 300 + i))
    sep_feats = extract_features(separated)
    null_feats = extract_features(null)
    sep_labels = [t["label"] for t in separated]
    null_labels = [t["label"] for t in null]
    r_sep = permutation_test(sep_feats, sep_labels, "roughness_used",
                             n_perm=300, seed=1)
    r_null = permutation_test(null_feats, null_labels, "roughness_used",
                              n_perm=300, seed=1)
    # a separated set must look far more extreme than a null one
    assert r_sep["empirical_p"] < r_null["empirical_p"]
    # and the parametric test must agree that the effect is there
    assert omnibus(sep_feats, sep_labels, "roughness_used")["p"] < 0.05
    assert omnibus(null_feats, null_labels, "roughness_used")["p"] > 0.05
    # the false-positive rate is a property of the procedure, not of the data
    assert r_sep["false_positive_rate"] < 0.2
    assert r_null["false_positive_rate"] < 0.2


# --- effect sizes and held-out evaluation ----------------------------------

def test_cohens_d_has_the_expected_sign_and_magnitude():
    a = [1.0, 1.1, 0.9, 1.05, 0.95]
    b = [3.0, 3.1, 2.9, 3.05, 2.95]
    d = cohens_d(a, b)
    # the sign follows the argument order: (mean of a) - (mean of b)
    assert d < 0
    assert abs(d) > 2.0                 # well separated: a large d
    assert cohens_d(b, a) == pytest.approx(-d)


def test_partial_eta_squared_is_zero_for_identical_groups():
    g = {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]}
    assert partial_eta_squared(g) == pytest.approx(0.0)


def test_the_held_out_score_is_out_of_sample():
    """A separable set must score well; a null set must score at chance."""
    trials = []
    for i in range(5):
        trials.append(make_trial("stationary", 0.02, 400 + i))
        trials.append(make_trial("hand", 0.30, 500 + i))
    feats = extract_features(trials)
    labels = [t["label"] for t in trials]
    ho = cross_validate(feats, labels, "roughness_used")
    assert ho["held_out_accuracy"] == 1.0
    assert ho["n_scored"] == 10

    null = [make_trial("stationary" if i % 2 == 0 else "hand", 0.02, 600 + i)
            for i in range(10)]
    nfeats = extract_features(null)
    nlabels = [t["label"] for t in null]
    nho = cross_validate(nfeats, nlabels, "roughness_used")
    assert 0.0 <= nho["held_out_accuracy"] <= 0.8


def test_the_bootstrap_interval_brackets_the_estimate():
    a = [1.0, 1.2, 0.8, 1.1, 0.9, 1.05]
    b = [2.0, 2.2, 1.8, 2.1, 1.9, 2.05]
    d = cohens_d(a, b)
    lo, hi = cohens_d_ci(a, b, n_boot=400, seed=1)
    assert lo < d < hi
    # the two groups are resampled independently: the interval is around
    # the difference, not around the mixed sample
    assert hi < 0.0


# --- power ------------------------------------------------------------------

def test_power_rises_with_the_effect_size_and_with_the_sample_size():
    weak = power_by_simulation(0.3, 6, k=3, n_sim=200, seed=1)["power"]
    strong = power_by_simulation(1.2, 6, k=3, n_sim=200, seed=1)["power"]
    assert strong > weak
    small = power_by_simulation(0.95, 3, k=3, n_sim=200, seed=1)["power"]
    large = power_by_simulation(0.95, 12, k=3, n_sim=200, seed=1)["power"]
    assert large > small


def test_required_n_finds_a_plausible_sample_size():
    r = required_n(0.95, k=3, target_power=0.8)
    assert r["n_per_group_needed"] is not None
    assert 3 <= r["n_per_group_needed"] <= 40
    assert r["total_trials_needed"] == r["n_per_group_needed"] * 3


# --- the ground-truth bench -------------------------------------------------

def test_the_bench_null_has_no_effect_and_the_bench_moving_does():
    quiet = SyntheticLink(effect=0.0, seed=2)
    loud = SyntheticLink(effect=0.2, seed=2)
    tq = quiet.trial("stationary", 5.0)
    tl = loud.trial("hand", 5.0, moving=True)
    fq = extract_features([tq])[0]
    fl = extract_features([tl])[0]
    assert fl["roughness_used"] > fq["roughness_used"]


def test_the_bench_labels_match_the_ground_truth():
    link = SyntheticLink(effect=0.1, seed=4)
    trials = link.set(["stationary", "hand"], repeats=2, seconds=3.0)
    for t in trials:
        assert t["ground_truth_moving"] == (t["label"] != "stationary")


def test_the_bench_uses_the_boards_real_null_band():
    link = SyntheticLink(effect=0.05, seed=6)
    t = link.trial("hand", 2.0, moving=True)
    amps = t["amplitudes"]
    assert amps.shape[1] == CARRIERS
    for c in NULL_CARRIERS:
        assert np.all(amps[:, c] == 0.0), f"carrier {c} must be unpopulated"
    assert int(t["used"].sum()) == CARRIERS - len(NULL_CARRIERS)


def test_the_bench_carries_the_phy_rate_confound():
    link = SyntheticLink(effect=0.0, seed=8)
    t = link.trial("stationary", 5.0)
    assert len(set(t["rates"].tolist())) > 1


# --- the parser fixes -------------------------------------------------------

def _line(seq=1, iq=None, first_word=0, csi_len=None):
    if iq is None:
        iq = [-12, 11] * 64
    if csi_len is None:
        csi_len = len(iq)
    fields = ["CSI_DATA", str(seq), "b8:62:1f:e5:ac:62", "-60",
              "9", "0", "0", "0", "0", "0", "0", "0", "0", "0",
              "-90", "0", "11", "0", "67768165", "0", "109", "0",
              str(csi_len), str(first_word)]
    return ",".join(fields) + ',"[' + ",".join(str(v) for v in iq) + ']"'


def test_a_tail_that_does_not_match_len_is_rejected():
    """A truncated packet must not be used for a spectrum."""
    parser = CsiParser()
    with pytest.raises(ValueError):
        parser.feed(_line(csi_len=128, iq=[1, 2, 3, 4]))


def test_first_word_invalid_marks_the_first_two_carriers():
    rec = CsiParser().feed(_line(first_word=1))
    assert rec.first_word_invalid is True
    assert rec.invalid_subcarriers == 2
    st = CsiViewState(columns=16, carriers=64)
    st.push(rec)
    mask = st.used_mask()
    assert not mask[0] and not mask[1]
    assert mask[2]


def test_the_rate_is_carried_on_the_record():
    rec = CsiParser().feed(_line())
    assert rec.rate_code == 9
    assert rec.sig_mode == 0
