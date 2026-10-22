#!/usr/bin/env python3
"""Replay a recorded Alpha 002-C session through the repaired analysis.

The recordings made before the audit are **acquisition-contaminated**: their
trial windows absorbed 43-55 s of sensor history. This tool does not repair
that - it cannot - and it does not pretend to. What it does is:

* report the sensor span of every trial, so the contamination is visible in
  the output rather than inferred by a reader;
* recompute the payload rate against **sensor time**, not against the
  reported wall duration;
* run the leakage-free, block-preserving analysis on the stored frames;
* mark the whole result as exploratory apparatus data, not a sensing claim.

    python3 tools/alpha002c_replay.py runs/.../phase1-main.json \
        --blocks 4 --out runs/.../phase1-replay.json
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

from specter.sensors.esp32.analysis import analyse_blinded  # noqa: E402
from specter.sensors.esp32.experiment import trials_from_json  # noqa: E402


def payload_only(trials, min_sig_len: int = 33):
    out = []
    for t in trials:
        samples = t.get("samples") or []
        if samples and not any("sig_len" in s for s in samples):
            out.append(t)
            continue
        keep = [s for s in samples if int(s.get("sig_len", 0)) >= min_sig_len]
        nt = dict(t)
        nt["samples"] = keep
        nt["payload_frames"] = len(keep)
        nt["null_frames"] = len(samples) - len(keep)
        out.append(nt)
    return out


def sensor_span(samples):
    ts = [int(s.get("local_timestamp", 0)) for s in samples]
    if not ts:
        return 0.0
    # unwrap a uint32 microsecond counter
    total = 0
    prev = ts[0]
    for v in ts[1:]:
        d = v - prev
        if d < -(1 << 31):
            d += 1 << 32
        total += d
        prev = v
    return total / 1e6


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("--blocks", type=int, default=0,
                    help="trials per acquisition block, if the recording "
                         "predates block ids (inferred, and said so)")
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--permutations", type=int, default=1000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    with open(args.path, encoding="utf-8") as fh:
        data = json.load(fh)
    trials = payload_only(data.get("trials", []))
    if args.blocks:
        for i, t in enumerate(trials):
            t["block"] = i // args.blocks
    blocks = [t.get("block") for t in trials]

    print(f"{'#':>2} {'label':>11} {'payload':>8} {'null':>6} "
          f"{'sensor s':>9} {'pay/sensor':>10} {'contam':>6}")
    for i, t in enumerate(trials, 1):
        s = t.get("samples") or []
        span = sensor_span(s)
        rate = (len(s) / span) if span > 0 else float("nan")
        req = float(t.get("requested_s") or 20.0)
        contam = span > req * 1.5
        t["sensor_span_s"] = round(span, 6)
        t["acquisition_contaminated"] = bool(contam)
        print(f"{i:>2} {t.get('label',''):>11} {len(s):>8} "
              f"{t.get('null_frames',0):>6} {span:>9.3f} {rate:>10.2f} "
              f"{('YES' if contam else 'no'):>6}")

    result = analyse_blinded(trials_from_json({"trials": trials}),
                             seed=args.seed, n_perm=args.permutations,
                             blocks=blocks if args.blocks else None)
    print("\nrepaired analysis (leakage-free, block-preserving):")
    print(f"  {'feature':>16} {'F':>9} {'perm p':>8} {'AUC':>7} "
          f"{'acc':>6} {'d':>7}")
    for name in ("roughness_used", "amp_volatility", "shape_shift",
                 "change_rate"):
        om = result["omnibus"][name]
        pm = result["permutation"][name]
        ho = result["held_out"][name]
        ef = result["effects"][name]
        pair = ef["pairs"].get("hand vs stationary", {})
        print(f"  {name:>16} {str(om['f']):>9} "
              f"{str(pm['empirical_p']):>8} {str(ho['held_out_auc']):>7} "
              f"{str(ho['held_out_accuracy']):>6} {str(pair.get('cohens_d')):>7}")

    out = {
        "source": os.path.abspath(args.path),
        "acquired_before_audit": True,
        "acquisition_contaminated": True,
        "note": ("trial windows absorbed a sensor backlog; the analysis is "
                 "repaired but the acquisition is not, so this is apparatus "
                 "data, not a sensing result"),
        "blocks_inferred": bool(args.blocks),
        "seed": args.seed,
        "n_permutations": args.permutations,
        "trials": [{"label": t.get("label"), "block": t.get("block"),
                    "payload_frames": len(t.get("samples") or []),
                    "null_frames": t.get("null_frames", 0),
                    "sensor_span_s": round(sensor_span(t.get("samples") or []), 6)}
                   for t in trials],
        "analysis": result,
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=str)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
