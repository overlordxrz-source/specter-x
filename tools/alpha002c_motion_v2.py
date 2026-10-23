#!/usr/bin/env python3
"""Alpha 002-C motion preregistration v2 — the frozen analysis.

One command, written before the data. It either reports a verdict under the
pre-registered rules or refuses with a reason. No option changes the
statistics.

Design: 10 randomised blocks, each with one ``stationary`` and one ``hand``
trial. The primary test is an **exact one-sided within-block sign-flip** on
the paired differences, in the pre-registered direction (hand rougher than
stationary): 2^10 = 1 024 assignments, floor 1/1 024 = 0.00098, so the 0.01
gate is attainable. The six-block design could not reach 0.01 (floor
0.03125 two-sided).

Power, stated honestly: with 10 pairs and alpha = 0.01 the exact test has
about 29 % power at d_z = 0.8, 46 % at 1.0, 65 % at 1.2 and 80 % at 1.4.
This design is powered for a large paired effect; it is not powered to rule
out a moderate one, and a FAIL is reported as such.

Fail-closed: any invalid or malformed field, wrong design, short or overly
long trial, non-finite statistic, queue/clock/late anomaly, empty raw, or a
malformed CSI record after the first valid one -> INVALID, no verdict.
Rate/PHY differences -> INCONCLUSIVE.

    python3 tools/alpha002c_motion_v2.py runs/.../session.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.analysis import (crossfit_features,   # noqa: E402
                                            extract_features)
from specter.sensors.esp32.dispatcher import CsiParser             # noqa: E402
from specter.sensors.esp32.experiment import trials_from_json      # noqa: E402

BLOCKS = 10
TRIALS_PER_BLOCK = 2
TRIAL_S = 25.0
TRIAL_TOLERANCE_S = 0.5
MIN_PAYLOAD = 225                  # 9/s over 25 s
RATE_MIN, RATE_MAX = 8.5, 11.5
RATE_TOLERANCE = 0.10
P_GATE = 0.01
D_GATE = 0.8
PRIMARY = "roughness_used"
SECONDARY = ("amp_volatility", "shape_shift", "mean_amplitude", "rssi")
DESCRIPTIVE = ("change_rate",)     # label-fitted floor; no p-value
BONFERRONI = 0.05 / len(SECONDARY)


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


# --- statistics ------------------------------------------------------------

def signflip_p(diffs):
    """Exact ONE-SIDED sign-flip p in the pre-registered direction.

    The statistic is the mean paired difference; the alternative is
    ``hand > stationary``. Enumerating all 2^n assignments makes the floor
    1/2^n, not an approximation.
    """
    d = np.asarray(diffs, dtype=float)
    if d.size == 0 or not np.all(np.isfinite(d)):
        return float("nan"), 0, 0
    obs = float(d.mean())
    total = 1 << d.size
    hits = 0
    for bits in range(total):
        signs = np.array([1.0 if (bits >> i) & 1 else -1.0
                          for i in range(d.size)])
        if float((signs * d).mean()) >= obs - 1e-12:
            hits += 1
    return hits / total, hits, total


def paired_dz(diffs, n_boot=2000, seed=0):
    """Paired Cohen's d_z, with infinities for zero-variance separation."""
    d = np.asarray(diffs, dtype=float)
    if d.size < 2 or not np.all(np.isfinite(d)):
        return float("nan"), (float("nan"), float("nan"))
    mean = float(d.mean())
    sd = float(d.std(ddof=1))
    if sd == 0:
        if mean > 0:
            return float("inf"), (float("inf"), float("inf"))
        if mean < 0:
            return float("-inf"), (float("-inf"), float("-inf"))
        return float("nan"), (float("nan"), float("nan"))
    dz = mean / sd
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        s = d[rng.integers(0, d.size, d.size)]
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
        nt = dict(t)
        nt["samples"] = [x for x in s
                         if int(x.get("sig_len", 0)) >= min_sig_len]
        out.append(nt)
    return out


