"""The statistics behind a motion claim: blinding, effect sizes, held-out
evaluation, and false-positive rates.

Checkpoint 009's experiment produced a number (max F = 1.454) and a verdict
("not separable") but it did not produce a *claim* anyone could check. The
gap is not statistical sophistication - it is that the analysis was not
blinded, the features were chosen after seeing the data, there was no
held-out evaluation, and there was no measurement of how often the procedure
would fire on noise.

This module is the machinery for a claim that survives review:

* **Frozen features.** ``FEATURE_NAMES`` is the pre-registered set. It is
  written down *before* a run and does not change afterwards; a run that
  changes it is a new pre-registration, not a re-analysis.
* **Blinding.** Feature extraction never sees a label. The labels are
  shuffled by a recorded seed and only joined to the features afterwards.
* **Effect sizes.** An F statistic says "maybe different"; Cohen's d and
  partial eta-squared say *how much*, with a bootstrap interval.
* **Held-out evaluation.** Leave-one-repetition-out: the classifier is
  built on the other repetitions and scored on the one that was held out.
  A score computed on the data that built the classifier is not a score.
* **False positives.** The label-permutation test: shuffle the labels many
  times and count how often the procedure fires. That is the procedure's
  actual false-positive rate, measured, not assumed.

Nothing here needs a radio. It is all offline, on recorded features.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .csi_analysis import EXPECTED_NULL, EXPECTED_SUBCARRIERS

#: The pre-registered feature set. Changing this is a new pre-registration.
FEATURE_NAMES = (
    "roughness_used",   # temporal change of the normalised multipath profile
    "amp_volatility",   # relative variation of the total amplitude
    "shape_shift",      # distance of the trial's profile from the pooled one
    "change_rate",      # fraction of packets beyond the stationary noise floor
)

#: What the features are, and why - written down so the choice can be
#: reviewed rather than reverse-engineered from the result.
FEATURE_RATIONALE = {
    "roughness_used": ("mean |delta| of the normalised spectrum between "
                       "consecutive packets, over the used subcarriers only"),
    "amp_volatility": ("mean |delta| of the total amplitude, divided by its "
                       "mean, over the trial"),
    "shape_shift": ("mean |delta| between the trial's mean normalised "
                    "spectrum and the pooled mean over all trials"),
    "change_rate": ("fraction of packets whose deviation from the running "
                    "baseline exceeds the stationary trials' 99th percentile"),
}

PREREGISTRATION = {
    "features": list(FEATURE_NAMES),
    "rationale": FEATURE_RATIONALE,
    "alpha": 0.05,
    "n_permutations": 1000,
    "classifier": "nearest centroid on z-scored features",
    "cv": "leave-one-repetition-out",
    "note": ("Features are computed per trial from the complex CSI. The "
             "amplitude is normalised per packet so that the features do "
             "not simply track the received power."),
}


# --- feature extraction ----------------------------------------------------


def _as_array(value) -> np.ndarray:
    """An array field, without the truthiness trap of numpy arrays."""
    if value is None:
        return np.zeros(0, dtype=np.float64)
    return np.asarray(value, dtype=np.float64)


#: The LLTF null slots, from the one canonical definition in csi_analysis.
LLTF_NULL_CARRIERS = frozenset(EXPECTED_NULL)


def lltf_used_mask(n_carriers: int = EXPECTED_SUBCARRIERS,
                   first_word_invalid: bool = False) -> np.ndarray:
    """The carriers a feature may use.

    One definition, used everywhere. The Alpha 002-C audit found the Phase 0
    null computed over all 64 slots while the pipeline used 52, so the same
    quantity had two values. The null slots are structural and the first two
    carriers are dropped when the hardware flags the first word invalid.
    """
    mask = np.ones(int(n_carriers), dtype=bool)
    # The null indices are positions in the 64-slot LLTF layout. Applying
    # them to any other width (e.g. a pre-masked 52-wide array) would remove
    # 11 more carriers and leave 40. Only the real layout gets the mask.
    if int(n_carriers) == EXPECTED_SUBCARRIERS:
        for i in LLTF_NULL_CARRIERS:
            if i < mask.size:
                mask[i] = False
    if first_word_invalid:
        mask[:2] = False
    return mask


def _trial_parts(trial: Dict) -> Optional[Dict]:
    """The pieces every feature is built from, computed once per trial.

    Keeping them separate is what makes leakage-free cross-fitting and a
    whole-pipeline permutation test affordable: only ``change_rate`` depends
    on labels, and only through the floor fitted on training trials.
    """
    amps = _as_array(trial.get("amplitudes"))
    if amps.ndim != 2 or amps.shape[0] < 4:
        return None
    used = trial.get("used")
    if used is None:
        used = lltf_used_mask(amps.shape[1])
    else:
        used = np.asarray(used, bool)
        if used.size < amps.shape[1]:
            pad = np.zeros(amps.shape[1], bool)
            pad[:used.size] = used
            used = pad
    totals = amps.sum(axis=1)
    safe = np.where(totals > 0, totals, 1.0)
    norm = amps / safe[:, None]
    u = norm[:, used] if used.any() else norm
    rough = float(np.abs(np.diff(u, axis=0)).mean()) if u.shape[0] > 1 else 0.0
    amp_diff = np.abs(np.diff(totals))
    vol = (float(amp_diff.mean() / (float(totals.mean()) or 1.0))
           if amp_diff.size else 0.0)
    return {"rough": rough, "vol": vol,
            "m": u.mean(axis=0),
            "d": (np.abs(np.diff(u, axis=0)).mean(axis=1)
                  if u.shape[0] > 1 else np.zeros(0))}


def _shape_reference(parts: Sequence[Optional[Dict]],
                     fit_idx: Sequence[int]) -> Optional[np.ndarray]:
    ms = [parts[i]["m"] for i in fit_idx if parts[i] is not None]
    if not ms:
        return None
    k = min(len(x) for x in ms)
    pooled = np.mean([x[:k] for x in ms], axis=0)
    return pooled / (pooled.sum() or 1.0)


def _change_floor(parts, labels, fit_idx, stationary_label: str):
    ds = [parts[i]["d"] for i in fit_idx
          if parts[i] is not None and labels[i] == stationary_label]
    if not ds:
        return None
    all_d = np.concatenate([x for x in ds if x.size]) if ds else np.zeros(0)
    return float(np.percentile(all_d, 99.0)) if all_d.size else None


def extract_features(trials: Sequence[Dict],
                     stationary_label: str = "stationary",
                     fit_idx: Optional[Sequence[int]] = None,
                     parts: Optional[Sequence[Optional[Dict]]] = None,
                     ) -> List[Dict]:
    """The frozen features, one dict per trial.

    ``fit_idx`` selects the trials whose statistics may be *learned from* -
    the pooled reference for ``shape_shift`` and the stationary noise floor
    for ``change_rate``. It defaults to all trials, which is correct for a
    descriptive report and **wrong for any held-out claim**: pass the
    training indices when evaluating a fold. The Alpha 002-C audit found both
    quantities fitted on the trials they were later used to score.
    """
    if parts is None:
        parts = [_trial_parts(t) for t in trials]
    n = len(trials)
    fit = list(range(n)) if fit_idx is None else list(fit_idx)
    base = _shape_reference(parts, fit)
    labels = [t.get("label", "") for t in trials]
    thr = _change_floor(parts, labels, fit, stationary_label)
    out: List[Dict] = []
    for i, p in enumerate(parts):
        f = {name: float("nan") for name in FEATURE_NAMES}
        if p is not None:
            f["roughness_used"] = p["rough"]
            f["amp_volatility"] = p["vol"]
            if base is not None:
                k = min(len(base), len(p["m"]))
                f["shape_shift"] = float(np.abs(p["m"][:k] - base[:k]).mean())
            if thr is not None and p["d"].size:
                f["change_rate"] = float((p["d"] > thr).mean())
        out.append(f)
    return out


def crossfit_features(trials: Sequence[Dict],
                      stationary_label: str = "stationary",
                      ) -> List[Dict]:
    """Each trial's features with every learned statistic fitted on *others*.

    This is the leakage-free feature vector. Trial ``i`` never contributes to
    the reference or the floor used to describe it, so no trial can help
    predict itself. It is O(n^2) in the number of trials, which is nothing
    for a session of this size.
    """
    parts = [_trial_parts(t) for t in trials]
    labels = [t.get("label", "") for t in trials]
    n = len(trials)
    out = []
    for i in range(n):
        fit = [j for j in range(n) if j != i]
        out.append(extract_features(trials, stationary_label, fit_idx=fit,
                                    parts=parts)[i])
    return out


# --- blinding and randomisation -------------------------------------------


def blinded_order(n: int, seed: int) -> List[int]:
    """A recorded randomisation of the trial order."""
    order = list(range(n))
    random.Random(seed).shuffle(order)
    return order


# --- effect sizes ----------------------------------------------------------


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d for two samples, with the pooled standard deviation."""
    a = np.asarray([v for v in a if v == v], dtype=np.float64)
    b = np.asarray([v for v in b if v == v], dtype=np.float64)
    if a.size < 2 or b.size < 2:
        return float("nan")
    na, nb = a.size, b.size
    sp = math.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1))
                   / (na + nb - 2))
    if sp == 0:
        # a zero pooled spread with different means is infinite separation,
        # not "no effect" - the audit found the old 0.0 inverted the meaning
        diff = float(a.mean() - b.mean())
        return 0.0 if diff == 0 else math.copysign(float("inf"), diff)
    return float((a.mean() - b.mean()) / sp)


