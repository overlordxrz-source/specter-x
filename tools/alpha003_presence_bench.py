#!/usr/bin/env python3
"""Alpha 003 synthetic-only presence benchmark.

Run the offline feature/evaluation machinery on a three-condition synthetic
link. The output is **not** evidence that a person can be detected: it tests
the code path, the grouped evaluation and the confound ablations against a
known synthetic truth. It never reads a human session.
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
    FEATURE_SETS, evaluate)
from specter.sensors.esp32.presence_synthetic import (  # noqa: E402
    PresenceSyntheticLink)


def _summary(r):
    return {
        "balanced_accuracy": round(r["balanced_accuracy"], 4),
        "ci95": [round(x, 4) for x in r["ci"]["balanced_accuracy"]],
        "empty_false_positive_rate": round(r["empty_false_positive_rate"], 4),
        "per_class_recall": {k: round(v, 4)
                             for k, v in r["per_class_recall"].items()},
        "posture_stationary_recall": r.get("stationary_recall_by_posture"),
        "session_sign_test": r.get("session_sign_test"),
        "auc": (round(r["auc"], 4) if "auc" in r else None),
        "null": ({k: (round(v, 4) if isinstance(v, float) else v)
                  for k, v in r["null"].items()} if "null" in r else None),
        "n": r["n"], "n_sessions": r["n_sessions"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--blocks", type=int, default=8)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--rate-hz", type=float, default=20.0)
    ap.add_argument("--static-effect", type=float, default=0.08)
    ap.add_argument("--moving-effect", type=float, default=0.85)
    ap.add_argument("--breathing-phase", type=float, default=0.035)
    ap.add_argument("--noise", type=float, default=0.018)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--permutations", type=int, default=100)
    ap.add_argument("--bootstrap", type=int, default=300)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    link = PresenceSyntheticLink(
        static_effect=args.static_effect,
        moving_effect=args.moving_effect,
        breathing_phase=args.breathing_phase,
        noise=args.noise, rate_hz=args.rate_hz, seed=args.seed)
    data = link.make_dataset(n_sessions=args.sessions, blocks=args.blocks,
                             seconds=args.seconds)

    contrasts = {
        "empty_vs_moving": ("empty", "moving"),
        "empty_vs_stationary": ("empty", "stationary"),
        "empty_stationary_moving": ("empty", "stationary", "moving"),
    }
    results = {}
    for cname, classes in contrasts.items():
        results[cname] = {}
        for fname, features in FEATURE_SETS.items():
            r = evaluate(data, classes, features,
                         n_perm=(args.permutations if fname == "all" else 0),
                         seed=args.seed, n_boot=args.bootstrap)
            results[cname][fname] = _summary(r)

    report = {
        "kind": "synthetic-benchmark",
        "disclaimer": ("Synthetic truth only. This is not evidence of "
                       "human presence, occupancy, respiration or "
                       "localization. It tests the offline pipeline."),
        "config": {
            "sessions": args.sessions, "blocks": args.blocks,
            "seconds": args.seconds, "rate_hz": args.rate_hz,
            "static_effect": args.static_effect,
            "moving_effect": args.moving_effect,
            "breathing_phase": args.breathing_phase,
            "noise": args.noise, "seed": args.seed,
            "permutations": args.permutations,
            "bootstrap": args.bootstrap,
        },
        "dataset": {
            "n_trials": len(data),
            "n_sessions": args.sessions,
            "conditions": {c: sum(1 for t in data if t["label"] == c)
                           for c in ("empty", "stationary", "moving")},
        },
        "results": results,
    }
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({
        "kind": report["kind"],
        "dataset": report["dataset"],
        "summary": {
            c: {f: {"bal": v["balanced_accuracy"],
                    "fpr": v["empty_false_positive_rate"],
                    "null_p": (v["null"] or {}).get("p")}
                for f, v in sets.items()}
            for c, sets in results.items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