GEOMETRY_FIELDS = {
    "distance_m": (1.45, 1.55),
    "phone_height_m": (0.75, 0.85),
    "esp32_height_m": (0.75, 0.85),
    # Amendment 1: S is centred longitudinally and offset laterally.
    "spot_longitudinal_m": (-0.05, 0.05),
    "spot_lateral_m": (0.25, 0.35),
}
GEOMETRY_TEXT = ("phone_orientation", "recorded_utc", "confirmed_by",
                 "method")
#: Amendment 3: a declared-estimate class, recorded as such. It widens the
#: geometry tolerances only; no statistical rule changes.
GEOMETRY_CLASSES = {
    "measured": {"distance": (1.45, 1.55), "height": (0.75, 0.85),
                 "long": (-0.05, 0.05), "lat": (0.25, 0.35),
                 "radial": (0.25, 0.36), "min_dist": 0.70,
                 "consistency": 0.03},
    "estimated": {"distance": (1.30, 1.70), "height": (0.60, 1.00),
                  "long": (-0.15, 0.15), "lat": (0.18, 0.42),
                  "radial": (0.18, 0.42), "min_dist": 0.60,
                  "consistency": 0.10},
}
#: HORIZONTAL (floor-plane) distances from the S mark to the floor
#: projections of each antenna. Not the 3D slant: at 0.8 m height the slant
#: is ~1.14 m and must never be entered here.
GEOMETRY_DERIVED = ("s_phone_horizontal_m", "s_esp32_horizontal_m")


def validate_geometry(session):
    """The exact geometry is a recorded session fact, not an assumption.

    The protocol fixes the permitted ranges; the operator records the
    measured values immediately before GO. The analysis refuses without it.
    """
    geo = session.get("geometry")
    if not isinstance(geo, dict):
        return ["geometry record missing (no session geometry)"]
    problems = []
    accuracy = geo.get("accuracy")
    if accuracy not in GEOMETRY_CLASSES:
        return [f"geometry accuracy must be one of "
                f"{sorted(GEOMETRY_CLASSES)}, got {accuracy!r}"]
    cls = GEOMETRY_CLASSES[accuracy]
    ranges = {
        "distance_m": cls["distance"],
        "phone_height_m": cls["height"],
        "esp32_height_m": cls["height"],
        "spot_longitudinal_m": cls["long"],
        "spot_lateral_m": cls["lat"],
    }
    for k, (lo, hi) in ranges.items():
        v = geo.get(k)
        if not _finite(v):
            problems.append(f"geometry {k} is not finite ({v!r})")
        elif not (lo <= float(v) <= hi):
            problems.append(f"geometry {k}={v} outside [{lo}, {hi}] "
                            f"for the {accuracy} class")
    for k in GEOMETRY_TEXT:
        if not geo.get(k):
            problems.append(f"geometry {k} missing")
    for k in GEOMETRY_DERIVED:
        if not _finite(geo.get(k)):
            problems.append(f"geometry {k} is not finite ({geo.get(k)!r})")
    # geometric consistency: recompute S-to-antenna distances from L, long, lat
    if not problems:
        L = float(geo["distance_m"])
        lon = float(geo["spot_longitudinal_m"])
        lat = float(geo["spot_lateral_m"])
        radial = math.hypot(lon, lat)
        rlo, rhi = cls["radial"]
        if not (rlo <= radial <= rhi):
            problems.append(f"geometry radial offset {radial:.3f} m outside "
                            f"[{rlo}, {rhi}]")
        d_phone = math.hypot(L / 2.0 + lon, lat)
        d_esp = math.hypot(L / 2.0 - lon, lat)
        if min(d_phone, d_esp) < cls["min_dist"]:
            problems.append(f"geometry places S closer than "
                            f"{cls['min_dist']} m to an antenna")
        for k, d in (("s_phone_horizontal_m", d_phone),
                     ("s_esp32_horizontal_m", d_esp)):
            if abs(float(geo[k]) - d) > cls["consistency"]:
                problems.append(f"geometry {k}={geo[k]} disagrees with the "
                                f"horizontal L/long/lat value ({d:.3f} m) "
                                f"beyond the {accuracy} tolerance")
    return problems


