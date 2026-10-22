#!/usr/bin/env python3
"""Offline, consent-based Wi-Fi CSI motion experiment.

The ESP32-S3 is already associated with an access point and streams the
access point's downlink CSI over USB. A person moving near that access point
perturbs the radio path, so the CSI changes. This tool records **labelled
trials** of that signal and writes the statistics out for offline analysis.

It does not scan, probe or identify any network or device other than the one
the ESP32 is already associated with, it adds no traffic to that network
beyond the association the ESP32 already has, and everything stays on the
local machine.

    # record: 30 s stationary, 30 s hand motion, 30 s walking
    python3 tools/esp32_csi_motion.py record \
        --trial stationary:30 --trial hand:30 --trial walking:30 \
        --consent "subject: <name>, informed: yes, date: 2026-10-21" \
        -o runs/motion_001.json

    # analyse a recording offline
    python3 tools/esp32_csi_motion.py analyse runs/motion_001.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import SerialDispatcher
from specter.sensors.esp32.csi import subcarrier_amplitudes
from specter.hw.usb import find_usb_serial_ports

ESP32_USB_VID = 0x303A
ESP32_USB_PID = 0x1001


def _now() -> float:
    return time.time()


def record_trials(trials_spec, port: str, prompt: bool = False) -> List[Dict]:
    """Record every trial inside **one** port session.

    Opening and closing the CDC port repeatedly is itself a trigger for the
    ESP32's USB stall (see docs/checkpoints/007), so the port is opened once
    and the trials are time slices inside that single session.
    """
    import serial
    ser = serial.Serial(port, baudrate=115200, timeout=0.5)
    dispatcher = SerialDispatcher(csi_capacity=2048, supervisor_capacity=16)
    out: List[Dict] = []
    try:
        for label, secs in trials_spec:
            print(f"\n>>> trial '{label}' for {secs:.0f}s - do what the label says")
            if prompt:
                input("    press Enter to start this trial... ")
            before = dispatcher.snapshot()
            samples: List[Dict] = []
            t0 = _now()
            end = t0 + secs
            while _now() < end:
                waiting = ser.in_waiting
                if waiting:
                    dispatcher.feed(ser.read(waiting))
                for rec in dispatcher.drain_csi():
                    amps = subcarrier_amplitudes(rec.iq)
                    samples.append({
                        "t": round(_now() - t0, 4),
                        "id": rec.seq,
                        "rssi": rec.rssi,
                        "channel": rec.channel,
                        "local_timestamp": rec.local_timestamp,
                        "amplitudes": [round(a, 2) for a in amps],
                    })
                time.sleep(0.005)
            after = dispatcher.snapshot()
            out.append({
                "label": label,
                "requested_s": secs,
                "actual_s": round(_now() - t0, 3),
                "packets": len(samples),
                "sequence_gaps": after["csi_sequence_gaps"] - before["csi_sequence_gaps"],
                "missing_packets": (after["csi_missing_packets"]
                                    - before["csi_missing_packets"]),
                "malformed": after["csi_malformed"] - before["csi_malformed"],
                "samples": samples,
            })
    finally:
        try:
            ser.close()
        except Exception:
            pass
    return out


def trial_stats(trial: Dict) -> Dict:
    """Basic per-trial statistics."""
    s = trial["samples"]
    if not s:
        return {
            "label": trial["label"], "packets": 0, "duration_s": trial.get("actual_s", 0.0),
            "sequence_gaps": trial.get("sequence_gaps", 0),
            "missing_packets": trial.get("missing_packets", 0),
            "malformed": trial.get("malformed", 0),
            "total_amplitude": {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "n": 0},
            "rssi": {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "n": 0},
            "per_carrier_mean": [], "per_carrier_std": [], "carriers": 0,
            "no_data": True,
        }
    n_carriers = max(len(x["amplitudes"]) for x in s)
    totals = []
    per_carrier_mean: List[List[float]] = [[] for _ in range(n_carriers)]
    rssis = []
    for x in s:
        a = x["amplitudes"]
        totals.append(sum(a) if a else 0.0)
        for i, v in enumerate(a):
            per_carrier_mean[i].append(v)
        if x["rssi"] is not None:
            rssis.append(x["rssi"])

    def _stats(vals):
        if not vals:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "n": 0}
        return {"mean": round(statistics.mean(vals), 3),
                "std": round(statistics.pstdev(vals), 3),
                "min": round(min(vals), 3), "max": round(max(vals), 3), "n": len(vals)}

    carrier_stats = [_stats(v) for v in per_carrier_mean]
    return {
        "label": trial["label"],
        "packets": trial["packets"],
        "duration_s": trial["actual_s"],
        "sequence_gaps": trial["sequence_gaps"],
        "missing_packets": trial["missing_packets"],
        "malformed": trial["malformed"],
        "total_amplitude": _stats(totals),
        "rssi": _stats(rssis),
        "per_carrier_mean": [round(c["mean"], 2) for c in carrier_stats],
        "per_carrier_std": [round(c["std"], 2) for c in carrier_stats],
        "carriers": n_carriers,
    }


def separability(stats: List[Dict]) -> Dict:
    """How distinguishable are the trials? A simple between/within variance ratio.

    For each carrier, the variance of the carrier's mean across trials versus
    the average within-trial variance gives a F-like ratio. A ratio well above
    1 means the condition changes the spectrum, not just the noise.
    """
    labels = [s["label"] for s in stats if s.get("packets")]
    usable = [s for s in stats if s.get("packets")]
    if len(usable) < 2:
        return {"verdict": "need at least two trials with data"}
    n_carriers = min(len(s["per_carrier_mean"]) for s in usable)
    ratios = []
    null_carriers = []
    for c in range(n_carriers):
        means = [s["per_carrier_mean"][c] for s in usable]
        stds = [s["per_carrier_std"][c] for s in usable]
        # the ESP32 leaves a guard band of subcarriers unpopulated (zero
        # amplitude in every trial). They carry no information and would drag
        # the ratio towards zero, so they are excluded and reported.
        if all(m == 0.0 for m in means):
            null_carriers.append(c)
            continue
        within = statistics.mean([x * x for x in stds]) or 1e-9
        between = statistics.pvariance(means) if len(means) > 1 else 0.0
        ratios.append(between / within)
    ratios_sorted = sorted(range(len(ratios)), key=lambda i: -ratios[i])
    return {
        "labels": labels,
        "carriers": n_carriers,
        "carriers_used": len(ratios),
        "null_carriers": null_carriers,
        "per_carrier_f": [round(r, 3) for r in ratios],
        "top_f_carriers": ratios_sorted[:8],
        "max_f": round(max(ratios), 3) if ratios else 0.0,
        "median_f": round(statistics.median(ratios), 3) if ratios else 0.0,
        "verdict": ("conditions are separable" if ratios and max(ratios) > 1.0
                    else "no clear separation yet - more trials or a stronger stimulus needed"),
    }


def cmd_record(args) -> int:
    port = args.port
    if not port:
        nodes = find_usb_serial_ports(vid=ESP32_USB_VID, pid=ESP32_USB_PID)
        if not nodes:
            raise SystemExit("no ESP32-S3 native USB node found")
        port = nodes[0]

    trials_spec = []
    for spec in args.trial:
        label, _, secs = spec.partition(":")
        trials_spec.append((label.strip(), float(secs or 30)))
    if not trials_spec:
        raise SystemExit("at least one --trial LABEL:SECONDS is required")

    if not args.consent:
        raise SystemExit(
            "this experiment records a person's movement - pass --consent with a\n"
            "note naming the subject and confirming they were informed and agreed")

    out = {
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "port": port,
        "consent": args.consent,
        "method": ("ESP32-S3 downlink CSI of the AP it is already associated with; "
                   "no scanning, no probing of other devices, all data local"),
        "trials": [],
    }

    for trial in record_trials(trials_spec, port, args.prompt):
        out["trials"].append(trial)
        st = trial_stats(trial)
        print(f"    {trial['packets']} packets, "
              f"total amplitude mean {st['total_amplitude']['mean']} "
              f"std {st['total_amplitude']['std']}, "
              f"rssi {st['rssi']['mean']} dBm +/- {st['rssi']['std']}")

    out["stats"] = [trial_stats(t) for t in out["trials"]]
    out["separability"] = separability(out["stats"])
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nrecording -> {args.out}")
    print(f"separability: {out['separability'].get('verdict')} "
          f"(max F {out['separability'].get('max_f')})")
    return 0


def _figure(stats: List[Dict], out_path: str, title: str = "") -> str:
    """Per-carrier reference profile: mean with a +/- std band, per trial.

    This is the reference a motion trial is compared against - the stationary
    condition's spectral shape, with its natural spread.
    """
    import numpy as np
    import cv2
    usable = [s for s in stats if s.get("carriers")]
    if not usable:
        raise SystemExit("no trial with per-carrier data")
    n_carriers = min(s["carriers"] for s in usable)
    W, H = 1400, 760
    canvas = np.full((H, W, 3), 12, np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    palette = [(150, 200, 255), (120, 255, 140), (80, 160, 255), (100, 255, 120)]

    # the spread of every trial, to scale the plot
    lo = min(min(s["per_carrier_mean"]) for s in usable)
    hi = max(max(s["per_carrier_mean"]) for s in usable)
    lo, hi = min(lo, 0.0), hi
    span = (hi - lo) or 1.0
    px0, py0, pw, ph = 90, 90, W - 140, H - 200

    for t_i, st in enumerate(usable):
        col = palette[t_i % len(palette)]
        means = st["per_carrier_mean"][:n_carriers]
        stds = st["per_carrier_std"][:n_carriers]
        pts = []
        for c in range(n_carriers):
            x = int(px0 + c / max(n_carriers - 1, 1) * pw)
            y = int(py0 + ph - (means[c] - lo) / span * ph)
            pts.append((x, y))
        # +/- std band as a vertical whisker per carrier
        for c in range(n_carriers):
            x = int(px0 + c / max(n_carriers - 1, 1) * pw)
            y_hi = int(py0 + ph - ((means[c] + stds[c]) - lo) / span * ph)
            y_lo = int(py0 + ph - (max(means[c] - stds[c], lo) - lo) / span * ph)
            cv2.line(canvas, (x, y_hi), (x, y_lo), col, 1, cv2.LINE_AA)
        cv2.polylines(canvas, [np.array(pts, np.int32)], False, col, 2, cv2.LINE_AA)
        cv2.putText(canvas, st["label"], (px0 + pw + 14, py0 + 20 + t_i * 24),
                    font, 0.55, col, 1)

    cv2.putText(canvas, "per-carrier mean amplitude (whisker = +/-1 std within the trial)",
                (px0, 40), font, 0.6, (235, 235, 235), 1)
    cv2.putText(canvas, f"carriers 0..{n_carriers - 1}   amplitude {lo:.0f}..{hi:.0f}",
                (px0, 64), font, 0.5, (140, 140, 140), 1)
    if title:
        cv2.putText(canvas, title[:90], (px0, H - 18), font, 0.45, (120, 120, 120), 1)
    for c in range(0, n_carriers, max(1, n_carriers // 12)):
        x = int(px0 + c / max(n_carriers - 1, 1) * pw)
        cv2.putText(canvas, str(c), (x - 8, py0 + ph + 22), font, 0.4, (140, 140, 140), 1)
    cv2.line(canvas, (px0, py0 + ph), (px0 + pw, py0 + ph), (70, 70, 70), 1)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cv2.imwrite(out_path, canvas)
    return out_path


def cmd_analyse(args) -> int:
    with open(args.path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    stats = data.get("stats") or [trial_stats(t) for t in data.get("trials", [])]
    for s in stats:
        print(f"\n--- {s['label']} ---")
        print(f"  packets {s['packets']}  gaps {s.get('sequence_gaps', 0)}  "
              f"missing {s.get('missing_packets', 0)}  malformed {s.get('malformed', 0)}")
        print(f"  total amplitude  mean {s['total_amplitude']['mean']}  "
              f"std {s['total_amplitude']['std']}  "
              f"min {s['total_amplitude']['min']}  max {s['total_amplitude']['max']}")
        print(f"  rssi             mean {s['rssi']['mean']}  std {s['rssi']['std']}  "
              f"min {s['rssi']['min']}  max {s['rssi']['max']}")
    sep = separability(stats)
    print("\n--- separability ---")
    print(f"  labels {sep.get('labels')}")
    print(f"  max F {sep.get('max_f')}  median F {sep.get('median_f')}")
    print(f"  verdict: {sep.get('verdict')}")
    if args.figure:
        path = _figure(stats, args.figure, data.get("consent", "")[:60])
        print(f"\nreference profile -> {path}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="record labelled trials")
    r.add_argument("--trial", action="append", default=[],
                   help="LABEL:SECONDS, repeatable, in order")
    r.add_argument("--consent", default="",
                   help="who the subject is and that they were informed and agreed")
    r.add_argument("--port", default=None)
    r.add_argument("--prompt", action="store_true",
                   help="wait for Enter before each trial")
    r.add_argument("-o", "--out", default="runs/motion.json")
    r.set_defaults(func=cmd_record)

    a = sub.add_parser("analyse", help="analyse a recording offline")
    a.add_argument("path")
    a.add_argument("--figure", default=None,
                   help="also write a per-carrier reference profile PNG")
    a.set_defaults(func=cmd_analyse)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
