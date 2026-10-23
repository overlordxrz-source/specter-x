#!/usr/bin/env python3
"""Alpha 003 recorded-session analysis (offline only).

Loads one or more Alpha-style session JSON files whose labels are
``empty``/``stationary``/``moving``, attaches raw IQ when ``<session>.raw``
exists, and runs the same session-independent evaluation as the synthetic
benchmark.

This script does not acquire data and does not make a presence claim. It
refuses labels outside the Alpha 003 conditions so an Alpha 002-C
stationary/hand session cannot be silently relabelled as occupancy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from specter.sensors.esp32.presence import (  # noqa: E402
    CONDITIONS, FEATURE_SETS, evaluate, load_session, trial_qc)


def _summary(r):
    return {
        "balanced_accuracy": round(r["balanced_accuracy"], 4),
        "ci95": [round(x, 4) for x in r["ci"]["balanced_accuracy"]],
        "empty_false_positive_rate": round(r["empty_false_positive_rate"], 4),
        "per_class_recall": {k: round(v, 4)
                             for k, v in r["per_class_recall"].items()},
        "posture_stationary_recall": r.get("stationary_recall_by_posture"),
        "auc": (round(r["auc"], 4) if "auc" in r else None),
        "null": ({k: (round(v, 4) if isinstance(v, float) else v)
                  for k, v in r["null"].items()} if "null" in r else None),
        "n": r["n"], "n_sessions": r["n_sessions"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", action="append", required=True,
                    help="session.json; <session>.raw is used if present")
    ap.add_argument("--permutations", type=int, default=100)
    ap.add_argument("--bootstrap", type=int, default=500)
    ap.add_argument("--trial-s", type=float, default=30.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    data = []
    excluded = []
    for path in args.session:
        raw = path + ".raw"
        trials = load_session(path, raw_path=(raw if Path(raw).exists()
                                              else None))
        labels = {t["label"] for t in trials}
        unknown = labels - set(CONDITIONS)
        if unknown:
            raise SystemExit(
                f"{path}: labels {sorted(unknown)} are not Alpha 003 "
                f"conditions {CONDITIONS}; refusing to relabel")
        for t in trials:
            problems = trial_qc(t, requested_s=args.trial_s)
            if problems:
                excluded.append({"session": path, "index": t.get("index"),
                                 "label": t.get("label"),
                                 "problems": problems})
            else:
                data.append(t)
    if not data:
        raise SystemExit(f"no valid Alpha 003 trials; exclusions: {excluded}")

    present = {t["label"] for t in data}
    contrasts = {}
    if {"empty", "moving"} <= present:
        contrasts["empty_vs_moving"] = ("empty", "moving")
    if {"empty", "stationary"} <= present:
        contrasts["empty_vs_stationary"] = ("empty", "stationary")
    if set(CONDITIONS) <= present:
        contrasts["empty_stationary_moving"] = CONDITIONS
    if not contrasts:
        raise SystemExit(f"need at least empty+stationary or empty+moving; "
                         f"found {sorted(present)}")

    results = {}
    for cname, classes in contrasts.items():
        results[cname] = {}
        for fname, features in FEATURE_SETS.items():
            r = evaluate(data, classes, features,
                         n_perm=(args.permutations if fname == "all" else 0),
                         seed=0, n_boot=args.bootstrap)
            results[cname][fname] = _summary(r)
        if cname == "empty_vs_stationary":
            r = evaluate(data, classes, FEATURE_SETS["all"],
                         n_perm=0, seed=0, n_boot=args.bootstrap,
                         calibration="session_empty")
            results[cname]["all_session_empty_calibration"] = _summary(r)

    report = {
        "kind": "recorded-session-analysis",
        "synthetic": False,
        "disclaimer": ("Offline analysis only. A result is not a presence "
                       "claim until the Alpha 003 preregistered gates and "
                       "independent replication are met."),
        "sessions": args.session,
        "conditions": {c: sum(1 for t in data if t["label"] == c)
                       for c in CONDITIONS},
        "excluded": excluded,
        "results": results,
    }
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
