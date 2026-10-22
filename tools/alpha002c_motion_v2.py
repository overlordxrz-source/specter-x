#!/usr/bin/env python3
"""Alpha 002-C motion preregistration v2 — the frozen analysis.

One command, written before the data. It either reports a verdict under the
pre-registered rules or refuses with a reason. It has no options that change
the statistics.

Design: 10 randomised blocks, each with one ``stationary`` and one ``hand``
trial. The primary test is an **exact within-block sign-flip** on the paired
differences: 2^10 = 1 024 assignments, so the two-sided floor is 0.00195,
below the 0.01 gate. The previous six-block design could not reach 0.01
(floor 0.03125), which is why the design changed.

Primary feature: ``roughness_used``, trial-local (no reference fitted on
other trials). Secondary features are reported with Bonferroni alpha = 0.01
and are never substituted for the primary.

Fail-closed rules:
  * any invalid trial, wrong design, short trial or malformed record after
    the first valid one -> INVALID session, no analysis;
  * a payload-rate difference above 10 %, or a different dominant PHY rate,
    -> INCONCLUSIVE;
  * otherwise PASS only if exact p <= 0.01 and |d_z| >= 0.8 with the
    bootstrap interval excluding zero.

    python3 tools/alpha002c_motion_v2.py runs/.../session.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.analysis import (crossfit_features,   # noqa: E402
                                            extract_features)
from specter.sensors.esp32.experiment import trials_from_json    # noqa: E402

BLOCKS = 10
TRIALS_PER_BLOCK = 2
TRIAL_S = 25.0
MIN_PAYLOAD = 150
RATE_MIN, RATE_MAX = 9.0, 11.0
RATE_TOLERANCE = 0.10
P_GATE = 0.01
D_GATE = 0.8
PRIMARY = "roughness_used"
SECONDARY = ("amp_volatility", "shape_shift", "change_rate",
             "mean_amplitude", "rssi")
BONFERRONI = 0.05 / len(SECONDARY)


# --- statistics ------------------------------------------------------------

def signflip_p(diffs):
    """Exact two-sided sign-flip p for paired differences."""
    d = np.asarray(diffs, dtype=float)
    if d.size == 0:
        return float("nan"), 0, 0
    obs = abs(float(d.mean()))
    total = 1 << d.size
    hits = 0
    for bits in range(total):
        signs = np.array([1.0 if (bits >> i) & 1 else -1.0
                          for i in range(d.size)])
        if abs(float((signs * d).mean())) >= obs - 1e-12:
            hits += 1
    return hits / total, hits, total


def paired_dz(diffs, n_boot=2000, seed=0):
    d = np.asarray(diffs, dtype=float)
    if d.size < 2:
        return float("nan"), (float("nan"), float("nan"))
    sd = float(d.std(ddof=1))
    dz = float(d.mean() / sd) if sd > 0 else float("nan")
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        idx = rng.integers(0, d.size, d.size)
        s = d[idx]
        sd_b = float(s.std(ddof=1))
        if sd_b > 0:
            out.append(float(s.mean() / sd_b))
    if not out:
        return dz, (float("nan"), float("nan"))
    return dz, (float(np.percentile(out, 2.5)),
                float(np.percentile(out, 97.5)))


# --- validation ------------------------------------------------------------

def payload_only(trials, min_sig_len=33):
    out = []
    for t in trials:
        s = t.get("samples") or []
        keep = [x for x in s if int(x.get("sig_len", 0)) >= min_sig_len]
        nt = dict(t)
        nt["samples"] = keep
        out.append(nt)
    return out


def validate_design(trials):
    problems = []
    if len(trials) != BLOCKS * TRIALS_PER_BLOCK:
        problems.append(f"{len(trials)} trials, expected "
                        f"{BLOCKS * TRIALS_PER_BLOCK}")
    by_block = {}
    for t in trials:
        by_block.setdefault(t.get("block"), []).append(t.get("label"))
    if sorted(by_block) != list(range(BLOCKS)):
        problems.append(f"blocks {sorted(by_block)}, expected 0..{BLOCKS-1}")
    for b, labels in by_block.items():
        if sorted(labels) != ["hand", "stationary"]:
            problems.append(f"block {b} labels {labels}")
    return problems


def validate_trials(trials, guard_s=0.10):
    problems = []
    for i, t in enumerate(trials, 1):
        if not t.get("valid", False):
            problems.append(f"trial {i}: invalid ({t.get('invalid_reason')})")
        n = len(t.get("samples") or [])
        if n < MIN_PAYLOAD:
            problems.append(f"trial {i}: {n} payload frames < {MIN_PAYLOAD}")
        span = float(t.get("sensor_span_s") or 0.0)
        active = float(t.get("active_s") or 0.0)
        if abs(span - active) > 0.5:
            problems.append(f"trial {i}: span {span:.3f} vs active {active:.3f}")
        if float(t.get("max_sensor_gap_s") or 0.0) > 0.5:
            problems.append(f"trial {i}: sensor gap "
                            f"{t.get('max_sensor_gap_s')}")
        if float(t.get("boundary_uncertainty_s") or 0.0) > guard_s:
            problems.append(f"trial {i}: uncertainty "
                            f"{t.get('boundary_uncertainty_s')}")
        rate = n / span if span > 0 else 0.0
        if not (RATE_MIN <= rate <= RATE_MAX):
            problems.append(f"trial {i}: payload rate {rate:.2f}/s")
    return problems


def validate_raw(path):
    """Allow the torn first line at attach; nothing after it."""
    if not path or not os.path.exists(path):
        return [f"raw stream missing: {path}"]
    lines = open(path, "rb").read().decode("utf-8", "replace").splitlines()
    seen_valid = False
    problems = []
    for i, l in enumerate(lines):
        if not l.startswith("CSI_DATA"):
            continue
        ok = l.endswith('"') and ',"[' in l
        if ok and not seen_valid:
            seen_valid = True
            continue
        if not ok and seen_valid:
            problems.append(f"malformed CSI line {i} after the first record")
    return problems


# --- features --------------------------------------------------------------

def trial_features(trials):
    """Primary trial-local; secondaries cross-fitted (and labelled as such)."""
    base = trials_from_json({"trials": trials})
    local = extract_features(base)
    cross = crossfit_features(base)
    rows = []
    for i, t in enumerate(trials):
        samples = t["samples"]
        amps = [sum(x.get("amplitudes") or []) for x in samples]
        rssi = [x.get("rssi") for x in samples if x.get("rssi") is not None]
        rows.append({
            "label": t.get("label"), "block": t.get("block"),
            "id": t.get("index"),
            PRIMARY: local[i].get(PRIMARY),
            "amp_volatility": local[i].get("amp_volatility"),
            "shape_shift": cross[i].get("shape_shift"),
            "change_rate": cross[i].get("change_rate"),
            "mean_amplitude": float(np.mean(amps)) if amps else float("nan"),
            "rssi": float(np.mean(rssi)) if rssi else float("nan"),
            "payload_frames": len(samples),
            "payload_rate": (len(samples) / float(t.get("sensor_span_s") or 1)),
        })
    return rows


def paired(rows, feature):
    by = {}
    for r in rows:
        by.setdefault(r["block"], {})[r["label"]] = r[feature]
    diffs = []
    for b in sorted(by):
        if "hand" in by[b] and "stationary" in by[b]:
            diffs.append(by[b]["hand"] - by[b]["stationary"])
    return diffs


# --- main ------------------------------------------------------------------

def analyse(session):
    trials = payload_only(session.get("trials", []))
    design = validate_design(trials)
    trial_problems = validate_trials(trials)
    raw_problems = validate_raw(session.get("raw") or
                                (session.get("path", "") + ".raw"))
    rows = trial_features(trials) if not (design or trial_problems) else []

    out = {
        "preregistration": {
            "blocks": BLOCKS, "trial_s": TRIAL_S, "primary": PRIMARY,
            "test": "exact within-block sign-flip, two-sided",
            "assignments": 1 << BLOCKS, "p_gate": P_GATE,
            "d_gate": D_GATE, "bonferroni_secondary": BONFERRONI,
        },
        "design_problems": design,
        "trial_problems": trial_problems,
        "raw_problems": raw_problems,
    }
    if design or trial_problems or raw_problems:
        out["verdict"] = "INVALID"
        out["reason"] = "session failed a pre-registered validity rule"
        return out

    rates = {"stationary": [], "hand": []}
    dominant = {"stationary": [], "hand": []}
    for t in trials:
        n = len(t["samples"])
        rates[t["label"]].append(n / float(t["sensor_span_s"]))
        c = {}
        for x in t["samples"]:
            c[x.get("rate")] = c.get(x.get("rate"), 0) + 1
        dominant[t["label"]].append(max(c, key=c.get) if c else None)
    rate_s = float(np.median(rates["stationary"]))
    rate_h = float(np.median(rates["hand"]))
    rate_diff = abs(rate_h - rate_s) / rate_s if rate_s else float("inf")
    dom_ok = set(dominant["stationary"]) == set(dominant["hand"])

    out["confounds"] = {
        "payload_rate_stationary": rate_s,
        "payload_rate_hand": rate_h,
        "payload_rate_rel_diff": rate_diff,
        "dominant_phy_stationary": sorted(set(dominant["stationary"])),
        "dominant_phy_hand": sorted(set(dominant["hand"])),
        "rate_ok": rate_diff <= RATE_TOLERANCE,
        "phy_ok": dom_ok,
    }

    def test(feature):
        d = paired(rows, feature)
        p, hits, total = signflip_p(d)
        dz, ci = paired_dz(d)
        return {"diffs": [round(x, 6) for x in d], "p": p,
                "hits": hits, "assignments": total, "dz": dz,
                "ci95": list(ci), "mean_diff": float(np.mean(d))}

    out["primary"] = test(PRIMARY)
    out["secondary"] = {f: test(f) for f in SECONDARY}

    if not (out["confounds"]["rate_ok"] and out["confounds"]["phy_ok"]):
        out["verdict"] = "INCONCLUSIVE"
        out["reason"] = ("payload rate or PHY rate differs between "
                         "conditions; a sampling artifact cannot be excluded")
        return out
    p = out["primary"]["p"]
    dz = out["primary"]["dz"]
    lo = out["primary"]["ci95"][0]
    if p <= P_GATE and abs(dz) >= D_GATE and lo > 0:
        out["verdict"] = "PASS"
        out["reason"] = (f"exact p={p:.5f} <= {P_GATE}, d_z={dz:.2f}, "
                         f"bootstrap lower bound {lo:.2f} > 0")
    else:
        out["verdict"] = "FAIL"
        out["reason"] = (f"p={p:.5f}, d_z={dz:.2f}, CI lower {lo:.2f}; "
                         "the pre-registered criteria were not met")
    out["rows"] = rows
    return out


def show(result):
    print(f"verdict: {result['verdict']} - {result.get('reason','')}")
    for k in ("design_problems", "trial_problems", "raw_problems"):
        for p in result.get(k) or []:
            print(f"  {k}: {p}")
    if "confounds" in result:
        c = result["confounds"]
        print(f"\nconfounds: rate stationary {c['payload_rate_stationary']:.2f}/s"
              f"  hand {c['payload_rate_hand']:.2f}/s"
              f"  ({c['payload_rate_rel_diff']*100:.1f}% apart, "
              f"{'ok' if c['rate_ok'] else 'FAIL'})")
        print(f"           dominant PHY stationary {c['dominant_phy_stationary']}"
              f"  hand {c['dominant_phy_hand']}"
              f"  ({'ok' if c['phy_ok'] else 'FAIL'})")
    if "primary" in result:
        p = result["primary"]
        print(f"\nprimary {PRIMARY}: p={p['p']:.5f} "
              f"({p['hits']}/{p['assignments']})  d_z={p['dz']:.2f} "
              f"CI [{p['ci95'][0]:.2f}, {p['ci95'][1]:.2f}]  "
              f"mean diff {p['mean_diff']:+.5f}")
        print("  paired differences:", p["diffs"])
        print(f"\nsecondary (Bonferroni alpha={BONFERRONI:.4f}):")
        for f, r in result["secondary"].items():
            print(f"  {f:16s} p={r['p']:.5f}  d_z={r['dz']:+.2f}  "
                  f"CI [{r['ci95'][0]:+.2f}, {r['ci95'][1]:+.2f}]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    with open(args.session, encoding="utf-8") as fh:
        session = json.load(fh)
    session["path"] = args.session
    result = analyse(session)
    show(result)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1, default=str)
        print(f"\nwrote {args.out}")
    return 0 if result["verdict"] in ("PASS", "FAIL", "INCONCLUSIVE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