def _derived_geometry(geo):
    """Horizontal and 3D slant distances, for the record only.

    The horizontal values are the ones measured and validated. The slant is
    computed from the antenna height so a 1.14 m slant cannot be mistaken
    for a 0.81 m plan distance.
    """
    if not isinstance(geo, dict):
        return None
    try:
        L = float(geo["distance_m"])
        lon = float(geo["spot_longitudinal_m"])
        lat = float(geo["spot_lateral_m"])
        hp = float(geo["phone_height_m"])
        he = float(geo["esp32_height_m"])
    except (KeyError, TypeError, ValueError):
        return None
    dp = math.hypot(L / 2 + lon, lat)
    de = math.hypot(L / 2 - lon, lat)
    return {"s_phone_horizontal_m": round(dp, 4),
            "s_esp32_horizontal_m": round(de, 4),
            "s_phone_slant_3d_m": round(math.hypot(dp, hp), 4),
            "s_esp32_slant_3d_m": round(math.hypot(de, he), 4)}


def validate_design(trials, session):
    problems = []
    if len(trials) != BLOCKS * TRIALS_PER_BLOCK:
        problems.append(f"{len(trials)} trials, expected "
                        f"{BLOCKS * TRIALS_PER_BLOCK}")
    blocks = []
    by = {}
    for t in trials:
        b = t.get("block")
        if not isinstance(b, int) or isinstance(b, bool):
            problems.append(f"block is not an int: {b!r}")
            continue
        blocks.append(b)
        by.setdefault(b, []).append((t.get("label"), t.get("index")))
    if sorted(set(blocks)) != list(range(BLOCKS)):
        problems.append(f"blocks {sorted(set(blocks))}, expected 0..{BLOCKS-1}")
    stationary_first = 0
    for b, items in by.items():
        labels = sorted(x[0] for x in items)
        if labels != ["hand", "stationary"]:
            problems.append(f"block {b} labels {labels}")
            continue
        first = min(items, key=lambda x: (x[1] is None, x[1]))
        stationary_first += int(first[0] == "stationary")
    # a fixed within-block order is a drift confound; both orders must occur
    if by and not (2 <= stationary_first <= len(by) - 2):
        problems.append(f"within-block order degenerate: {stationary_first}"
                        f"/{len(by)} blocks stationary-first")
    design = session.get("design") or {}
    if "seed" not in design:
        problems.append("design metadata has no seed")
    return problems


