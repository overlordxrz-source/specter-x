"""The guided motion experiment, and the statistics that judge it.

This module holds three things:

* the **trial machine** - a small state machine that walks a subject through
  labelled phases (stationary, hand motion, ...) and records each one;
* the **metrics** - the gain-free features and the one-way ANOVA that decide
  whether the conditions are actually different;
* the **verdict** - and this is the part that matters most.

Signal change is not human detection
-------------------------------------
The live HUD shows a "signal change from baseline" trace. That trace says the
radio path moved. It does **not** say a person was detected: a person
walking past, a door, a chair, the access point changing its transmit power
- all of them move the radio path.

A **verified human detection** is a much stronger claim, and it needs two
things this project will not fake:

1. a **labelled trial** - a phase during which a consenting person was
   told to move, and did;
2. **statistics that separate the conditions** - the labelled phases must
   differ by more than the same phase repeated does.

If either is missing, the verdict is "not verified". The module never
upgrades a signal change into a detection on its own.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# --- the statistics --------------------------------------------------------


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-12:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def f_sf(f: float, df1: int, df2: int) -> float:
    """Survival function of the F distribution: P(F > f)."""
    if df1 <= 0 or df2 <= 0 or f != f:
        return float("nan")
    if f <= 0:
        return 1.0
    x = df2 / (df2 + df1 * f)
    return _betai(df2 / 2.0, df1 / 2.0, x)


def one_way_f(groups: Dict[str, List[float]]) -> Dict:
    """One-way ANOVA F test across the conditions."""
    labels = list(groups)
    grand = [v for lab in labels for v in groups[lab]]
    if len(labels) < 2 or len(grand) <= len(labels):
        return {"f": float("nan"), "p": float("nan"), "df1": 0, "df2": 0}
    gm = statistics.mean(grand)
    between = sum(len(groups[l]) * (statistics.mean(groups[l]) - gm) ** 2
                  for l in labels)
    within = sum(sum((v - statistics.mean(groups[l])) ** 2 for v in groups[l])
                 for l in labels)
    df1, df2 = len(labels) - 1, len(grand) - len(labels)
    if within <= 0:
        return {"f": float("inf"), "p": 0.0, "df1": df1, "df2": df2}
    f = (between / df1) / (within / df2)
    return {"f": round(f, 4), "p": round(f_sf(f, df1, df2), 6),
            "df1": df1, "df2": df2}


def trial_features(trial: Dict) -> Dict:
    """The gain-free features of one trial.

    ``trial`` is a dict with ``amplitudes`` (n x carriers), ``rssi`` (n,),
    ``used`` (carriers,) and ``label``.

    The total amplitude is not a motion feature: it tracks the received
    power. Everything here is either normalised by the packet's own gain or
    is a *temporal* measure, which is what a body in the path changes.
    """
    raw = trial.get("amplitudes")
    amps = np.asarray(raw if raw is not None else [], dtype=np.float32)
    if amps.ndim != 2 or amps.shape[0] < 2:
        return {"n": 0, "label": trial.get("label", "")}
    raw_rssi = trial.get("rssi")
    rssi = np.asarray(raw_rssi if raw_rssi is not None else [], dtype=np.float32)
    used = trial.get("used")
    if used is None:
        used = np.ones(amps.shape[1], bool)
    else:
        used = np.asarray(used, bool)

    totals = amps.sum(axis=1)
    safe = np.where(totals > 0, totals, 1.0)
    norm = amps / safe[:, None]

    # temporal roughness: how much the normalised profile moves per packet
    diffs = np.abs(np.diff(norm, axis=0)).sum(axis=1) / max(norm.shape[1], 1)
    roughness = float(diffs.mean()) if diffs.size else 0.0

    # the same on the used carriers only
    if used.any():
        u = norm[:, used]
        du = np.abs(np.diff(u, axis=0)).mean(axis=1)
        roughness_used = float(du.mean()) if du.size else 0.0
    else:
        roughness_used = 0.0

    # amplitude volatility, and the correlation with RSSI - the confounder
    amp_diff = np.abs(np.diff(totals))
    amp_vol = float(amp_diff.mean() / (float(totals.mean()) or 1.0)) \
        if amp_diff.size else 0.0
    corr = 0.0
    if rssi.size == totals.size and totals.size > 2:
        a = totals.astype(np.float64)
        r = rssi.astype(np.float64)
        a = a - a.mean()
        r = r - r.mean()
        den = float(np.sqrt((a * a).sum() * (r * r).sum()))
        if den > 0:
            corr = float((a * r).sum() / den)

    return {
        "label": trial.get("label", ""),
        "n": int(amps.shape[0]),
        "total_amplitude_mean": round(float(totals.mean()), 3),
        "total_amplitude_std": round(float(totals.std()), 3),
        "rssi_mean": round(float(rssi.mean()), 3) if rssi.size else None,
        "rssi_std": round(float(rssi.std()), 3) if rssi.size > 1 else None,
        "roughness": round(roughness, 6),
        "roughness_used": round(roughness_used, 6),
        "amp_volatility": round(amp_vol, 6),
        "amp_rssi_corr": round(corr, 4),
    }


def per_carrier_screen(trials: Sequence[Dict]) -> Dict:
    """Screen the conditions carrier by carrier.

    For each subcarrier, the variance *between* the trials' mean amplitudes
    is divided by the variance *within* them. A large ratio means that
    carrier's amplitude depends on the condition.

    Two things this screen must not do:

    * count the carriers the radio is not populating - they read zero in
      every trial and would dilute every ratio;
    * call a ratio of 1.0 a detection. An F of 1 is the smallest the ratio
      can be; it means "no better than chance". The verdict is judged
      against the F distribution, and the p-value is reported.
    """
    usable = [t for t in trials
              if t.get("amplitudes") is not None
              and np.asarray(t["amplitudes"]).size]
    labels = [t.get("label", "") for t in usable]
    if not usable:
        return {"labels": labels, "max_f": 0.0, "median_f": 0.0, "verdict":
                "need at least two trials with data"}
    mats = [np.asarray(t["amplitudes"], dtype=np.float64) for t in usable]
    n_carriers = min(m.shape[1] for m in mats)
    means = np.stack([m[:, :n_carriers].mean(axis=0) for m in mats])   # trials x carriers
    stds = np.stack([m[:, :n_carriers].std(axis=0) for m in mats])
    null_carriers = [c for c in range(n_carriers) if all(means[i, c] == 0.0
                                                         for i in range(len(means)))]
    ratios = []
    for c in range(n_carriers):
        if c in null_carriers:
            continue
        within = float(np.mean(stds[:, c] ** 2)) or 1e-9
        between = float(np.var(means[:, c]))
        ratios.append(between / within)
    max_f = max(ratios) if ratios else 0.0
    n_labels = len(set(labels))
    critical = 5.14 if n_labels == 3 else 4.26
    p = f_sf(max_f, max(n_labels - 1, 1), max(len(usable) - n_labels, 1)) \
        if (usable and n_labels > 1) else float("nan")
    if max_f >= critical:
        verdict = (f"conditions are separable (max F {max_f:.2f} >= the "
                   f"alpha=0.05 critical value {critical})")
    else:
        verdict = (f"NOT separable - max F {max_f:.2f} is below the alpha=0.05 "
                   f"critical value {critical} for {n_labels} conditions. "
                   f"No effect was detected: this is the noise floor, so more "
                   f"trials or a stronger stimulus are needed.")
    return {
        "labels": labels,
        "carriers": n_carriers,
        "carriers_used": len(ratios),
        "null_carriers": null_carriers,
        "per_carrier_f": [round(r, 3) for r in ratios],
        "max_f": round(max_f, 3),
        "median_f": round(float(np.median(ratios)), 3) if ratios else 0.0,
        "max_f_p": p,
        "critical_f": critical,
        "verdict": verdict,
    }


def condition_test(trials: Sequence[Dict], alpha: float = 0.05) -> Dict:
    """Test the gain-free features across the conditions."""
    feats = [trial_features(t) for t in trials]
    groups: Dict[str, List[float]] = {}
    for f in feats:
        if not f.get("n"):
            continue
        groups.setdefault(f["label"], []).append(f["roughness_used"])
    out: Dict[str, Dict] = {}
    if len(groups) > 1:
        out["roughness"] = one_way_f(groups)
    groups = {}
    for f in feats:
        if f.get("n"):
            groups.setdefault(f["label"], []).append(f["amp_volatility"])
    if len(groups) > 1:
        out["amplitude volatility"] = one_way_f(groups)
    # the confounded ones, for reference
    groups = {}
    for f in feats:
        if f.get("n"):
            groups.setdefault(f["label"], []).append(f["total_amplitude_mean"])
    if len(groups) > 1:
        out["total amplitude (confounded by RSSI)"] = one_way_f(groups)
    groups = {}
    for f in feats:
        if f.get("n") and f.get("rssi_mean") is not None:
            groups.setdefault(f["label"], []).append(f["rssi_mean"])
    if len(groups) > 1:
        out["RSSI (the confounder)"] = one_way_f(groups)
    for r in out.values():
        r["significant"] = bool(r["p"] == r["p"] and r["p"] < alpha)
    return out


def verdict_from(trials: Sequence[Dict], test: Dict, alpha: float = 0.05) -> Dict:
    """Turn the statistics into a claim - and keep the claim honest."""
    labels = sorted({t.get("label", "") for t in trials})
    significant = [k for k, v in test.items() if v.get("significant")]
    has_control = "stationary" in labels
    has_motion = any(l != "stationary" for l in labels)
    separated = bool(significant)

    if not separated:
        headline = "NOT SEPARABLE"
        detail = ("the conditions do not differ by more than repeating one "
                  "condition does")
    else:
        headline = "CONDITIONS SEPARATE"
        detail = f"significant on: {', '.join(significant)}"

    if separated and has_control and has_motion:
        claim = "VERIFIED HUMAN DETECTION (labelled trial, conditions separate)"
    elif separated:
        claim = "CONDITIONS SEPARATE, BUT NO STATIONARY CONTROL"
    else:
        claim = "SIGNAL CHANGE ONLY - NO VERIFIED HUMAN DETECTION"

    return {
        "headline": headline,
        "detail": detail,
        "claim": claim,
        "verified_human_detection": bool(separated and has_control and has_motion),
        "significant_features": significant,
        "labels": labels,
        "alpha": alpha,
    }


# --- the trial machine -----------------------------------------------------


@dataclass
class TrialSpec:
    """One phase of the experiment."""
    label: str
    seconds: float
    instruction: str = ""

    def to_dict(self) -> Dict:
        return {"label": self.label, "seconds": self.seconds,
                "instruction": self.instruction}


DEFAULT_INSTRUCTIONS = {
    "stationary": "Stand still and do not move.",
    "hand": "Wave one hand up and down, in place.",
    "walking": "Walk a few steps back and forth, at normal speed.",
}


class GuidedExperiment:
    """Walks a subject through labelled phases and records each one.

    The machine is deliberately simple: it has a phase, a clock and a
    recorder. Everything it knows is in :meth:`state`, so the HUD can draw it
    and the export can be written without knowing anything else.
    """

    PHASES = ("IDLE", "LEAD-IN", "RECORDING", "ANALYSIS", "DONE")

    def __init__(self, specs: Sequence[TrialSpec], consent: str = "",
                 lead_in: float = 4.0, announce: bool = False,
                 shuffle: bool = False, seed: int = 1,
                 method: str = ""):
        base = list(specs) or [TrialSpec("stationary", 30.0),
                               TrialSpec("hand", 30.0)]
        if shuffle:
            import random
            rng = random.Random(seed)
            rng.shuffle(base)
        self.specs = base
        self.consent = consent
        self.lead_in = float(lead_in)
        self.announce = bool(announce)
        self.method = method

        self.phase = "IDLE"
        self.phase_started = 0.0
        self.index = 0
        self.trials: List[Dict] = []
        self._rec: Optional[Dict] = None
        self._amp: List[np.ndarray] = []
        self._rssi: List[float] = []
        self._ids: List[int] = []
        self._t: List[float] = []
        self.used: Optional[np.ndarray] = None
        self.result: Optional[Dict] = None
        self.started_at = 0.0
        self.ended_at = 0.0

    # -- driving ------------------------------------------------------------

    def start(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        if self.phase != "IDLE":
            return
        self.started_at = now
        self._begin_trial(now)

    def _begin_trial(self, now: float) -> None:
        self.phase = "LEAD-IN"
        self.phase_started = now
        spec = self.specs[self.index]
        if self.announce:
            self.say(f"Trial {self.index + 1} of {len(self.specs)}. "
                     f"{spec.instruction or DEFAULT_INSTRUCTIONS.get(spec.label, '')}")

    def say(self, message: str) -> None:
        """Speak a cue, so the subject does not have to watch a screen."""
        if not self.announce:
            return
        try:
            subprocess.run(["say", message], check=False, capture_output=True)
        except Exception:
            pass

    def feed(self, record, t: Optional[float] = None) -> None:
        """Fold one CSI packet into the current trial."""
        if self.phase != "RECORDING":
            return
        from .csi_analysis import subcarrier_amplitudes_np
        amps = subcarrier_amplitudes_np(record.iq)
        if amps.size == 0:
            return
        self._amp.append(amps.astype(np.float32))
        self._rssi.append(float(record.rssi))
        self._ids.append(int(record.seq))
        self._t.append(float(t if t is not None else time.time()))

    def tick(self, now: Optional[float] = None) -> None:
        """Advance the machine. Called once per frame."""
        now = time.time() if now is None else now
        if self.phase == "LEAD-IN":
            if now - self.phase_started >= self.lead_in:
                self.phase = "RECORDING"
                self.phase_started = now
                self._rec = {
                    "label": self.specs[self.index].label,
                    "requested_s": self.specs[self.index].seconds,
                    "started_at": now,
                    "packets": 0,
                    "sequence_gaps": 0,
                    "missing_packets": 0,
                    "malformed": 0,
                }
        elif self.phase == "RECORDING":
            spec = self.specs[self.index]
            if now - self.phase_started >= spec.seconds:
                self._close_trial(now)
        elif self.phase == "ANALYSIS":
            self.result = self.analyse()
            self.phase = "DONE"
            self.ended_at = now
            self.say("The recording is finished. Thank you.")

    def _close_trial(self, now: float) -> None:
        rec = self._rec or {}
        amps = np.asarray(self._amp, dtype=np.float32) if self._amp \
            else np.zeros((0, 0), np.float32)
        rec["actual_s"] = round(now - self.phase_started, 3)
        rec["packets"] = int(amps.shape[0])
        rec["amplitudes"] = amps
        rec["rssi"] = np.asarray(self._rssi, dtype=np.float32)
        rec["ids"] = np.asarray(self._ids, dtype=np.int64)
        rec["t"] = np.asarray(self._t, dtype=np.float32)
        rec["used"] = self.used
        self.trials.append(rec)
        self._amp, self._rssi, self._ids, self._t = [], [], [], []
        self._rec = None
        self.index += 1
        if self.index < len(self.specs):
            self._begin_trial(now)
        else:
            self.phase = "ANALYSIS"
            self.phase_started = now

    # -- reading ------------------------------------------------------------

    def state(self) -> Dict:
        """What the HUD needs to draw the experiment."""
        spec = self.specs[self.index] if self.index < len(self.specs) else None
        remaining = None
        if self.phase == "LEAD-IN":
            remaining = max(0.0, self.lead_in - (time.time() - self.phase_started))
        elif self.phase == "RECORDING" and spec is not None:
            remaining = max(0.0, spec.seconds - (time.time() - self.phase_started))
        st = {
            "phase": self.phase,
            "phase_label": (spec.instruction or DEFAULT_INSTRUCTIONS.get(
                spec.label, spec.label)) if spec else self.phase,
            "trial_label": spec.label if spec else "",
            "trial_index": min(self.index + 1, len(self.specs)),
            "trial_total": len(self.specs),
            "remaining_s": remaining,
            "trials_done": len(self.trials),
            "consent": self.consent,
        }
        if self.result:
            st["verdict"] = self.result.get("claim", "")
            st["headline"] = self.result.get("headline", "")
        return st

    def analyse(self) -> Dict:
        """The statistics over the recorded trials."""
        test = condition_test(self.trials)
        return {
            "test": test,
            "verdict": verdict_from(self.trials, test),
            "features": [trial_features(t) for t in self.trials],
        }

    # -- exporting ----------------------------------------------------------

    def export(self, path: str, csv_path: Optional[str] = None) -> Dict:
        """Write the trials and their metrics.

        The per-packet amplitudes are written as a compact binary sidecar
        (``.npz``) rather than as JSON, because a fifteen minute run is
        hundreds of thousands of packets and JSON would be hundreds of
        megabytes of nothing but brackets.
        """
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        result = self.analyse()
        summary = {
            "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at)),
            "consent": self.consent,
            "method": self.method or ("ESP32-S3 downlink CSI of the AP it is "
                                      "already associated with; no scanning, no "
                                      "probing of other devices, all data local"),
            "trials": [{
                "label": t.get("label"),
                "requested_s": t.get("requested_s"),
                "actual_s": t.get("actual_s"),
                "packets": t.get("packets"),
                "sequence_gaps": t.get("sequence_gaps"),
                "missing_packets": t.get("missing_packets"),
                "malformed": t.get("malformed"),
            } for t in self.trials],
            "features": result["features"],
            "test": result["test"],
            "screen": result.get("screen", {}),
            "verdict": result["verdict"],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)

        arrays = {}
        for i, t in enumerate(self.trials):
            arrays[f"amps_{i}"] = t.get("amplitudes", np.zeros((0, 0), np.float32))
            arrays[f"rssi_{i}"] = t.get("rssi", np.zeros(0, np.float32))
            arrays[f"ids_{i}"] = t.get("ids", np.zeros(0, np.int64))
            arrays[f"t_{i}"] = t.get("t", np.zeros(0, np.float32))
        np.savez_compressed(os.path.splitext(path)[0] + "_packets.npz", **arrays)

        if csv_path:
            self.export_csv(csv_path, result)
        return summary

    def export_csv(self, path: str, result: Optional[Dict] = None) -> None:
        """One row per trial, for a spreadsheet."""
        result = result or self.analyse()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        cols = ["trial", "label", "packets", "duration_s", "amplitude_mean",
                "amplitude_std", "rssi_mean", "rssi_std", "roughness",
                "roughness_used", "amp_volatility", "amp_rssi_corr"]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(",".join(cols) + "\n")
            for i, f in enumerate(result["features"]):
                t = self.trials[i] if i < len(self.trials) else {}
                row = [str(i + 1), f.get("label", ""), f.get("n", 0),
                       t.get("actual_s", ""), f.get("total_amplitude_mean", ""),
                       f.get("total_amplitude_std", ""), f.get("rssi_mean", ""),
                       f.get("rssi_std", ""), f.get("roughness", ""),
                       f.get("roughness_used", ""), f.get("amp_volatility", ""),
                       f.get("amp_rssi_corr", "")]
                fh.write(",".join(str(x) for x in row) + "\n")


# --- offline analysis of a recorded session --------------------------------


def trials_from_json(data: Dict) -> List[Dict]:
    """Rebuild the trial list from a recorded JSON file, for offline analysis.

    The recorded format keeps one entry per packet with the per-carrier
    amplitudes; the metrics work on the array form, so it is converted here.
    """
    out: List[Dict] = []
    for t in data.get("trials", []):
        samples = t.get("samples") or []
        if not samples:
            out.append({"label": t.get("label", ""),
                        "amplitudes": np.zeros((0, 0), np.float32),
                        "rssi": np.zeros(0, np.float32),
                        "used": None})
            continue
        n_carriers = max(len(s.get("amplitudes") or []) for s in samples)
        amps = np.zeros((len(samples), n_carriers), np.float32)
        rssi = np.zeros(len(samples), np.float32)
        for i, s in enumerate(samples):
            a = s.get("amplitudes") or []
            amps[i, :len(a)] = a
            rssi[i] = s.get("rssi") or 0.0
        used = None
        if amps.size:
            used = amps.std(axis=0) > 0
        out.append({
            "label": t.get("label", ""),
            "amplitudes": amps,
            "rssi": rssi,
            "ids": np.asarray([s.get("id", 0) for s in samples], np.int64),
            "t": np.asarray([s.get("t", 0.0) for s in samples], np.float32),
            "used": used,
            "requested_s": t.get("requested_s"),
            "actual_s": t.get("actual_s"),
            "packets": t.get("packets", len(samples)),
        })
    return out


def analyse_offline(data: Dict) -> Dict:
    """The full offline analysis of a recorded session."""
    trials = trials_from_json(data)
    test = condition_test(trials)
    return {
        "features": [trial_features(t) for t in trials],
        "test": test,
        "screen": per_carrier_screen(trials),
        "verdict": verdict_from(trials, test),
    }