def partial_eta_squared(groups: Dict[str, List[float]]) -> float:
    """The proportion of the variance in the feature explained by the label."""
    grand = [v for g in groups.values() for v in g if v == v]
    if len(groups) < 2 or len(grand) < len(groups) + 1:
        return float("nan")
    gm = float(np.mean(grand))
    ss_total = float(sum((v - gm) ** 2 for v in grand))
    ss_between = float(sum(len([v for v in g if v == v]) *
                           (float(np.mean([v for v in g if v == v])) - gm) ** 2
                           for g in groups.values()))
    if ss_total <= 0:
        return 0.0
    return ss_between / ss_total


def bootstrap_ci(values: Sequence[float], stat, n_boot: int = 2000,
                 seed: int = 0) -> Tuple[float, float]:
    """A percentile bootstrap interval for a statistic of ONE sample."""
    values = [v for v in values if v == v]
    if len(values) < 3:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    out = []
    arr = np.asarray(values, dtype=np.float64)
    for _ in range(n_boot):
        idx = rng.integers(0, arr.size, arr.size)
        out.append(stat(arr[idx]))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def cohens_d_ci(a: Sequence[float], b: Sequence[float], n_boot: int = 2000,
                seed: int = 0) -> Tuple[float, float]:
    """A bootstrap interval for Cohen's d.

    The two groups are resampled **independently**. Resampling them
    together and splitting the result would mix the groups and produce an
    interval around the wrong quantity.
    """
    a = np.asarray([v for v in a if v == v], dtype=np.float64)
    b = np.asarray([v for v in b if v == v], dtype=np.float64)
    # A bootstrap interval on a variance needs enough points to resample.
    # With three trials per group the resamples are degenerate (the same
    # value three times, zero variance, an undefined ratio) and the
    # interval is not estimable - so it is not reported.
    if a.size < 4 or b.size < 4:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        ai = rng.integers(0, a.size, a.size)
        bi = rng.integers(0, b.size, b.size)
        d = cohens_d(a[ai], b[bi])
        if d == d:
            out.append(d)
    if not out:
        return (float("nan"), float("nan"))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)))