def validate_trials(trials):
    problems = []
    for i, t in enumerate(trials, 1):
        if t.get("valid") is not True:
            problems.append(f"trial {i}: valid is not True "
                            f"({t.get('valid')!r})")
        s = t.get("samples") or []
        n = len(s)
        if n < MIN_PAYLOAD:
            problems.append(f"trial {i}: {n} payload frames < {MIN_PAYLOAD}")
        active = t.get("active_s")
        span = t.get("sensor_span_s")
        sample_span = t.get("sample_span_s")
        for name, v in (("active_s", active), ("sensor_span_s", span),
                        ("sample_span_s", sample_span),
                        ("max_sensor_gap_s", t.get("max_sensor_gap_s")),
                        ("boundary_uncertainty_s",
                         t.get("boundary_uncertainty_s"))):
            if not _finite(v):
                problems.append(f"trial {i}: {name} is not finite ({v!r})")
        if _finite(active) and abs(float(active) - TRIAL_S) > TRIAL_TOLERANCE_S:
            problems.append(f"trial {i}: active {active} != {TRIAL_S}±"
                            f"{TRIAL_TOLERANCE_S}")
        if _finite(span) and abs(float(span) - TRIAL_S) > TRIAL_TOLERANCE_S:
            problems.append(f"trial {i}: sensor span {span} != {TRIAL_S}±"
                            f"{TRIAL_TOLERANCE_S}")
        if _finite(active) and _finite(span) and \
                abs(float(span) - float(active)) > TRIAL_TOLERANCE_S:
            problems.append(f"trial {i}: span {span} vs active {active}")
        if _finite(active) and _finite(sample_span) and \
                abs(float(sample_span) - float(active)) > TRIAL_TOLERANCE_S:
            problems.append(f"trial {i}: sample span {sample_span} vs active "
                            f"{active}")
        if _finite(sample_span) and float(sample_span) > 0:
            rate = n / float(sample_span)
            if not (RATE_MIN <= rate <= RATE_MAX):
                problems.append(f"trial {i}: payload rate {rate:.2f}/s")
        if _finite(t.get("max_sensor_gap_s")) and \
                float(t["max_sensor_gap_s"]) > 0.5:
            problems.append(f"trial {i}: sensor gap {t['max_sensor_gap_s']}")
        if _finite(t.get("boundary_uncertainty_s")) and \
                float(t["boundary_uncertainty_s"]) > 0.10:
            problems.append(f"trial {i}: uncertainty "
                            f"{t['boundary_uncertainty_s']}")
        if t.get("clock_resets") not in (0, None):
            problems.append(f"trial {i}: clock resets {t.get('clock_resets')}")
        if t.get("late_frames") not in (0, None):
            problems.append(f"trial {i}: late frames {t.get('late_frames')}")
    return problems


def validate_raw(session, trials):
    path = session.get("raw")
    if not path or not os.path.exists(path):
        return [f"raw stream missing: {path}"]
    if os.path.getsize(path) == 0:
        return [f"raw stream is empty: {path}"]
    lines = open(path, "rb").read().decode("utf-8", "replace").splitlines()
    parser = CsiParser()
    seen_valid = False
    csi_lines = 0
    torn = 0
    problems = []
    for i, l in enumerate(lines):
        if not l.startswith("CSI_DATA"):
            continue
        outcome = parser.feed_resilient(l)
        if outcome.malformed:
            torn += 1
            # The frozen rule allows at most the first (startup) torn line:
            # opening the port mid-record can leave a partial prefix on the
            # same physical line as the first full record. A torn line before
            # any valid record is that startup line; a later one is corruption.
            # See docs/design/alpha002c-analysis-correction-01.md.
            if torn > 1:
                problems.append(
                    f"malformed CSI line {i} after the first torn line")
            elif seen_valid:
                problems.append(
                    f"malformed CSI line {i} after the first record")
        if outcome.records:
            csi_lines += sum(1 for _ in outcome.records)
            seen_valid = True
    if session.get("malformed") not in (0, 1, None):
        problems.append(f"recorder counted {session.get('malformed')} "
                        "malformed lines")
    if session.get("clock_resets") not in (0, None):
        problems.append("recorder counted a clock reset")
    late = session.get("late_frames") or {}
    if isinstance(late, dict) and any(v for v in late.values()):
        problems.append(f"late in-window frames: {late}")
    payload = sum(len(t.get("samples") or []) for t in trials)
    if csi_lines < payload:
        problems.append(f"raw has {csi_lines} CSI records for {payload} "
                        "selected frames")
    return problems


# --- features --------------------------------------------------------------

