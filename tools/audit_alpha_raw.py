"""Independent offline raw-to-session check of Alpha 002-C v2, not a new trial.

Reads only supplied evidence. No Alpha parser/statistic implementation is imported.
Prints JSON; redirect to a private audit directory. Requires the frozen 10-pair design.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np


def check(raw_path, session_path):
    raw = Path(raw_path).read_bytes()
    session_bytes = Path(session_path).read_bytes()
    session = json.loads(session_bytes)
    packets = {}
    malformed, recovered_lines, duplicates = 0, 0, 0
    for line in raw.decode("utf-8", "replace").splitlines():
        starts = [i for i in range(len(line)) if line.startswith("CSI_DATA,", i)]
        if len(starts) > 1:
            recovered_lines += 1
        for i, start in enumerate(starts):
            text = line[start : starts[i + 1] if i + 1 < len(starts) else len(line)]
            try:
                f = next(csv.reader([text]))
                if len(f) != 25:
                    raise ValueError("wrong width")
                iq = json.loads(f[24])
                if len(iq) != 128 or int(f[22]) != 128:
                    raise ValueError("wrong layout")
                key = int(f[1]), int(f[18])
                if key in packets:
                    duplicates += 1
                packets[key] = dict(
                    amplitudes=[
                        round(math.hypot(iq[j], iq[j + 1]), 2) for j in range(0, 128, 2)
                    ],
                    rssi=int(f[3]),
                    rate=int(f[4]),
                    channel=int(f[16]),
                    sig_len=int(f[20]),
                    first_word_invalid=bool(int(f[23])),
                )
            except (ValueError, TypeError, IndexError, csv.Error):
                malformed += 1
    blocks, seen, matched, mismatches, spans = {}, set(), 0, [], []
    for trial in session["trials"]:
        samples = trial["samples"]
        for sample in samples:
            key = sample["id"], sample["local_timestamp"]
            if key in seen:
                raise ValueError("sample reused across trials")
            seen.add(key)
            actual = packets.get(key)
            if actual is None or any(sample[k] != actual[k] for k in actual):
                mismatches.append({"id": key[0], "timestamp": key[1]})
            else:
                matched += 1
        payload = [s for s in samples if s["sig_len"] >= 33]
        a = np.array([s["amplitudes"] for s in payload], dtype=float)
        if a.ndim != 2 or a.shape[1] != 64 or len(a) < 2 or not np.isfinite(a).all():
            raise ValueError("invalid primary input")
        normal = a / np.where(a.sum(axis=1) > 0, a.sum(axis=1), 1)[:, None]
        mask = np.ones(64, bool)
        mask[[0, *range(27, 38)]] = False
        if any(s["first_word_invalid"] for s in payload):
            mask[:2] = False
        roughness = float(np.abs(np.diff(normal[:, mask], axis=0)).mean())
        pair = blocks.setdefault(trial["block"], {})
        if trial["label"] in pair:
            raise ValueError("duplicate condition within block")
        pair[trial["label"]] = roughness
        spans.append(
            {
                "index": trial["index"],
                "active_s": trial["active_s"],
                "sensor_span_s": trial["sensor_span_s"],
                "sample_span_s": trial["sample_span_s"],
                "payload_frames": len(payload),
                "valid": trial["valid"],
            }
        )
    if len(blocks) != 10 or any(
        set(p) != {"hand", "stationary"} for p in blocks.values()
    ):
        raise ValueError("expected frozen 10-pair design")
    diffs = np.array([p["hand"] - p["stationary"] for _, p in sorted(blocks.items())])
    hits = sum(
        float((diffs * signs).mean()) >= float(diffs.mean()) - 1e-12
        for signs in itertools.product((-1, 1), repeat=10)
    )
    return dict(
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        session_sha256=hashlib.sha256(session_bytes).hexdigest(),
        parsed_raw_packets=len(packets),
        malformed_fragments=malformed,
        recovered_concatenated_lines=recovered_lines,
        duplicate_packet_keys=duplicates,
        selected_samples=len(seen),
        matched_samples=matched,
        mismatches=mismatches,
        unique_sample_assignment=True,
        trials=spans,
        primary_p=hits / 1024,
        primary_dz=(
            float(diffs.mean() / diffs.std(ddof=1)) if diffs.std(ddof=1) > 0 else None
        ),
        interpretation="Arithmetic/provenance cross-check only; one exploratory session, no independent replication or new authorization.",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raw")
    ap.add_argument("session")
    args = ap.parse_args()
    result = check(args.raw, args.session)
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(bool(result["mismatches"]))
