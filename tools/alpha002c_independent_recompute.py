#!/usr/bin/env python3
"""Independent minimal recomputation of the Alpha 002-C primary result.

This file deliberately does **not** import ``tools/alpha002c_motion_v2.py`` or
``specter.sensors.esp32.analysis``. It re-implements only the frozen primary
feature (``roughness_used``), the paired differences, the exact one-sided
sign-flip test and the seeded bootstrap interval from the trial JSON.

The purpose is a cross-check of the recorded result, not a new analysis or a
new feature. It reads the same raw-derived trial samples; it does not alter
them.
"""
from __future__ import annotations

import argparse
import json
import math
from typing import Any

import numpy as np

#: Canonical LLTF null slots (csi_analysis.EXPECTED_NULL): DC plus the
#: eleven guard/null positions. Kept as a literal so this file is independent.
EXPECTED_NULL = frozenset((0, *range(27, 38)))
MIN_SIG_LEN = 33          # payload-only, same frozen boundary
N_BOOT = 2000
SEED = 0


def _used_mask(width: int, first_word_invalid: bool) -> np.ndarray:
    mask = np.ones(int(width), dtype=bool)
    if int(width) == 64:
        for i in EXPECTED_NULL:
            if i < mask.size:
                mask[i] = False
    if first_word_invalid:
        mask[:2] = False
    return mask


def _payload(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in samples if int(s.get("sig_len", 0)) >= MIN_SIG_LEN]


def roughness(samples: list[dict[str, Any]]) -> tuple[float, int]:
    """Mean absolute change of the row-normalised spectrum between packets."""
    payload = _payload(samples)
    if len(payload) < 2:
        return float("nan"), len(payload)
    width = max(len(s.get("amplitudes") or []) for s in payload)
    amps = np.zeros((len(payload), width), dtype=np.float64)
    for i, s in enumerate(payload):
        a = s.get("amplitudes") or []
        amps[i, :len(a)] = a
    totals = amps.sum(axis=1)
    safe = np.where(totals > 0.0, totals, 1.0)
    norm = amps / safe[:, None]
    mask = _used_mask(width,
                      any(bool(s.get("first_word_invalid")) for s in payload))
    u = norm[:, mask] if mask.any() else norm
    return float(np.abs(np.diff(u, axis=0)).mean()), len(payload)


def signflip_p(diffs: np.ndarray) -> tuple[float, int, int]:
    diffs = np.asarray(diffs, dtype=np.float64)
    obs = float(diffs.mean())
    hits = 0
    for bits in range(1 << diffs.size):
        signs = np.array([1.0 if (bits >> i) & 1 else -1.0
                          for i in range(diffs.size)])
        if float((signs * diffs).mean()) >= obs - 1e-12:
            hits += 1
    return hits / (1 << diffs.size), hits, 1 << diffs.size


def paired_dz(diffs: np.ndarray, n_boot: int = N_BOOT,
              seed: int = SEED) -> tuple[float, tuple[float, float]]:
    diffs = np.asarray(diffs, dtype=np.float64)
    mean = float(diffs.mean())
    sd = float(diffs.std(ddof=1))
    if sd == 0.0:
        if mean > 0:
            return float("inf"), (float("inf"), float("inf"))
        if mean < 0:
            return float("-inf"), (float("-inf"), float("-inf"))
        return float("nan"), (float("nan"), float("nan"))
    dz = mean / sd
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        sample = diffs[rng.integers(0, diffs.size, diffs.size)]
        sd_b = float(sample.std(ddof=1))
        if sd_b > 0.0:
            out.append(float(sample.mean() / sd_b))
    if not out:
        return dz, (float("nan"), float("nan"))
    return dz, (float(np.percentile(out, 2.5)),
                float(np.percentile(out, 97.5)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--result", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    session = json.load(open(args.session, encoding="utf-8"))
    rows = []
    by_block: dict[int, dict[str, float]] = {}
    for t in session["trials"]:
        value, n = roughness(t.get("samples") or [])
        rows.append({"index": t.get("index"), "block": t.get("block"),
                     "label": t.get("label"), "roughness_used": value,
                     "payload_frames": n})
        by_block.setdefault(t["block"], {})[t["label"]] = value

    blocks = sorted(by_block)
    diffs = np.array([by_block[b]["hand"] - by_block[b]["stationary"]
                      for b in blocks], dtype=np.float64)
    p, hits, assignments = signflip_p(diffs)
    dz, ci = paired_dz(diffs)

    report = {
        "source": args.session,
        "method": ("independent literal implementation of roughness_used; "
                   "payload sig_len>=33; LLTF null mask; exact one-sided "
                   "sign-flip; seeded percentile bootstrap"),
        "n_trials": len(rows),
        "n_blocks": len(blocks),
        "rows": rows,
        "diffs": [float(x) for x in diffs],
        "p": p,
        "hits": hits,
        "assignments": assignments,
        "dz": dz,
        "ci95": [float(ci[0]), float(ci[1])],
        "mean_diff": float(diffs.mean()),
    }

    if args.result:
        frozen = json.load(open(args.result, encoding="utf-8"))
        primary = frozen.get("primary", {})
        report["comparison"] = {
            "frozen_p": primary.get("p"),
            "frozen_dz": primary.get("dz"),
            "frozen_ci95": primary.get("ci95"),
            "frozen_diffs": primary.get("diffs"),
            "p_match": primary.get("p") == p,
            "dz_delta": (None if primary.get("dz") is None
                         else float(primary["dz"]) - dz),
            "ci_delta": (None if not primary.get("ci95")
                         else [float(primary["ci95"][0]) - ci[0],
                               float(primary["ci95"][1]) - ci[1]]),
        }

    text = json.dumps(report, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
