"""Alpha 003 offline presence/occupancy analysis.

This module is deliberately **not** a presence detector and does not claim
that anyone is present. It provides the offline machinery the preregistered
Alpha 003 experiment will use:

* attach raw IQ to recorded samples (the Alpha acquisition already preserves
  the raw CSI stream; the trial JSON keeps amplitudes);
* compute amplitude, differential-phase and RSSI features per trial;
* evaluate fixed classifiers with **leave-one-session-out** folds;
* report balanced accuracy, per-class recall, empty false-positive rate,
  bootstrap intervals and a label-permutation null.

The phase path uses *differential phase between adjacent used subcarriers*,
not absolute phase. Commodity ESP32 phase has a per-packet common offset
(CFO), a linear sampling slope (SFO) and packet-boundary jitter; absolute
phase is not a distance measurement. Differential phase removes the common
offset; temporal changes in the differential phase are the exploratory
quantity.

No file here changes the Alpha 002-C analysis or its replication protocol.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

CONDITIONS = ("empty", "stationary", "moving")
PAYLOAD_MIN_SIG_LEN = 33
ALPHA003_TRIAL_S = 30.0
ALPHA003_MIN_PAYLOAD = 270       # 9 payload frames/s over 30 s
ALPHA003_TRIAL_TOLERANCE_S = 0.5
ALPHA003_MAX_GAP_S = 0.5
ALPHA003_MAX_UNCERTAINTY_S = 0.10

#: The feature set under test. ``profile_distance`` needs an empty reference
#: and is filled per evaluation fold; it is NaN when no reference exists.
FEATURES = (
    "roughness_used",
    "amp_volatility",
    "phase_roughness",
    "phase_std",
    "phase_resp_ratio",
    "profile_distance",
    "rssi_mean",
)
PHASE_FEATURES = ("phase_roughness", "phase_std", "phase_resp_ratio")

FEATURE_SETS = {
    "all": FEATURES,
    "no_rssi": tuple(f for f in FEATURES if f != "rssi_mean"),
    "amplitude_only": ("roughness_used", "amp_volatility",
                       "profile_distance"),
    "phase_only": PHASE_FEATURES,
    "rssi_only": ("rssi_mean",),
}

EXPECTED_NULL = frozenset((0, *range(27, 38)))


# --- IQ / phase ------------------------------------------------------------

def used_mask(width: int, first_word_invalid: bool = False) -> np.ndarray:
    """Used LLTF carriers. Only the real 64-slot layout is masked by index."""
    mask = np.ones(int(width), dtype=bool)
    if int(width) == 64:
        for i in EXPECTED_NULL:
            if i < mask.size:
                mask[i] = False
    if first_word_invalid:
        mask[:2] = False
    return mask


def complex_from_iq(iq: Sequence[Any]) -> np.ndarray:
    """ESP32 IQ pairs are (imag, real); build ``real + 1j*imag``.

    Also accepts an already-complex array, which the synthetic bench uses.
    """
    a = np.asarray(iq)
    if np.iscomplexobj(a):
        return a.astype(np.complex128)
    a = a.astype(np.float64)
    if a.size < 2 or a.size % 2:
        return np.zeros(0, dtype=np.complex128)
    pairs = a.reshape(-1, 2)
    return pairs[:, 1] + 1j * pairs[:, 0]


def differential_phase(iq: Sequence[Any],
                       first_word_invalid: bool = False) -> np.ndarray:
    """Phase difference between adjacent used subcarriers, unwrapped.

    Common CFO is removed by differencing; the static SFO slope is a
    constant offset in the differences. Temporal analysis removes each
    pair's own mean, so slow common drift does not become a feature.
    """
    c = complex_from_iq(iq)
    if c.size < 4:
        return np.zeros(0, dtype=np.float64)
    mask = used_mask(c.size, first_word_invalid)
    if not mask.any():
        return np.zeros(0, dtype=np.float64)
    phase = np.angle(c[mask])
    phase = np.unwrap(phase)
    return np.diff(phase)


def _resp_band(times: np.ndarray, values: np.ndarray) -> Tuple[float, float]:
    """Exploratory 0.1–0.5 Hz power ratio and peak.

    This is not a respiration detector. It is a descriptive feature for the
    controlled, still-subject phase experiment, and it is NaN when the
    window is too short or the timestamps are unusable.
    """
    t = np.asarray(times, dtype=np.float64)
    x = np.asarray(values, dtype=np.float64)
    if t.size != x.size or t.size < 12:
        return float("nan"), float("nan")
    order = np.argsort(t)
    t, x = t[order], x[order]
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(x)):
        return float("nan"), float("nan")
    dt = float(np.median(np.diff(t)))
    if dt <= 0 or t[-1] - t[0] < 3.0:
        return float("nan"), float("nan")
    grid = np.arange(t[0], t[-1] + dt * 0.5, dt)
    if grid.size < 12:
        return float("nan"), float("nan")
    y = np.interp(grid, t, x)
    y = y - y.mean()
    if np.allclose(y, 0):
        return 0.0, 0.0
    w = np.hanning(y.size)
    spec = np.abs(np.fft.rfft(y * w)) ** 2
    freq = np.fft.rfftfreq(y.size, dt)
    total = (freq >= 0.05) & (freq <= 1.5)
    band = (freq >= 0.10) & (freq <= 0.50)
    denom = float(spec[total].sum())
    if denom <= 0 or not band.any():
        return float("nan"), float("nan")
    ratio = float(spec[band].sum() / denom)
    peak = float(freq[band][int(np.argmax(spec[band]))])
    return ratio, peak


# --- trial features --------------------------------------------------------

def _payload_samples(samples: Sequence[dict]) -> List[dict]:
    out = []
    for s in samples:
        sl = s.get("sig_len")
        if sl is None or int(sl) >= PAYLOAD_MIN_SIG_LEN:
            out.append(s)
    return out


def trial_qc(trial: dict, requested_s: float = ALPHA003_TRIAL_S,
             min_payload: int = ALPHA003_MIN_PAYLOAD) -> List[str]:
    """Pre-registered Alpha 003 trial-level validity checks.

    These are deliberately the same kinds of failure as Alpha 002-C, with the
    Alpha 003 30 s window and 270-payload floor. The function does not
    silently drop trials; the caller records every reason.
    """
    problems = []
    payload = len(_payload_samples(trial.get("samples") or []))
    if payload < int(min_payload):
        problems.append(f"{payload} payload frames < {int(min_payload)}")
    active = trial.get("active_s", trial.get("sensor_span_s"))
    if active is None or not np.isfinite(float(active)):
        problems.append("active window missing")
    elif abs(float(active) - float(requested_s)) > ALPHA003_TRIAL_TOLERANCE_S:
        problems.append(f"active window {active} outside "
                        f"{requested_s}±{ALPHA003_TRIAL_TOLERANCE_S} s")
    gap = trial.get("max_sensor_gap_s")
    if gap is not None and (not np.isfinite(float(gap))
                            or float(gap) > ALPHA003_MAX_GAP_S):
        problems.append(f"max sensor gap {gap} > {ALPHA003_MAX_GAP_S}")
    unc = trial.get("boundary_uncertainty_s")
    if unc is not None and (not np.isfinite(float(unc))
                            or float(unc) > ALPHA003_MAX_UNCERTAINTY_S):
        problems.append(f"boundary uncertainty {unc} > "
                        f"{ALPHA003_MAX_UNCERTAINTY_S}")
    if trial.get("clock_resets") not in (0, None):
        problems.append("clock resets")
    late = trial.get("late_frames")
    if isinstance(late, dict):
        if any(v for v in late.values()):
            problems.append("late frames")
    elif late not in (0, None):
        problems.append("late frames")
    if trial.get("valid") is False:
        problems.append("recorder marked trial invalid")
    if trial.get("label") not in CONDITIONS:
        problems.append(f"label {trial.get('label')!r} is not an Alpha 003 "
                        "condition")
    return problems


def _amplitude_block(samples: Sequence[dict]) -> Tuple[np.ndarray, np.ndarray]:
    payload = _payload_samples(samples)
    if not payload:
        return np.zeros((0, 0)), np.zeros(0)
    width = max(len(s.get("amplitudes") or []) for s in payload)
    amps = np.zeros((len(payload), width), dtype=np.float64)
    for i, s in enumerate(payload):
        a = s.get("amplitudes") or []
        amps[i, :len(a)] = a
    return amps, np.asarray([s.get("rssi", np.nan) for s in payload],
                            dtype=np.float64)


def amplitude_features(samples: Sequence[dict]) -> Dict[str, Any]:
    amps, rssi = _amplitude_block(samples)
    if amps.size == 0 or amps.shape[0] < 2:
        return {"roughness_used": float("nan"),
                "amp_volatility": float("nan"),
                "rssi_mean": (float(np.nanmean(rssi)) if rssi.size else
                              float("nan")),
                "profile": np.zeros(0), "payload_frames": len(amps)}
    fwi = any(bool(s.get("first_word_invalid"))
              for s in _payload_samples(samples))
    mask = used_mask(amps.shape[1], fwi)
    totals = amps.sum(axis=1)
    safe = np.where(totals > 0, totals, 1.0)
    norm = amps / safe[:, None]
    u = norm[:, mask] if mask.any() else norm
    rough = float(np.abs(np.diff(u, axis=0)).mean())
    vol = float(np.abs(np.diff(totals)).mean() / (totals.mean() or 1.0))
    profile = u.mean(axis=0)
    return {"roughness_used": rough, "amp_volatility": vol,
            "rssi_mean": (float(np.nanmean(rssi)) if rssi.size else
                          float("nan")),
            "profile": profile, "payload_frames": int(amps.shape[0])}


def phase_features(samples: Sequence[dict]) -> Dict[str, Any]:
    rows, times = [], []
    for s in _payload_samples(samples):
        iq = s.get("iq")
        if iq is None:
            continue
        d = differential_phase(iq, bool(s.get("first_word_invalid")))
        if d.size == 0:
            continue
        rows.append(d)
        t = s.get("t", s.get("t_sensor", s.get("t_host")))
        times.append(float(t) if t is not None else np.nan)
    if len(rows) < 3:
        return {"phase_roughness": float("nan"),
                "phase_std": float("nan"),
                "phase_resp_ratio": float("nan"),
                "phase_resp_peak_hz": float("nan"),
                "phase_frames": len(rows)}
    width = min(r.size for r in rows)
    D = np.stack([r[:width] for r in rows])
    # remove each pair's static offset; common drift then cannot leak in.
    D = D - D.mean(axis=0, keepdims=True)
    phase_rough = float(np.abs(np.diff(D, axis=0)).mean())
    phase_std = float(D.std(axis=0).mean())
    ratio, peak = _resp_band(np.asarray(times, dtype=np.float64),
                             D.mean(axis=1))
    return {"phase_roughness": phase_rough, "phase_std": phase_std,
            "phase_resp_ratio": ratio, "phase_resp_peak_hz": peak,
            "phase_frames": len(rows)}


def trial_features(trial: dict,
                   empty_profile: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Features for one trial. The label is never read."""
    a = amplitude_features(trial.get("samples") or [])
    p = phase_features(trial.get("samples") or [])
    profile = a.pop("profile")
    if empty_profile is not None and profile.size and np.size(empty_profile):
        k = min(profile.size, np.size(empty_profile))
        dist = float(np.linalg.norm(profile[:k] -
                                    np.asarray(empty_profile)[:k]))
    else:
        dist = float("nan")
    out = {k: a.get(k, float("nan")) for k in
           ("roughness_used", "amp_volatility", "rssi_mean")}
    out.update({k: p.get(k, float("nan")) for k in PHASE_FEATURES})
    out["profile_distance"] = dist
    out["profile"] = profile
    out["payload_frames"] = a.get("payload_frames", 0)
    out["phase_frames"] = p.get("phase_frames", 0)
    return out


