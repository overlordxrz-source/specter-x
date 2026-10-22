#!/usr/bin/env python3
"""Verify a bench capture against its own raw stream and the device counters.

This is the post-capture gate, not a summary printer. It answers, with
numbers:

* did every window contain roughly its requested active time in **sensor**
  time (no backlog);
* is the payload rate the offered 10/s, measured on the sensor clock;
* are the host's record counts corroborated by the device's own ``printed``
  and ``data`` counters;
* is the raw IQ stream present, complete and parseable;
* are the metadata (design, cues, per-frame PHY fields) present.

    python3 tools/bench_verify.py runs/.../bench.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _stat_int(line: str, key: str):
    m = re.search(rf"(?:^|,){re.escape(key)}=(-?\d+)", line)
    return int(m.group(1)) if m else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("--raw", default=None)
    args = ap.parse_args(argv)

    data = json.load(open(args.path, encoding="utf-8"))
    raw_path = args.raw or data.get("raw") or (args.path + ".raw")
    raw = open(raw_path, "rb").read() if os.path.exists(raw_path) else b""
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    csi = [l for l in lines if l.startswith("CSI_DATA,")]
    stat = [l for l in lines if l.startswith("SPECTER_STAT,")]
    bad = 0
    for l in csi:
        if not l.endswith('"') or ',"[' not in l:
            bad += 1

    trials = data.get("trials", [])
    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    # --- windows ---------------------------------------------------------
    spans = [(t.get("active_s", 0.0), t.get("sensor_span_s", 0.0))
             for t in trials]
    worst = max((abs(s - a) for a, s in spans), default=0.0)
    check("every trial valid", all(t.get("valid") for t in trials),
          f"{sum(1 for t in trials if t.get('valid'))}/{len(trials)}")
    check("sensor span matches active window", worst <= 0.5,
          f"worst |sensor-active| = {worst:.3f}s")
    gaps = [t.get("max_sensor_gap_s", 0.0) for t in trials]
    check("no sensor gap over 0.5s", (max(gaps) if gaps else 0.0) <= 0.5,
          f"max {max(gaps) if gaps else 0:.3f}s")

    # --- rates -----------------------------------------------------------
    rates = []
    for t in trials:
        span = t.get("sensor_span_s") or 0.0
        n = t.get("payload_frames", len(t.get("samples") or []))
        if span > 0:
            rates.append(n / span)
    rmin, rmax = (min(rates), max(rates)) if rates else (0.0, 0.0)
    check("payload rate near the offered 10/s",
          rates and 9.0 <= rmin and rmax <= 11.0,
          f"{rmin:.2f}..{rmax:.2f}/s over {len(rates)} trials")

    # --- host vs device counters ----------------------------------------
    host_payload = sum(t.get("payload_frames", 0) for t in trials)
    host_null = sum(t.get("null_frames", 0) for t in trials)
    host_total = host_payload + host_null
    dev = None
    if len(stat) >= 2:
        a, b = stat[0], stat[-1]
        d = {k: (_stat_int(b, k) - _stat_int(a, k))
             for k in ("csi_cb", "printed", "data", "null", "rej",
                       "drop_old", "drop_new")}
        dev = d
    if dev and dev["printed"]:
        drift = abs(host_total - dev["printed"]) / dev["printed"]
        check("host records match device printed", drift <= 0.02,
              f"host {host_total}, device {dev['printed']} "
              f"({drift * 100:.2f}% apart)")
        dp = dev.get("data") or 0
        if dp:
            drift_p = abs(host_payload - dp) / dp
            check("host payload matches device data", drift_p <= 0.02,
                  f"host {host_payload}, device {dp} "
                  f"({drift_p * 100:.2f}% apart)")
        check("no device queue drops", (dev.get("drop_old", 0) +
                                       dev.get("drop_new", 0)) == 0,
              f"drop_old {dev.get('drop_old')}, drop_new {dev.get('drop_new')}")
    else:
        check("device counters present", False,
              f"{len(stat)} SPECTER_STAT lines in the raw stream")

    # --- stream and metadata --------------------------------------------
    check("raw stream captured", len(raw) > 0, f"{len(raw)} bytes at {raw_path}")
    check("no malformed CSI line in the raw stream", bad == 0, f"{bad} malformed")
    check("raw CSI count matches the JSON",
          len(csi) >= host_total,
          f"raw {len(csi)} CSI lines, JSON {host_total} records")
    design = data.get("design") or {}
    check("design metadata present",
          all(k in design for k in ("seed", "trial_order", "blocks",
                                    "guard_s", "max_gap_s")),
          f"keys {sorted(design)}")
    cues = [c for t in trials for c in (t.get("cues") or [])]
    check("cue events recorded", bool(cues), f"{len(cues)} cue events")
    sample = next((t.get("samples") or [None])[0] for t in trials
                  if t.get("samples"))
    fields = set(sample or {})
    need = {"t_host", "t_sensor", "id", "rssi", "channel", "rate", "sig_len",
            "first_word_invalid", "amplitudes"}
    check("per-frame metadata present", need <= fields,
          f"missing {sorted(need - fields)}" if sample else "no samples")

    # --- report ----------------------------------------------------------
    print(f"{'check':44s} {'result':6s} detail")
    print("-" * 90)
    for name, ok, detail in checks:
        print(f"{name:44s} {'PASS' if ok else 'FAIL':6s} {detail}")
    failed = [c for c in checks if not c[1]]
    print()
    if failed:
        print(f"BENCH VERIFY: FAIL ({len(failed)} checks)")
        return 1
    print(f"BENCH VERIFY: PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