def trial_features(trials):
    base = trials_from_json({"trials": trials})
    local = extract_features(base)
    cross = crossfit_features(base)
    rows = []
    for i, t in enumerate(trials):
        s = t["samples"]
        amps = [sum(x.get("amplitudes") or []) for x in s]
        rssi = [x.get("rssi") for x in s if x.get("rssi") is not None]
        span = float(t.get("sample_span_s") or 0.0)
        rows.append({
            "label": t.get("label"), "block": t.get("block"),
            "index": t.get("index"),
            PRIMARY: local[i].get(PRIMARY),
            "amp_volatility": local[i].get("amp_volatility"),
            "shape_shift": cross[i].get("shape_shift"),
            "change_rate": cross[i].get("change_rate"),
            "mean_amplitude": float(np.mean(amps)) if amps else float("nan"),
            "rssi": float(np.mean(rssi)) if rssi else float("nan"),
            "payload_frames": len(s),
            "payload_rate": (len(s) / span) if span > 0 else float("nan"),
        })
    return rows


def paired(rows, feature):
    by = {}
    for r in rows:
        by.setdefault(r["block"], {})[r["label"]] = r[feature]
    return [by[b]["hand"] - by[b]["stationary"] for b in sorted(by)
            if "hand" in by[b] and "stationary" in by[b]]


# --- main ------------------------------------------------------------------

def analyse(session):
    trials = payload_only(session.get("trials", []))
    design = validate_design(trials, session)
    geometry = validate_geometry(session)
    trial_problems = validate_trials(trials)
    raw_problems = validate_raw(session, trials)
    base_problems = design or geometry or trial_problems or raw_problems

    out = {
        "preregistration": {
            "blocks": BLOCKS, "trial_s": TRIAL_S, "primary": PRIMARY,
            "test": "exact one-sided within-block sign-flip (hand > stationary)",
            "assignments": 1 << BLOCKS, "floor": 1 / (1 << BLOCKS),
            "p_gate": P_GATE, "d_gate": D_GATE,
            "bonferroni_secondary": BONFERRONI,
            "power_note": ("~29% at d_z=0.8, 46% at 1.0, 65% at 1.2, "
                           "80% at 1.4"),
        },
        "design_problems": design,
        "geometry_problems": geometry,
        "geometry": session.get("geometry"),
        "geometry_accuracy": (session.get("geometry") or {}).get("accuracy")
        if isinstance(session.get("geometry"), dict) else None,
        "geometry_derived": _derived_geometry(session.get("geometry")),
        "trial_problems": trial_problems,
        "raw_problems": raw_problems,
    }
    if base_problems:
        out["verdict"] = "INVALID"
        out["reason"] = "session failed a pre-registered validity rule"
        return out

    rows = trial_features(trials)
    out["trials"] = rows

    # confounds, computed over payload frames
    rate = {"stationary": [], "hand": []}
    phy = {"stationary": {}, "hand": {}}
    for t in trials:
        rate[t["label"]].append(len(t["samples"]) /
                                float(t["sample_span_s"]))
        for x in t["samples"]:
            r = x.get("rate")
            if r is None:
                out["verdict"] = "INVALID"
                out["reason"] = "payload frame without a PHY rate"
                return out
            phy[t["label"]][r] = phy[t["label"]].get(r, 0) + 1
    rate_s = float(np.median(rate["stationary"]))
    rate_h = float(np.median(rate["hand"]))
    rate_diff = abs(rate_h - rate_s) / rate_s if rate_s else float("inf")
    modal = {}
    conc = {}
    for lab in ("stationary", "hand"):
        total = sum(phy[lab].values())
        modal[lab] = max(phy[lab], key=phy[lab].get) if total else None
        conc[lab] = (phy[lab].get(modal[lab], 0) / total) if total else 0.0
    phy_ok = (modal["stationary"] == modal["hand"]
              and conc["stationary"] >= 0.9 and conc["hand"] >= 0.9)
    out["confounds"] = {
        "payload_rate_stationary": rate_s,
        "payload_rate_hand": rate_h,
        "payload_rate_rel_diff": rate_diff,
        "modal_phy": modal, "modal_concentration": conc,
        "rate_ok": rate_diff <= RATE_TOLERANCE, "phy_ok": phy_ok,
    }

    def test(feature):
        d = paired(rows, feature)
        if not d or not all(_finite(x) for x in d):
            return {"p": None, "diffs": d, "dz": None,
                    "ci95": [None, None], "mean_diff": None}
        p, hits, total = signflip_p(d)
        dz, ci = paired_dz(d)
        return {"diffs": [round(x, 6) for x in d], "p": p, "hits": hits,
                "assignments": total, "dz": dz, "ci95": list(ci),
                "mean_diff": float(np.mean(d))}

    out["primary"] = test(PRIMARY)
    out["secondary"] = {f: test(f) for f in SECONDARY}
    out["descriptive"] = {f: test(f) for f in DESCRIPTIVE}

    if not (out["confounds"]["rate_ok"] and out["confounds"]["phy_ok"]):
        out["verdict"] = "INCONCLUSIVE"
        out["reason"] = ("payload-rate or PHY-rate difference between "
                         "conditions; a sampling artifact cannot be excluded")
        return out
    pr = out["primary"]
    if pr["p"] is None or not _finite(pr["dz"]):
        out["verdict"] = "INVALID"
        out["reason"] = "primary statistic is not finite"
        return out
    if pr["p"] <= P_GATE and pr["dz"] >= D_GATE and pr["ci95"][0] > 0:
        out["verdict"] = "PASS"
        out["reason"] = (f"one-sided p={pr['p']:.5f} <= {P_GATE}, "
                         f"d_z={pr['dz']:.2f}, CI lower {pr['ci95'][0]:.2f}")
    else:
        out["verdict"] = "FAIL"
        out["reason"] = (f"p={pr['p']:.5f}, d_z={pr['dz']:.2f}, "
                         f"CI lower {pr['ci95'][0]:.2f}; criteria not met")
    return out