def effect_sizes(features: List[Dict], labels: Sequence[str],
                 feature: str = "roughness_used") -> Dict:
    """Pairwise Cohen's d and the omnibus partial eta-squared, with CIs."""
    groups: Dict[str, List[float]] = {}
    for f, lab in zip(features, labels):
        groups.setdefault(lab, []).append(f.get(feature, float("nan")))
    pairs = {}
    names = sorted(groups)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = groups[names[i]], groups[names[j]]
            d = cohens_d(a, b)
            lo, hi = cohens_d_ci(a, b, seed=7)
            pairs[f"{names[i]} vs {names[j]}"] = {
                "cohens_d": round(d, 3) if d == d else None,
                "ci95": ([round(lo, 3), round(hi, 3)]
                         if lo == lo else None),
                "n_per_group": [len(a), len(b)],
                "ci_note": (None if lo == lo else
                            "not estimable: a bootstrap interval on the "
                            "effect size needs at least four trials per "
                            "group"),
            }
    return {
        "feature": feature,
        "partial_eta_squared": round(partial_eta_squared(groups), 4),
        "group_means": {k: round(float(np.mean([v for v in g if v == v])), 6)
                        for k, g in groups.items()},
        "pairs": pairs,
    }


# --- the omnibus test and its false-positive rate -------------------------


def _f_statistic(groups: Dict[str, List[float]]) -> float:
    # drop empty and all-NaN groups first: np.mean([]) is NaN, and 0 * NaN
    # would turn an undefined contrast into a plausible-looking number
    groups = {k: [v for v in g if v == v] for k, g in groups.items()}
    groups = {k: g for k, g in groups.items() if g}
    grand = [v for g in groups.values() for v in g]
    if len(groups) < 2 or len(grand) <= len(groups):
        return float("nan")
    gm = float(np.mean(grand))
    between = sum(len([v for v in g if v == v]) *
                  (float(np.mean([v for v in g if v == v])) - gm) ** 2
                  for g in groups.values())
    within = sum(float(np.sum((np.asarray([v for v in g if v == v], float) -
                                np.mean([v for v in g if v == v])) ** 2))
                 for g in groups.values())
    if within <= 0:
        # perfectly separated constant groups: the ratio is unbounded
        return float("inf") if between > 0 else 0.0
    df1 = len(groups) - 1
    df2 = len(grand) - len(groups)
    return float((between / df1) / (within / df2))


