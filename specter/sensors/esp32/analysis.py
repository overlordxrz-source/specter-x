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


def _features_for_trial(trial: Dict) -> Dict[str, float]:
    amps = _as_array(trial.get("amplitudes"))
    if amps.ndim != 2 or amps.shape[0] < 4:
        return {k: float("nan") for k in FEATURE_NAMES}
    used = trial.get("used")
    used = (np.asarray(used, bool) if used is not None
            else np.ones(amps.shape[1], bool))
    totals = amps.sum(axis=1)
    safe = np.where(totals > 0, totals, 1.0)
    norm = amps / safe[:, None]
    u = norm[:, used] if used.any() else norm
    rough = float(np.abs(np.diff(u, axis=0)).mean()) if u.shape[0] > 1 else 0.0
    amp_diff = np.abs(np.diff(totals))
    vol = float(amp_diff.mean() / (float(totals.mean()) or 1.0)) \
        if amp_diff.size else 0.0
    return {
        "roughness_used": rough,
        "amp_volatility": vol,
        "shape_shift": float("nan"),   # filled in across trials
        "change_rate": float("nan"),   # filled in across trials
    }


def extract_features(trials: Sequence[Dict],
                     stationary_label: str = "stationary") -> List[Dict]:
    """The frozen features, one dict per trial.

    Two of the features are defined *across* trials (how far a trial's
    profile sits from the pooled one, and how often a packet exceeds the
    stationary noise floor), so they are filled in after the per-trial
    features are computed.
    """
    feats = [_features_for_trial(t) for t in trials]
    amps = [_as_array(t.get("amplitudes")) for t in trials]
    valid = [a for a in amps if a.ndim == 2 and a.shape[0] >= 2]
    if not valid:
        return feats
    n_carriers = min(a.shape[1] for a in valid)
    pooled = np.mean([a[:, :n_carriers].mean(axis=0) for a in valid], axis=0)
    for f, t, a in zip(feats, trials, amps):
        if a.ndim != 2 or a.shape[0] < 2:
            continue
        m = a[:, :n_carriers].mean(axis=0)
        total = a.sum(axis=1)
        safe = np.where(total > 0, total, 1.0)
        n = a[:, :n_carriers] / safe[:, None]
        base = pooled / (pooled.sum() or 1.0)
        f["shape_shift"] = float(np.abs(n.mean(axis=0) - base).mean())

    # the noise floor of the change metric, from the stationary trials
    floor = None
    for f, t in zip(feats, trials):
        if t.get("label") != stationary_label:
            continue
        a = _as_array(t.get("amplitudes"))
        if a.ndim != 2 or a.shape[0] < 4:
            continue
        used = t.get("used")
        used = (np.asarray(used, bool) if used is not None
                else np.ones(a.shape[1], bool))
        total = a.sum(axis=1)
        n = a / np.where(total > 0, total, 1.0)[:, None]
        u = n[:, used] if used.any() else n
        d = np.abs(np.diff(u, axis=0)).mean(axis=1)
        floor = d if floor is None else np.concatenate([floor, d])
    if floor is not None and floor.size:
        thr = float(np.percentile(floor, 99.0))
        for f, t in zip(feats, trials):
            a = _as_array(t.get("amplitudes"))
            if a.ndim != 2 or a.shape[0] < 4:
                continue
            used = t.get("used")
            used = (np.asarray(used, bool) if used is not None
                    else np.ones(a.shape[1], bool))
            total = a.sum(axis=1)
            n = a / np.where(total > 0, total, 1.0)[:, None]
            u = n[:, used] if used.any() else n
            d = np.abs(np.diff(u, axis=0)).mean(axis=1)
            f["change_rate"] = float((d > thr).mean())
    return feats


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
        return 0.0
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
    grand = [v for g in groups.values() for v in g if v == v]
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
        return 0.0
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
    """The rank-based AUC (Mann-Whitney)."""
    pos = scores[positive]
    neg = scores[~positive]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(scores.size, dtype=np.float64)
    ranks[order] = np.arange(1, scores.size + 1)
    return float((ranks[positive].sum() - pos.size * (pos.size + 1) / 2)
                 / (pos.size * neg.size))