def show(result):
    print(f"verdict: {result['verdict']} - {result.get('reason','')}")
    if result.get("geometry_accuracy"):
        print(f"geometry: {result['geometry_accuracy']} "
              "(estimated values are labelled and must not be read as "
              "verified measurements)")
    for k in ("design_problems", "geometry_problems", "trial_problems",
              "raw_problems"):
        for p in result.get(k) or []:
            print(f"  {k}: {p}")
    if "confounds" in result:
        c = result["confounds"]
        print(f"\nconfounds: rate {c['payload_rate_stationary']:.2f} vs "
              f"{c['payload_rate_hand']:.2f}/s "
              f"({c['payload_rate_rel_diff']*100:.1f}%, "
              f"{'ok' if c['rate_ok'] else 'FAIL'})")
        print(f"           modal PHY {c['modal_phy']} "
              f"concentration {c['modal_concentration']} "
              f"({'ok' if c['phy_ok'] else 'FAIL'})")
    if "primary" in result:
        p = result["primary"]
        print(f"\nprimary {PRIMARY}: p={p['p']} ({p['hits']}/{p['assignments']})"
              f"  d_z={p['dz']}  CI {p['ci95']}  mean {p['mean_diff']}")
        print("  paired differences:", p["diffs"])
        print(f"\nsecondary (Bonferroni alpha={BONFERRONI:.4f}):")
        for f, r in result["secondary"].items():
            print(f"  {f:16s} p={r['p']}  d_z={r['dz']}")
        print("\ndescriptive (no p; label-fitted secondary):")
        for f, r in result["descriptive"].items():
            print(f"  {f:16s} diffs={r['diffs']}")
        print("\nper-trial:")
        for r in result["trials"]:
            print(f"  b{r['block']:>2} {r['label']:>10} "
                  f"frames {r['payload_frames']:>4} rate {r['payload_rate']:5.2f}"
                  f" rough {r[PRIMARY]:.5f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    with open(args.session, encoding="utf-8") as fh:
        session = json.load(fh)
    sidecar = args.session + ".geometry.json"
    if "geometry" not in session and os.path.exists(sidecar):
        with open(sidecar, encoding="utf-8") as fh:
            session["geometry"] = json.load(fh)
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