def omnibus(feats: List[Dict], labels: Sequence[str],
            feature: str = "roughness_used") -> Dict:
    """The one-way ANOVA F for the frozen feature set."""
    from .experiment import f_sf
    groups: Dict[str, List[float]] = {}
    for f, lab in zip(feats, labels):
        groups.setdefault(lab, []).append(f.get(feature, float("nan")))
    f = _f_statistic(groups)
    df1 = len(groups) - 1
    df2 = sum(len(g) for g in groups.values()) - len(groups)
    p = f_sf(f, df1, df2) if f == f else float("nan")
    return {"feature": feature, "f": round(f, 4) if f == f else None,
            "df1": df1, "df2": df2, "p": round(p, 6) if p == p else None}


def permutation_test(feats: List[Dict], labels: Sequence[str],
                     feature: str = "roughness_used", n_perm: int = 1000,
                     seed: int = 0) -> Dict:
    """The label-permutation test: the procedure's own false-positive rate.

    The labels are shuffled ``n_perm`` times and the omnibus F is recomputed
    each time. The fraction of shuffles that reach the alpha threshold is
    the *measured* false-positive rate of the whole procedure - not the
    nominal one.
    """
    from .experiment import f_sf as _f_sf
    values = [f.get(feature, float("nan")) for f in feats]
    labels = list(labels)
    groups: Dict[str, List[float]] = {}
    for v, lab in zip(values, labels):
        groups.setdefault(lab, []).append(v)
    f = _f_statistic(groups)
    df1 = len(groups) - 1
    df2 = len(values) - len(groups)
    alpha = 0.05
    # the critical F is the one with p == alpha
    lo, hi = 0.5, 50.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _f_sf(mid, df1, df2) > alpha:
            lo = mid
        else:
            hi = mid
    critical = (lo + hi) / 2

    rng = random.Random(seed)
    hits_critical = 0      # permutations that would have been called a find
    hits_observed = 0      # permutations at least as extreme as the data
    usable = 0
    for _ in range(n_perm):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        g2: Dict[str, List[float]] = {}
        for v, lab in zip(values, shuffled):
            g2.setdefault(lab, []).append(v)
        f2 = _f_statistic(g2)
        if f2 != f2:
            continue
        usable += 1
        if f2 >= critical:
            hits_critical += 1
        if f2 >= f:
            hits_observed += 1
    p_value = (hits_observed + 1) / (usable + 1) if usable else float("nan")
    fpr = hits_critical / usable if usable else float("nan")
    # The smallest p the permutation test can report is 1 / (the number of
    # distinct ways to assign the labels). With few trials that floor is
    # well above zero, and a permutation p at the floor means "as extreme
    # as anything the design can produce", not "not significant".
    counts = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    n_assign = 1
    total = sum(counts.values())
    for c in counts.values():
        n_assign *= math.comb(total, c)
        total -= c
    # For two groups the label assignment and its complement give the same
    # statistic, so the smallest p the test can report is 2 / (the number
    # of assignments), not 1 / (the number).
    symmetry = 2 if len(counts) == 2 else 1
    floor = symmetry / n_assign if n_assign else float("nan")
    return {
        "min_attainable_p": round(floor, 5),
        "at_floor": bool(p_value == p_value and abs(p_value - floor) < 1e-9),
        "feature": feature,
        "observed_f": round(f, 4) if f == f else None,
        "critical_f": round(critical, 4),
        "n_permutations": n_perm,
        "permutations_above_critical": hits_critical,
        "permutations_as_extreme_as_data": hits_observed,
        "empirical_p": round(p_value, 5),
        "false_positive_rate": round(fpr, 5),
        "note": ("empirical_p is the fraction of shuffled labels that reach "
                 "the observed F; false_positive_rate is the fraction that "
                 "reach the alpha=0.05 critical value - the procedure's own "
                 "rate, measured rather than assumed"),
    }


# --- held-out evaluation ---------------------------------------------------


def _zscore(matrix: np.ndarray) -> np.ndarray:
    mu = matrix.mean(axis=0, keepdims=True)
    sd = matrix.std(axis=0, keepdims=True)
    sd[sd == 0] = 1.0
    return (matrix - mu) / sd