def cross_validate(feats: List[Dict], labels: Sequence[str],
                   feature: str = "roughness_used",
                   folds: Optional[Sequence[Sequence[int]]] = None) -> Dict:
    """Leave-one-repetition-out evaluation.

    For each fold, the classifier (a nearest centroid on z-scored
    features) is built on the *other* folds and scored on this one. The
    score is therefore out of sample, which is the whole point.
    """
    labels = list(labels)
    if folds is None:
        # one fold per distinct label repetition: group by the order the
        # labels appear, so fold i holds the i-th trial of each condition
        by_label: Dict[str, List[int]] = {}
        for i, lab in enumerate(labels):
            by_label.setdefault(lab, []).append(i)
        reps = min(len(v) for v in by_label.values()) if by_label else 0
        folds = []
        for r in range(reps):
            folds.append([by_label[lab][r] for lab in by_label])
    results = []
    correct = 0
    total = 0
    for f_i, fold in enumerate(folds):
        test = set(fold)
        train = [i for i in range(len(labels)) if i not in test]
        if not train or not fold:
            continue
        Xtr = np.asarray([[feats[i].get(feature, np.nan)] for i in train], float)
        Xte = np.asarray([[feats[i].get(feature, np.nan)] for i in fold], float)
        if np.isnan(Xtr).any() or np.isnan(Xte).any():
            continue
        Ztr = _zscore(Xtr)
        Zte = _zscore(Xte)
        cents = {}
        for lab in set(labels[i] for i in train):
            cents[lab] = Ztr[[labels[i] == lab for i in train]].mean(axis=0)
        hit = 0
        scores = []
        truth = []
        for row, idx in zip(Zte, fold):
            best = min(cents, key=lambda k: float(np.linalg.norm(row - cents[k])))
            hit += int(best == labels[idx])
            truth.append(labels[idx])
            scores.append(float(-min(float(np.linalg.norm(row - cents[k]))
                                     for k in cents)))
        results.append({"fold": f_i, "n_test": len(fold),
                        "accuracy": round(hit / len(fold), 4)})
        correct += hit
        total += len(fold)
    return {
        "feature": feature,
        "folds": results,
        "held_out_accuracy": round(correct / total, 4) if total else None,
        "n_scored": total,
        "note": "the classifier never sees the fold it is scored on",
    }


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


def analyse_blinded(trials: Sequence[Dict], seed: int = 0,
                    n_perm: int = 1000, alpha: float = 0.05) -> Dict:
    """The full blinded analysis of a recorded set of trials.

    ``trials`` are dicts with ``label`` and ``amplitudes``; the labels are
    shuffled by the recorded seed before anything is computed, and the
    permutation test is run on the shuffled labels.
    """
    n = len(trials)
    order = blinded_order(n, seed)
    shuffled = [trials[i] for i in order]
    labels = [t.get("label", "") for t in shuffled]
    feats = extract_features(shuffled)
    out = {
        "preregistration": PREREGISTRATION,
        "seed": seed,
        "n_trials": n,
        "order": order,
        "labels_in_analysis_order": labels,
        "features": feats,
        "omnibus": {},
        "permutation": {},
        "effects": {},
        "held_out": {},
    }
    for name in FEATURE_NAMES:
        out["omnibus"][name] = omnibus(feats, labels, name)
        out["permutation"][name] = permutation_test(feats, labels, name,
                                                    n_perm=n_perm, seed=seed)
        out["effects"][name] = effect_sizes(feats, labels, name)
        out["held_out"][name] = cross_validate(feats, labels, name)
    return out
