"""Regression tests for every statistical defect the audit verified.

Each test is written so that it FAILS against the pre-audit implementation:

* the held-out scaler no longer sees the test fold;
* folds follow the acquisition blocks instead of the analyser's shuffle;
* ``shape_shift`` and ``change_rate`` are fitted only on the training trials;
* the permutation rebuilds the supervised feature under the permuted labels
  and stays inside the blocks;
* tied AUC is 0.5, not 1.0;
* perfectly separated constant groups are infinite separation, not zero.
"""
from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np

import specter.sensors.esp32.analysis as A
import pytest

from specter.sensors.esp32.analysis import (FEATURE_NAMES, _auc, _f_statistic,
                                            _permute_within_blocks,
                                            _within_block_assignments,
                                            _change_rate_crossfit,
                                            _trial_parts, cohens_d,
                                            cross_validate, extract_features)


def make_trial(label: str, sigma: float, seed: int, n: int = 200,
               carriers: int = 64) -> dict:
    rng = np.random.default_rng(seed)
    base = np.full((n, carriers), 20.0)
    walk = np.cumsum(rng.normal(0.0, sigma, (n, carriers)), axis=0)
    return {"label": label, "amplitudes": base + walk,
            "used": np.ones(carriers, bool)}


def _feats(values):
    return [{"roughness_used": v} for v in values]


# --- held-out scaling -------------------------------------------------------

def test_a_held_out_prediction_cannot_depend_on_another_test_sample():
    """The old code z-scored the test fold; changing one held-out value then
    changed another held-out sample's prediction."""
    feats = _feats([1.0, 1.1, 0.9, 10.0, 10.1, 9.9, 10.2, 9.8])
    labels = ["stationary"] * 3 + ["hand"] * 3 + ["stationary", "hand"]
    folds = [[6, 7]]
    before = cross_validate(feats, labels, "roughness_used", folds=folds,
                            positive="hand")
    p_before = [p for p in before["predictions"] if p["index"] == 7][0]

    changed = [dict(f) for f in feats]
    changed[6]["roughness_used"] = 1.0          # only the OTHER test sample
    after = cross_validate(changed, labels, "roughness_used", folds=folds,
                           positive="hand")
    p_after = [p for p in after["predictions"] if p["index"] == 7][0]

    assert p_before["predicted"] == p_after["predicted"], \
        "test-fold scaling leaked across held-out samples"


# --- folds follow the blocks ------------------------------------------------

def test_folds_are_the_acquisition_blocks():
    feats = _feats(list(range(6)))
    labels = ["stationary", "hand"] * 3
    blocks = [0, 0, 1, 1, 2, 2]
    r = cross_validate(feats, labels, "roughness_used", blocks=blocks)
    assert r["fold_indices"] == [[0, 1], [2, 3], [4, 5]]


# --- feature leakage --------------------------------------------------------

def test_shape_shift_reference_excludes_the_held_out_trial():
    trials = [make_trial("stationary", 0.02, 1),
              make_trial("stationary", 0.02, 2),
              make_trial("stationary", 0.02, 3)]
    fit = [0, 1]
    a = extract_features(trials, fit_idx=fit)
    # change the trial that is NOT in the fit set
    trials2 = [dict(t) for t in trials]
    trials2[2] = make_trial("stationary", 0.30, 99)
    b = extract_features(trials2, fit_idx=fit)
    for i in fit:
        assert a[i]["shape_shift"] == pytest.approx(b[i]["shape_shift"]), \
            "a held-out trial changed a training trial's shape_shift"

    # and the defect is real: a global fit does move them
    c = extract_features(trials)
    d = extract_features(trials2)
    assert c[0]["shape_shift"] != pytest.approx(d[0]["shape_shift"])


def test_change_rate_floor_excludes_held_out_stationary_trials():
    trials = [make_trial("stationary", 0.02, 11),
              make_trial("stationary", 0.02, 12),
              make_trial("stationary", 0.02, 13)]
    fit = [0, 1]
    a = extract_features(trials, fit_idx=fit)
    trials2 = [dict(t) for t in trials]
    trials2[2] = make_trial("stationary", 0.50, 98)
    b = extract_features(trials2, fit_idx=fit)
    for i in fit:
        assert a[i]["change_rate"] == pytest.approx(b[i]["change_rate"]), \
            "a held-out stationary trial set the training floor"


def test_the_permutation_rebuilds_the_supervised_feature():
    """Under a permutation the change-rate floor must be refitted."""
    trials = [make_trial("stationary", 0.02, 21),
              make_trial("stationary", 0.02, 22),
              make_trial("hand", 0.40, 23),
              make_trial("hand", 0.40, 24)]
    parts = [_trial_parts(t) for t in trials]
    labels = [t["label"] for t in trials]
    true_vals = _change_rate_crossfit(parts, labels)
    perm = ["hand", "hand", "stationary", "stationary"]
    perm_vals = _change_rate_crossfit(parts, perm)
    assert any((a != b) for a, b in zip(true_vals, perm_vals)), \
        "change_rate did not respond to the permuted labels"