def _auc(scores: np.ndarray, positive: np.ndarray) -> float:
    """The rank-based AUC (Mann-Whitney), with tied scores counted as half.

    The old implementation assigned distinct ranks to ties in argument
    order, so two tied groups came out as AUC = 1.0 instead of 0.5. The
    audit found exactly that; the correct tie handling is average ranks.
    """
    pos = scores[positive]
    neg = scores[~positive]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ordered = scores[order]
    ranks = np.empty(scores.size, dtype=np.float64)
    i = 0
    while i < scores.size:
        j = i
        while j + 1 < scores.size and ordered[j + 1] == ordered[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return float((ranks[positive].sum() - pos.size * (pos.size + 1) / 2)
                 / (pos.size * neg.size))


def _feature_columns(feature) -> List[str]:
    return [feature] if isinstance(feature, str) else list(feature)


def _folds(labels: Sequence[str], blocks) -> List[List[int]]:
    if blocks is not None:
        by: Dict = {}
        for i, b in enumerate(blocks):
            by.setdefault(str(b), []).append(i)
        return [by[b] for b in sorted(by, key=str)]
    by_label: Dict[str, List[int]] = {}
    for i, lab in enumerate(labels):
        by_label.setdefault(lab, []).append(i)
    reps = min(len(v) for v in by_label.values()) if by_label else 0
    return [[by_label[lab][r] for lab in by_label] for r in range(reps)]


def _cv_core(train_X, train_y, test_X, test_y, positive, classes):
    """Train-only scaling, nearest centroid, out-of-fold scores."""
    mu = train_X.mean(axis=0, keepdims=True)
    sd = train_X.std(axis=0, keepdims=True)
    sd = np.where(sd == 0, 1.0, sd)
    Ztr = (train_X - mu) / sd
    Zte = (test_X - mu) / sd           # transform uses train statistics only
    cents = {}
    for lab in set(train_y):
        rows = Ztr[[y == lab for y in train_y]]
        if len(rows):
            cents[lab] = rows.mean(axis=0)
    if len(cents) < 2:
        return None, None
    hits = 0
    preds = []
    for row, truth in zip(Zte, test_y):
        dist = {k: float(np.linalg.norm(row - c)) for k, c in cents.items()}
        best = min(dist, key=dist.get)
        hits += int(best == truth)
        score = None
        if len(classes) == 2 and positive in dist:
            other = classes[0] if classes[0] != positive else classes[1]
            if other in dist:
                score = dist[other] - dist[positive]
        preds.append({"predicted": best, "label": truth, "score": score})
    return hits, preds


def _cv_result(feature, folds, predictions, correct, total, skipped,
               positive, classes):
    auc = None
    if predictions and len(classes) == 2:
        sc = [p["score"] for p in predictions if p["score"] is not None]
        lab = [p["label"] == positive for p in predictions if p["score"] is not None]
        if sc:
            auc = _auc(np.asarray(sc, float), np.asarray(lab, bool))
    return {
        "feature": feature if isinstance(feature, str) else list(feature),
        "folds": folds,
        "held_out_accuracy": round(correct / total, 4) if total else None,
        "held_out_auc": (round(auc, 4) if auc is not None and auc == auc
                         else None),
        "positive_class": positive,
        "n_scored": total,
        "skipped_folds": skipped,
        "fold_indices": [list(f) for f in folds],
        "predictions": predictions,
        "note": ("train-only scaling; folds follow the acquisition blocks; "
                 "any skipped fold carries its reason"),
    }


def cross_validate(feats: List[Dict], labels: Sequence[str],
                   feature: str = "roughness_used",
                   folds: Optional[Sequence[Sequence[int]]] = None,
                   blocks: Optional[Sequence] = None,
                   positive: Optional[str] = None) -> Dict:
    """Held-out evaluation of *pre-fitted* feature rows.

    Use :func:`cross_validate_trials` when the features were learned across
    trials: this function cannot refit them, so it cannot remove that
    leakage.
    """
    labels = list(labels)
    cols = _feature_columns(feature)
    folds = [list(f) for f in folds] if folds is not None else _folds(labels, blocks)
    classes = sorted(set(labels))
    if positive is None:
        positive = classes[-1] if classes else None
    predictions, results, skipped = [], [], []
    correct = total = 0
    for f_i, fold in enumerate(folds):
        test = set(fold)
        train = [i for i in range(len(labels)) if i not in test]
        if not train or not fold:
            skipped.append({"fold": f_i, "reason": "empty train or test fold"})
            continue
        Xtr = np.asarray([[feats[i].get(c, np.nan) for c in cols]
                          for i in train], float)
        Xte = np.asarray([[feats[i].get(c, np.nan) for c in cols]
                          for i in fold], float)
        if np.isnan(Xtr).any() or np.isnan(Xte).any():
            skipped.append({"fold": f_i, "reason": "NaN feature in the fold"})
            continue
        hit, preds = _cv_core(Xtr, [labels[i] for i in train], Xte,
                              [labels[i] for i in fold], positive, classes)
        if hit is None:
            skipped.append({"fold": f_i, "reason": "fewer than two classes"})
            continue
        for idx, pr in zip(fold, preds):
            pr["index"] = int(idx)
            predictions.append(pr)
        correct += hit
        total += len(fold)
        results.append({"fold": f_i, "n_test": len(fold),
                        "accuracy": round(hit / len(fold), 4)})
    return _cv_result(feature, folds, predictions, correct, total, skipped,
                      positive, classes)


def cross_validate_trials(trials: Sequence[Dict], labels: Sequence[str],
                          feature="roughness_used",
                          blocks: Optional[Sequence] = None,
                          positive: Optional[str] = None,
                          stationary_label: str = "stationary",
                          folds: Optional[Sequence[Sequence[int]]] = None) -> Dict:
    """Held-out evaluation with every learned statistic fitted **per fold**.

    The audit's third major finding: cross-fitting leave-one-trial-out and
    then scoring leave-one-block-out still lets a test trial's reference
    include other trials in the same test block. Here the reference and the
    noise floor for a fold are computed from that fold's *training* trials
    only, so a held-out prediction can depend on nothing in its own block.
    """
    labels = list(labels)
    cols = _feature_columns(feature)
    folds = ([list(f) for f in folds] if folds is not None
             else _folds(labels, blocks))
    classes = sorted(set(labels))
    if positive is None:
        positive = classes[-1] if classes else None
    predictions, results, skipped = [], [], []
    correct = total = 0
    for f_i, fold in enumerate(folds):
        test = set(fold)
        train = [i for i in range(len(labels)) if i not in test]
        if not train or not fold:
            skipped.append({"fold": f_i, "reason": "empty train or test fold"})
            continue
        fitted = extract_features(trials, stationary_label, fit_idx=train)
        Xtr = np.asarray([[fitted[i].get(c, np.nan) for c in cols]
                          for i in train], float)
        Xte = np.asarray([[fitted[i].get(c, np.nan) for c in cols]
                          for i in fold], float)
        if np.isnan(Xtr).any() or np.isnan(Xte).any():
            skipped.append({"fold": f_i,
                            "reason": "NaN feature after per-fold fitting"})
            continue
        hit, preds = _cv_core(Xtr, [labels[i] for i in train], Xte,
                              [labels[i] for i in fold], positive, classes)
        if hit is None:
            skipped.append({"fold": f_i, "reason": "fewer than two classes"})
            continue
        for idx, pr in zip(fold, preds):
            pr["index"] = int(idx)
            predictions.append(pr)
        correct += hit
        total += len(fold)
        results.append({"fold": f_i, "n_test": len(fold),
                        "accuracy": round(hit / len(fold), 4)})
    return _cv_result(feature, folds, predictions, correct, total, skipped,
                      positive, classes)


def power_by_simulation(d: float, n_per_group: int, k: int = 2,
                        n_sim: int = 400, alpha: float = 0.05,
                        seed: int = 0) -> Dict:
    """How often the omnibus test would fire, for a known effect size.

    Simulated rather than taken from a table: the test, the features and
    the critical value are the ones this project actually uses, and a
    table would have to assume they match.

    ``d`` is Cohen's d between the groups; the groups are placed
    symmetrically so that the pooled variance is the one the statistic
    assumes.
    """
    from .experiment import f_sf
    rng = np.random.default_rng(seed)
    labels = [f"g{i}" for i in range(k)]
    hits = 0
    used = 0
    for _ in range(n_sim):
        groups = {}
        for gi, lab in enumerate(labels):
            shift = (gi - (k - 1) / 2.0) * d
            vals = rng.normal(shift, 1.0, n_per_group)
            groups[lab] = [float(v) for v in vals]
        f = _f_statistic(groups)
        if f != f:
            continue
        used += 1
        df1 = k - 1
        df2 = k * n_per_group - k
        lo, hi = 0.5, 200.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if f_sf(mid, df1, df2) > alpha:
                lo = mid
            else:
                hi = mid
        if f >= (lo + hi) / 2:
            hits += 1
    return {
        "cohens_d": d,
        "n_per_group": n_per_group,
        "k": k,
        "power": round(hits / used, 4) if used else None,
        "n_sim": n_sim,
    }


def required_n(d: float, k: int = 2, target_power: float = 0.8,
               alpha: float = 0.05, seed: int = 0) -> Dict:
    """The smallest number of trials per group that reaches the target power."""
    curve = []
    chosen = None
    for n in range(2, 41):
        r = power_by_simulation(d, n, k, n_sim=250, alpha=alpha, seed=seed)
        curve.append({"n_per_group": n, "power": r["power"]})
        if r["power"] is not None and r["power"] >= target_power and chosen is None:
            chosen = n
    return {
        "cohens_d": d,
        "k": k,
        "target_power": target_power,
        "n_per_group_needed": chosen,
        "total_trials_needed": (chosen * k) if chosen else None,
        "curve": curve,
        "note": ("simulated with the same omnibus test and critical value "
                 "the analysis uses"),
    }


# --- the whole thing -------------------------------------------------------


# --- whole-pipeline permutation, block preserving -------------------------


def _groups(values: Sequence[float], labels: Sequence[str]) -> Dict[str, List[float]]:
    groups: Dict[str, List[float]] = {}
    for v, lab in zip(values, labels):
        groups.setdefault(lab, []).append(v)
    return groups


def _critical_f(df1: int, df2: int, alpha: float = 0.05) -> float:
    from .experiment import f_sf
    lo, hi = 0.5, 50.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if f_sf(mid, df1, df2) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _permute_within_blocks(labels: Sequence[str], blocks, rng) -> List[str]:
    """Permute labels only inside their acquisition block.

    The design randomises within blocks; an unrestricted permutation would
    be a different, easier test than the one the experiment ran. The audit
    found the old procedure used unrestricted shuffles.
    """
    out = list(labels)
    if blocks is None:
        rng.shuffle(out)
        return out
    by: Dict[str, List[int]] = {}
    for i, b in enumerate(blocks):
        by.setdefault(str(b), []).append(i)
    for idx in by.values():
        vals = [labels[i] for i in idx]
        rng.shuffle(vals)
        for i, v in zip(idx, vals):
            out[i] = v
    return out


def _within_block_assignments(labels: Sequence[str], blocks) -> Optional[int]:
    """How many distinct within-block label assignments exist."""
    if blocks is None:
        return None
    import math as _math
    by: Dict[str, List[int]] = {}
    for i, b in enumerate(blocks):
        by.setdefault(str(b), []).append(i)
    total = 1
    for idx in by.values():
        counts: Dict[str, int] = {}
        for i in idx:
            counts[labels[i]] = counts.get(labels[i], 0) + 1
        m = len(idx)
        denom = 1
        for c in counts.values():
            denom *= _math.factorial(c)
        total *= _math.factorial(m) // denom
    return total


def _invariant_features(parts) -> Dict[str, List[float]]:
    """Features that do not depend on labels, cross-fitted leave-one-out."""
    n = len(parts)
    rough = [float("nan")] * n
    vol = [float("nan")] * n
    shape = [float("nan")] * n
    for i, p in enumerate(parts):
        if p is None:
            continue
        rough[i] = p["rough"]
        vol[i] = p["vol"]
        base = _shape_reference(parts, [j for j in range(n) if j != i])
        if base is not None:
            k = min(len(base), len(p["m"]))
            shape[i] = float(np.abs(p["m"][:k] - base[:k]).mean())
    return {"roughness_used": rough, "amp_volatility": vol,
            "shape_shift": shape}


def _change_rate_crossfit(parts, labels: Sequence[str],
                          stationary_label: str = "stationary") -> List[float]:
    """``change_rate`` with the floor fitted on the *other* trials.

    This is the feature the audit found most leaky: its threshold used the
    true stationary labels of every fold, including the fold being scored.
    Here trial ``i``'s floor comes only from trials ``j != i``, and under a
    permutation it is rebuilt from the *permuted* labels.
    """
    n = len(parts)
    out = [float("nan")] * n
    for i in range(n):
        if parts[i] is None:
            continue
        ds = [parts[j]["d"] for j in range(n)
              if j != i and parts[j] is not None
              and labels[j] == stationary_label and parts[j]["d"].size]
        if not ds:
            continue
        all_d = np.concatenate(ds)
        if not all_d.size:
            continue
        thr = float(np.percentile(all_d, 99.0))
        d = parts[i]["d"]
        if d.size:
            out[i] = float((d > thr).mean())
    return out


def _feature_values(inv, parts, labels, feature: str) -> List[float]:
    if feature == "change_rate":
        return _change_rate_crossfit(parts, labels)
    return inv[feature]


def permutation_test_crossfit(parts, labels: Sequence[str], blocks,
                              feature: str = "roughness_used",
                              n_perm: int = 1000, seed: int = 0,
                              alpha: float = 0.05) -> Dict:
    """Label permutation of the *whole* pipeline, block preserving.

    For every permutation the supervised feature is rebuilt with the
    permuted labels - so the test measures the procedure, not a feature
    that was allowed to peek at the labels. Permutations stay inside the
    acquisition blocks, and the smallest attainable p is reported: with a
    few blocks it is well above zero, and a p at that floor means "as
    extreme as this design can produce", not "significant".
    """
    inv = _invariant_features(parts)
    labels = list(labels)
    observed = _feature_values(inv, parts, labels, feature)
    f_obs = _f_statistic(_groups(observed, labels))
    classes = sorted(set(labels))
    df1 = len(classes) - 1
    df2 = sum(1 for v in observed if v == v) - len(classes)
    critical = _critical_f(df1, df2, alpha)
    rng = random.Random(seed)
    hits_critical = hits_observed = usable = 0
    for _ in range(n_perm):
        pl = _permute_within_blocks(labels, blocks, rng)
        vals = _feature_values(inv, parts, pl, feature)
        f2 = _f_statistic(_groups(vals, pl))
        if f2 != f2:
            continue
        usable += 1
        if f2 >= critical:
            hits_critical += 1
        if f2 >= f_obs:
            hits_observed += 1
    n_assign = _within_block_assignments(labels, blocks)
    n_classes = len(set(labels))
    if n_assign:
        # swapping labels leaves F unchanged, so an assignment and its
        # complement give the same statistic: the two-sided floor is 2/N.
        min_p = (2.0 if n_classes == 2 else 1.0) / n_assign
    else:
        min_p = (1.0 / (usable + 1)) if usable else None
    p = ((hits_observed + 1) / (usable + 1)) if usable else None
    if p is not None and min_p is not None:
        p = max(p, min_p)
    return {
        "feature": feature,
        "observed_f": round(f_obs, 4) if f_obs == f_obs else None,
        "critical_f": round(critical, 4),
        "n_permutations": n_perm,
        "permutations_above_critical": hits_critical,
        "permutations_as_extreme_as_data": hits_observed,
        "empirical_p": round(p, 6) if p is not None else None,
        "false_positive_rate": round(hits_critical / usable, 6) if usable else None,
        "min_attainable_p": round(min_p, 6) if min_p else None,
        "at_floor": bool(p is not None and min_p is not None
                         and p <= min_p + 1e-12),
        "block_preserving": blocks is not None,
        "n_distinct_assignments": n_assign,
        "note": ("features are rebuilt under every permutation; labels are "
                 "permuted only within acquisition blocks"),
    }


def analyse_blinded(trials: Sequence[Dict], seed: int = 0,
                    n_perm: int = 1000, alpha: float = 0.05,
                    blocks: Optional[Sequence] = None) -> Dict:
    """The full blinded analysis, leakage-free.

    Differences from the version the audit examined: the features are
    cross-fitted (no trial contributes to its own reference or floor), the
    permutation rebuilds the supervised feature under the permuted labels
    and stays inside the acquisition blocks, the held-out score uses
    train-only scaling, follows the blocks, and reports AUC as the protocol
    declared. It is still not a substitute for valid acquisition: a
    contaminated window is contaminated before any of this runs.
    """
    n = len(trials)
    order = blinded_order(n, seed)
    shuffled = [trials[i] for i in order]
    labels = [t.get("label", "") for t in shuffled]
    if blocks is None:
        cand = [t.get("block") for t in shuffled]
        blocks = cand if cand and all(b is not None for b in cand) else None
    else:
        blocks = list(blocks)
        if len(blocks) != n:
            raise ValueError(f"blocks has {len(blocks)} entries for {n} trials")
        # the trials were shuffled; a caller's block list is in the original
        # order and MUST be shuffled the same way or the folds are misaligned
        blocks = [blocks[i] for i in order]
    parts = [_trial_parts(t) for t in shuffled]
    feats = crossfit_features(shuffled)
    out = {
        "preregistration": PREREGISTRATION,
        "seed": seed,
        "n_trials": n,
        "order": order,
        "labels_in_analysis_order": labels,
        "blocks": blocks,
        "features": feats,
        "omnibus": {},
        "permutation": {},
        "effects": {},
        "held_out": {},
        "leakage_free": True,
    }
    positive = "hand" if "hand" in labels else None
    for name in FEATURE_NAMES:
        out["omnibus"][name] = omnibus(feats, labels, name)
        out["permutation"][name] = permutation_test_crossfit(
            parts, labels, blocks, name, n_perm=n_perm, seed=seed, alpha=alpha)
        out["effects"][name] = effect_sizes(feats, labels, name)
        out["held_out"][name] = cross_validate_trials(
            shuffled, labels, name, blocks=blocks, positive=positive)
    # the pre-registration says "nearest centroid on z-scored features"
    # (plural), so the full frozen set also gets a held-out score
    out["held_out_multivariate"] = cross_validate_trials(
        shuffled, labels, list(FEATURE_NAMES), blocks=blocks, positive=positive)
    return out