def baseline_profile(trials: Sequence[dict]) -> Optional[np.ndarray]:
    profs = []
    for t in trials:
        if t.get("label") != "empty":
            continue
        f = amplitude_features(t.get("samples") or [])
        if f["profile"].size:
            profs.append(f["profile"])
    if not profs:
        return None
    k = min(p.size for p in profs)
    return np.mean([p[:k] for p in profs], axis=0)


# --- raw IQ attachment -----------------------------------------------------

def attach_iq_from_raw(trials: Sequence[dict], raw_path: str) -> Dict[str, int]:
    """Attach raw IQ to trial samples by CSI sequence id.

    The Alpha acquisition writes the raw serial stream *and* the trial JSON
    amplitudes. The raw stream still has the 128 IQ values per frame, so
    phase can be recovered offline without a firmware change.
    """
    from .dispatcher import CsiParser

    parser = CsiParser()
    by_seq: Dict[int, Sequence[int]] = {}
    malformed = 0
    with open(raw_path, "rb") as fh:
        for raw in fh:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("CSI_DATA"):
                continue
            outcome = parser.feed_resilient(line)
            malformed += int(bool(outcome.malformed))
            for rec in outcome.records:
                by_seq[int(rec.seq)] = rec.iq
    attached = missing = 0
    for t in trials:
        for s in t.get("samples") or []:
            seq = s.get("id")
            if seq is None:
                missing += 1
                continue
            iq = by_seq.get(int(seq))
            if iq is None:
                missing += 1
            else:
                s["iq"] = iq
                attached += 1
    return {"raw_records": len(by_seq), "attached": attached,
            "missing": missing, "malformed_lines": malformed}


