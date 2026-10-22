#!/usr/bin/env python3
"""The synthetic CSI sensitivity sweep.

The bench link (``specter.sensors.esp32.synthetic_link``) has a *known*
ground truth, so the detection pipeline can be characterised the way a real
link never allows:

* **the false-positive rate** - how often the procedure declares an effect
  when there is none. Measured, not assumed.
* **the power curve** - for each effect size, how often the procedure finds
  it. The effect size at which the power reaches 0.8 is the sensitivity of
  the whole pipeline.
* **the held-out accuracy** - leave-one-repetition-out, so the score is
  out of sample.

Every run is seeded from one master seed, so the whole sweep is
reproducible from the command line alone.

    python3 tools/esp32_csi_sweep.py --out runs/campaign/sweep
    python3 tools/esp32_csi_sweep.py --out runs/campaign/sweep --quick
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from typing import Dict, List

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.analysis import (FEATURE_NAMES, analyse_blinded,
                                            power_by_simulation, required_n)
from specter.sensors.esp32.synthetic_link import SyntheticLink

#: the feature the pipeline decides on. Frozen: this is the pre-registered
#: primary feature, and the sweep reports the others but does not pick
#: between them.
PRIMARY = "roughness_used"
ALPHA = 0.05


def one_experiment(effect: float, reps: int, seconds: float, seed: int,
                   labels=("stationary", "hand")) -> Dict:
    """One independent simulated experiment: build a set, blind it, analyse it."""
    link = SyntheticLink(effect=effect, seed=seed)
    trials = link.set(list(labels), repeats=reps, seconds=seconds)
    out = analyse_blinded(trials, seed=seed + 1, n_perm=200)
    om = out["omnibus"][PRIMARY]
    pe = out["permutation"][PRIMARY]
    ho = out["held_out"][PRIMARY]
    eff = out["effects"][PRIMARY]
    ds = [abs(v["cohens_d"]) for v in eff["pairs"].values()
          if v["cohens_d"] is not None]
    return {
        "effect": effect,
        "seed": seed,
        "f": om["f"],
        "p": om["p"],
        "permutation_p": pe["empirical_p"],
        "fpr_estimate": pe["false_positive_rate"],
        "held_out_accuracy": ho["held_out_accuracy"],
        "max_abs_d": max(ds) if ds else None,
        "significant": bool(om["p"] == om["p"] and om["p"] < ALPHA),
    }


def sweep(effects: List[float], n_runs: int, reps: int, seconds: float,
          seed: int) -> List[Dict]:
    """The sweep: for each effect size, many independent experiments."""
    rows = []
    for effect in effects:
        runs = []
        for r in range(n_runs):
            runs.append(one_experiment(effect, reps, seconds,
                                       seed + 1000 * r + int(effect * 1e6)))
        det = sum(1 for x in runs if x["significant"]) / len(runs)
        held = [x["held_out_accuracy"] for x in runs
                if x["held_out_accuracy"] is not None]
        ps = [x["p"] for x in runs if x["p"] == x["p"]]
        ds = [x["max_abs_d"] for x in runs if x["max_abs_d"] is not None]
        # the null band of the effect size: what |d| a random split of two
        # identical conditions produces. An observed d has to be judged
        # against this, not against zero.
        null_d = sorted(abs(x["max_abs_d"]) for x in runs
                        if x["max_abs_d"] is not None)
        band = None
        if null_d:
            band = {
                "median": round(statistics.median(null_d), 4),
                "p95": round(null_d[min(len(null_d) - 1,
                                         int(0.95 * len(null_d)))], 4),
                "max": round(null_d[-1], 4),
            }
        rows.append({
            "effect": effect,
            "n_runs": n_runs,
            "detection_rate": round(det, 4),
            "abs_d_null_band": band,
            "held_out_accuracy_mean": round(statistics.mean(held), 4)
            if held else None,
            "median_p": round(statistics.median(ps), 5) if ps else None,
            "median_max_abs_d": round(statistics.median(ds), 4) if ds else None,
            "mean_measured_fpr": round(statistics.mean(
                [x["fpr_estimate"] for x in runs]), 4),
            "runs": runs,
        })
        print(f"  effect {effect:>6.3f}  detection rate {det:>6.3f}  "
              f"held-out {rows[-1]['held_out_accuracy_mean']}  "
              f"median p {rows[-1]['median_p']}  median d {rows[-1]['median_max_abs_d']}"
              f"  null |d| band {band['p95'] if band else '-'}",
              flush=True)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="runs/campaign/sweep")
    ap.add_argument("--seed", type=int, default=20261022,
                    help="the master seed; every run derives from it")
    ap.add_argument("--runs", type=int, default=24,
                    help="independent experiments per effect size")
    ap.add_argument("--reps", type=int, default=5,
                    help="repetitions per condition in one experiment")
    ap.add_argument("--seconds", type=float, default=20.0,
                    help="seconds per trial")
    ap.add_argument("--effects", default="0,0.01,0.02,0.05,0.1,0.2,0.4")
    ap.add_argument("--quick", action="store_true",
                    help="a fast version for a smoke test")
    args = ap.parse_args(argv)

    if args.quick:
        args.runs, args.reps, args.seconds = 4, 3, 5.0
        args.effects = "0,0.05,0.2"

    effects = [float(x) for x in args.effects.split(",") if x.strip()]
    os.makedirs(args.out, exist_ok=True)

    print(f"synthetic CSI sweep: {len(effects)} effect sizes x {args.runs} runs, "
          f"{args.reps} repetitions per condition, {args.seconds:.0f}s per trial")
    print(f"  master seed {args.seed}; primary feature '{PRIMARY}'; "
          f"alpha {ALPHA}", flush=True)
    t0 = time.time()
    rows = sweep(effects, args.runs, args.reps, args.seconds, args.seed)
    elapsed = time.time() - t0

    # the false-positive rate is the null row's detection rate
    null = next((r for r in rows if r["effect"] == 0.0), None)
    fpr = null["detection_rate"] if null else None

    # the sensitivity: the smallest effect that reaches 80% power
    sensitive = next((r["effect"] for r in rows
                      if r["detection_rate"] >= 0.8), None)

    # what the measured effect sizes would need, in trials
    d_needed = required_n(0.95, k=2, target_power=0.8)

    report = {
        "preregistration": {
            "primary_feature": PRIMARY,
            "features": list(FEATURE_NAMES),
            "alpha": ALPHA,
            "conditions": ["stationary", "hand"],
            "decision_rule": "one-way ANOVA on the primary feature, p < alpha",
        },
        "seed": args.seed,
        "n_runs_per_effect": args.runs,
        "repetitions_per_condition": args.reps,
        "seconds_per_trial": args.seconds,
        "elapsed_s": round(elapsed, 1),
        "rows": rows,
        "false_positive_rate": fpr,
        "smallest_effect_with_80_percent_power": sensitive,
        "trials_needed_at_d_0_95": d_needed["n_per_group_needed"],
        "trials_needed_total": d_needed["total_trials_needed"],
    }
    with open(os.path.join(args.out, "sweep.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    with open(os.path.join(args.out, "sweep.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["effect", "n_runs", "detection_rate",
                    "held_out_accuracy_mean", "median_p", "median_max_abs_d",
                    "null_d_p95", "mean_measured_fpr"])
        for r in rows:
            w.writerow([r["effect"], r["n_runs"], r["detection_rate"],
                        r["held_out_accuracy_mean"], r["median_p"],
                        r["median_max_abs_d"],
                        (r.get("abs_d_null_band") or {}).get("p95"),
                        r["mean_measured_fpr"]])

    print(f"\n=== the sweep ===")
    print(f"  false-positive rate (null effect): {fpr}")
    print(f"  smallest effect with 80% power:    {sensitive}")
    if null and null.get("abs_d_null_band"):
        b = null["abs_d_null_band"]
        print(f"  the null |d| band at effect 0:     median {b['median']}, "
              f"95th percentile {b['p95']}")
        print("    (an observed effect size has to clear THIS, not zero)")
    print(f"  trials needed at d = 0.95:          "
          f"{d_needed['n_per_group_needed']} per condition "
          f"({d_needed['total_trials_needed']} total)")
    print(f"  report -> {os.path.join(args.out, 'sweep.json')}")
    print(f"  table  -> {os.path.join(args.out, 'sweep.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