# --- block-preserving permutations -----------------------------------------

def test_permutations_stay_inside_their_block():
    labels = ["stationary", "stationary", "hand", "hand",
              "stationary", "hand", "hand", "stationary"]
    blocks = [0, 0, 1, 1, 2, 2, 3, 3]
    import random
    rng = random.Random(0)
    for _ in range(200):
        p = _permute_within_blocks(labels, blocks, rng)
        for b in set(blocks):
            idx = [i for i, x in enumerate(blocks) if x == b]
            assert sorted(labels[i] for i in idx) == sorted(p[i] for i in idx)


def test_the_number_of_distinct_assignments_matches_the_design():
    labels = ["stationary", "stationary", "hand", "hand"] * 3
    blocks = [0] * 4 + [1] * 4 + [2] * 4
    # each block has 2 of each class -> C(4,2) = 6; three blocks -> 216
    assert _within_block_assignments(labels, blocks) == 216


# --- degenerate statistics --------------------------------------------------

def test_tied_scores_give_auc_one_half():
    scores = np.array([1.0, 1.0, 1.0, 1.0])
    positive = np.array([True, False, True, False])
    assert _auc(scores, positive) == pytest.approx(0.5)


def test_perfectly_separated_constant_groups_are_infinite_not_zero():
    assert cohens_d([2.0, 2.0, 2.0], [1.0, 1.0, 1.0]) == math.inf
    assert cohens_d([1.0, 1.0, 1.0], [2.0, 2.0, 2.0]) == -math.inf
    assert cohens_d([1.0, 1.0], [1.0, 1.0]) == 0.0
    assert _f_statistic({"a": [2.0, 2.0], "b": [1.0, 1.0]}) == math.inf
    assert _f_statistic({"a": [1.0, 1.0], "b": [1.0, 1.0]}) == 0.0


# --- the canonical carrier mask --------------------------------------------

def test_features_use_the_fifty_two_carrier_mask_by_default():
    """64 slots, 12 structural nulls, 52 used - one definition everywhere."""
    from specter.sensors.esp32.analysis import lltf_used_mask
    m = lltf_used_mask()
    assert m.sum() == 52
    assert not m[0]
    assert all(not m[i] for i in range(27, 38))
    # the invalid first word covers carriers 0 and 1; carrier 0 is already
    # a structural null, so the usable count falls 52 -> 51, not 52 -> 50
    m2 = lltf_used_mask(first_word_invalid=True)
    assert m2.sum() == 51
    assert not m2[0] and not m2[1]


def test_change_rate_never_uses_its_own_trial():
    """The floor must exclude trial i, not merely other trials' labels.

    A very noisy trial dominates the 99th percentile if it is allowed into
    its own reference, which drives its own change_rate down. Excluding it
    is the difference between a cross-fitted feature and a self-fitted one.
    """
    trials = [make_trial("stationary", 0.01, 31),
              make_trial("stationary", 0.01, 32),
              make_trial("stationary", 0.01, 33),
              make_trial("stationary", 0.60, 34)]
    parts = [A._trial_parts(t) for t in trials]
    labels = [t["label"] for t in trials]
    vals = A._change_rate_crossfit(parts, labels)

    all_d = np.concatenate([p["d"] for p in parts])
    thr_with_self = float(np.percentile(all_d, 99.0))
    with_self = float((parts[3]["d"] > thr_with_self).mean())
    assert vals[3] != pytest.approx(with_self)


def test_every_permutation_passes_permuted_labels_to_the_supervised_feature():
    """If the permutation reuses the observed labels, the test is invalid.

    Spying on the labels each call receives catches a 'fixed features' run
    even when the resulting p-value happens to look plausible.
    """
    trials = [make_trial("stationary", 0.02, 41),
              make_trial("stationary", 0.02, 42),
              make_trial("hand", 0.30, 43),
              make_trial("hand", 0.30, 44)]
    parts = [A._trial_parts(t) for t in trials]
    labels = [t["label"] for t in trials]
    seen = []
    original = A._change_rate_crossfit

    def spy(p, labs, stationary_label="stationary"):
        seen.append(tuple(labs))
        return original(p, labs, stationary_label)

    with patch.object(A, "_change_rate_crossfit", side_effect=spy):
        A.permutation_test_crossfit(parts, labels, None, "change_rate",
                                    n_perm=20, seed=1)
    assert len(set(seen)) > 1, "every call received the observed labels"