def load_session(path: str, raw_path: Optional[str] = None,
                 session_id: Optional[str] = None) -> List[dict]:
    """Load a recorded Alpha-style session into a flat trial list."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sid = session_id or Path(path).stem
    trials = []
    for t in data.get("trials", []):
        d = dict(t)
        d["session_id"] = sid
        d["samples"] = [dict(s) for s in t.get("samples", [])]
        for s in d["samples"]:
            if "t" not in s:
                s["t"] = s.get("t_sensor", s.get("t_host"))
        trials.append(d)
    if raw_path:
        attach_iq_from_raw(trials, raw_path)
    return trials


# --- grouped evaluation ----------------------------------------------------

def _auc(scores: np.ndarray, positive: np.ndarray) -> float:
    scores = np.asarray(scores, dtype=np.float64)
    positive = np.asarray(positive, dtype=bool)
    n_pos = int(positive.sum())
    n_neg = int((~positive).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(scores.size, dtype=np.float64)
    ranks[order] = np.arange(1, scores.size + 1, dtype=np.float64)
    # average ties
    s_sorted = scores[order]
    i = 0
    while i < s_sorted.size:
        j = i + 1
        while j < s_sorted.size and s_sorted[j] == s_sorted[i]:
            j += 1
        if j - i > 1:
            ranks[order[i:j]] = (i + j + 1) / 2.0
        i = j
    return float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2.0)
                 / (n_pos * n_neg))


def _standardise(train: np.ndarray, test: np.ndarray):
    # Column-wise finite median, without numpy's all-NaN warning.
    med = np.zeros(train.shape[1], dtype=np.float64)
    for j in range(train.shape[1]):
        col = train[np.isfinite(train[:, j]), j]
        med[j] = float(np.median(col)) if col.size else 0.0
    train = np.where(np.isfinite(train), train, med)
    test = np.where(np.isfinite(test), test, med)
    mu = train.mean(axis=0)
    sd = train.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    return (train - mu) / sd, (test - mu) / sd


def _feature_matrix(base: Sequence[dict], idx: Sequence[int],
                    features: Sequence[str],
                    baseline: Optional[np.ndarray]) -> np.ndarray:
    rows = []
    for i in idx:
        f = base[i]
        vals = []
        for name in features:
            if name == "profile_distance":
                prof = f.get("profile")
                if baseline is None or prof is None or not len(prof):
                    v = float("nan")
                else:
                    k = min(len(prof), len(baseline))
                    v = float(np.linalg.norm(prof[:k] - baseline[:k]))
            else:
                v = f.get(name, float("nan"))
            vals.append(v)
        rows.append(vals)
    return np.asarray(rows, dtype=np.float64)


def _centroid_predict(Xtr, ytr, Xte):
    classes = sorted(set(ytr))
    cent = {}
    for c in classes:
        z = Xtr[ytr == c]
        cent[c] = z.mean(axis=0)
    dist = np.stack([np.linalg.norm(Xte - cent[c], axis=1)
                     for c in classes], axis=1)
    pred = np.asarray(classes)[np.argmin(dist, axis=1)]
    return pred, classes, dist


def _metrics(y, pred, classes, scores=None, positive=None):
    y = np.asarray(y)
    pred = np.asarray(pred)
    recall = {}
    for c in classes:
        m = y == c
        recall[c] = (float((pred[m] == c).mean()) if m.any()
                     else float("nan"))
    bal = float(np.nanmean(list(recall.values())))
    empty = y == "empty"
    fpr = (float((pred[empty] != "empty").mean()) if empty.any()
           else float("nan"))
    out = {"balanced_accuracy": bal,
           "accuracy": float((pred == y).mean()),
           "per_class_recall": recall,
           "empty_false_positive_rate": fpr,
           "confusion": {c: {d: int(((y == c) & (pred == d)).sum())
                             for d in classes} for c in classes}}
    if scores is not None and positive is not None:
        out["auc"] = _auc(scores, y == positive)
    return out


def leave_one_session_out(trials: Sequence[dict]):
    """Return ``(train_idx, test_idx, test_session)`` folds.

    No session may contribute to both sides of a fold. This is the unit the
    preregistration uses; frame-level random splits are not permitted.
    """
    sessions = sorted({t["session_id"] for t in trials})
    folds = []
    for test_session in sessions:
        test_idx = [i for i, t in enumerate(trials)
                    if t["session_id"] == test_session]
        train_idx = [i for i, t in enumerate(trials)
                     if t["session_id"] != test_session]
        if test_idx and train_idx:
            folds.append((train_idx, test_idx, test_session))
    return folds


def _predict_cv(base, trials, classes, features, labels=None,
                calibration: str = "training"):
    """Out-of-fold predictions with one full session held out at a time."""
    labels = labels if labels is not None else [t["label"] for t in trials]
    preds = []
    sessions = sorted({t["session_id"] for t in trials})
    for train_idx, test_idx, test_session in leave_one_session_out(trials):
        train_trials = [trials[i] for i in train_idx]
        train_labels = [labels[i] for i in train_idx]
        # The empty reference is fitted on training sessions only for the
        # primary analysis. The explicitly secondary calibrated analysis may
        # use the held-out session's empty trials as a calibration baseline;
        # that is calibration, not training on condition labels.
        base_prof = baseline_profile(train_trials)
        test_prof = base_prof
        if calibration == "session_empty":
            test_prof = baseline_profile([trials[i] for i in test_idx])
        elif calibration != "training":
            raise ValueError(f"unknown calibration {calibration!r}")
        Xtr = _feature_matrix(base, train_idx, features, base_prof)
        Xte = _feature_matrix(base, test_idx, features, test_prof)
        Xtr, Xte = _standardise(Xtr, Xte)
        pred, cls, dist = _centroid_predict(
            Xtr, np.asarray(train_labels), Xte)
        for j, i in enumerate(test_idx):
            rec = {"index": i, "session_id": trials[i]["session_id"],
                   "block": trials[i].get("block"),
                   "posture": trials[i].get("posture"),
                   "true": labels[i], "pred": str(pred[j])}
            if len(cls) == 2 and "empty" in cls:
                pos = [c for c in cls if c != "empty"][0]
                # higher score means more like the positive class
                rec["score"] = float(dist[j, cls.index("empty")] -
                                     dist[j, cls.index(pos)])
            preds.append(rec)
    return preds, sessions


def _aggregate(preds, classes):
    y = np.array([p["true"] for p in preds])
    pred = np.array([p["pred"] for p in preds])
    scores = (np.array([p.get("score", np.nan) for p in preds])
              if len(classes) == 2 else None)
    positive = next((c for c in classes if c != "empty"), None)
    return _metrics(y, pred, classes, scores, positive)


def stationary_recall_by_posture(predictions: Sequence[dict]) -> Dict[str, dict]:
    """Recall of the stationary class for each recorded posture.

    Posture is metadata attached before analysis (standing/sitting/...).
    Empty/moving predictions are ignored here; the preregistration uses this
    as the posture-generality check.
    """
    groups: Dict[str, List[dict]] = {}
    for p in predictions:
        if p.get("true") != "stationary":
            continue
        key = str(p.get("posture") or "unspecified")
        groups.setdefault(key, []).append(p)
    out = {}
    for key, rows in sorted(groups.items()):
        out[key] = {
            "n": len(rows),
            "recall": float(np.mean([r["pred"] == "stationary"
                                     for r in rows])),
        }
    return out


def _bootstrap(preds, classes, n_boot=1000, seed=0):
    sessions = sorted({p["session_id"] for p in preds})
    if len(sessions) < 2:
        return {"balanced_accuracy": [float("nan"), float("nan")],
                "empty_false_positive_rate": [float("nan"), float("nan")],
                "method": "insufficient sessions"}
    rng = np.random.default_rng(seed)
    vals_bal, vals_fpr = [], []
    by = {s: [p for p in preds if p["session_id"] == s] for s in sessions}
    for _ in range(n_boot):
        chosen = rng.choice(sessions, size=len(sessions), replace=True)
        sample = [p for s in chosen for p in by[s]]
        m = _aggregate(sample, classes)
        vals_bal.append(m["balanced_accuracy"])
        vals_fpr.append(m["empty_false_positive_rate"])
    return {"balanced_accuracy": [float(np.nanpercentile(vals_bal, 2.5)),
                                  float(np.nanpercentile(vals_bal, 97.5))],
            "empty_false_positive_rate": [
                float(np.nanpercentile(vals_fpr, 2.5)),
                float(np.nanpercentile(vals_fpr, 97.5))],
            "method": "session bootstrap"}


def evaluate(trials: Sequence[dict], classes: Sequence[str],
             features: Sequence[str], *, n_perm: int = 0,
             seed: int = 0, n_boot: int = 1000,
             calibration: str = "training") -> Dict[str, Any]:
    """Session-independent evaluation of a fixed nearest-centroid model.

    Every test session is held out entirely. The empty profile reference and
    the feature scaler are fitted on training sessions only. A permutation
    null shuffles labels within each session, preserving session class
    counts and the session structure.
    """
    classes = tuple(classes)
    use = [t for t in trials if t["label"] in classes]
    if not use:
        raise ValueError("no trials in the requested classes")
    base = []
    for t in use:
        f = trial_features(t)
        base.append(f)
    labels = [t["label"] for t in use]
    preds, sessions = _predict_cv(base, use, classes, features,
                                  calibration=calibration)
    obs = _aggregate(preds, classes)
    obs["ci"] = _bootstrap(preds, classes, n_boot=n_boot, seed=seed)
    obs["n"] = len(preds)
    obs["n_sessions"] = len(sessions)
    obs["classes"] = list(classes)
    obs["features"] = list(features)
    obs["calibration"] = calibration
    obs["folds"] = "leave-one-session-out"
    obs["predictions"] = preds
    obs["stationary_recall_by_posture"] = stationary_recall_by_posture(preds)
    if n_perm:
        rng = np.random.default_rng(seed + 1)
        by_session = {}
        for i, t in enumerate(use):
            by_session.setdefault(t["session_id"], []).append(i)
        null = []
        for _ in range(int(n_perm)):
            shuffled = list(labels)
            for idxs in by_session.values():
                vals = [labels[i] for i in idxs]
                rng.shuffle(vals)
                for i, v in zip(idxs, vals):
                    shuffled[i] = v
            p, _ = _predict_cv(base, use, classes, features, labels=shuffled,
                               calibration=calibration)
            null.append(_aggregate(p, classes)["balanced_accuracy"])
        null = np.asarray(null, dtype=np.float64)
        obs["null"] = {
            "n": int(n_perm),
            "mean_balanced_accuracy": float(np.nanmean(null)),
            "p": float((1 + int(np.sum(null >= obs["balanced_accuracy"])))
                       / (1 + int(n_perm))),
            "q95_balanced_accuracy": float(np.nanpercentile(null, 95)),
        }
    return obs
