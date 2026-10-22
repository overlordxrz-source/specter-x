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
import math
import os
import subprocess
import statistics
import sys
import time
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import SerialDispatcher
from specter.sensors.esp32.analysis import FEATURE_NAMES, analyse_blinded
from specter.sensors.esp32.experiment import (analyse_offline,
                                               per_carrier_screen,
                                               trials_from_json)
from specter.sensors.esp32.csi import subcarrier_amplitudes
from specter.hw.usb import find_usb_serial_ports

ESP32_USB_VID = 0x303A
ESP32_USB_PID = 0x1001


def _now() -> float:
    return time.time()


def _cue(text: str) -> None:
    """Speak a trial cue on the host's speaker.

    The operator is also the subject, so a terminal prompt is useless: they
    are standing at the marked spot, not at the keyboard. The cue is spoken
    from this machine, which is already in the room and already part of the
    rig. It is a convenience, not part of the measurement - no radio
    parameter depends on it.
    """
    try:
        subprocess.run(["say", text], check=False, timeout=20)
    except Exception:
        pass


# Spoken instructions for a human subject. The board hears the access point's
# downlink CSI, so the subject perturbs the radio path by moving near the
# board and the AP.
TRIAL_INSTRUCTIONS = {
    "stationary": "Stand still and do not move.",
    "still": "Stand at the marked spot, arms down, and do not move.",
    "hand": "Stay at the marked spot and move one hand across the path, "
            "about once a second. Feet and torso still.",
    "walking": "Walk a few steps back and forth, at normal speed.",
    "empty": "Leave the room and stay out until the trial ends.",
}

#: A frame with no payload is exactly 28 bytes (24-byte MAC header + 4-byte
#: FCS). Everything longer carried a payload. The receiver hears both on this
#: link, at different PHY rates, and checkpoint 011 established that the
#: amplitude scale follows the rate - so mixing them would put a
#: rate-dependent amplitude difference into the features. The motion
#: features are therefore computed on payload frames only, and the null
#: frames are kept and counted as a data-quality indicator.
PAYLOAD_MIN_SIG_LEN = 33


def payload_only(trials: List[Dict],
                 min_sig_len: int = PAYLOAD_MIN_SIG_LEN
                 ) -> Tuple[List[Dict], Dict]:
    """Return the trials restricted to frames that carried a payload.

    The null-data frames are **kept in the recording** and only filtered
    here, so the decision is auditable and reversible. A recording made
    before this change carries no ``sig_len``; it is passed through
    unchanged and reported as such rather than silently emptied.
    """
    out: List[Dict] = []
    kept = dropped = unknown_trials = 0
    for t in trials:
        samples = t.get("samples") or []
        if samples and not any("sig_len" in s for s in samples):
            unknown_trials += 1
            out.append(t)
            continue
        keep = [s for s in samples if int(s.get("sig_len", 0)) >= min_sig_len]
        kept += len(keep)
        dropped += len(samples) - len(keep)
        nt = dict(t)
        nt["samples"] = keep
        nt["frames_total"] = len(samples)
        nt["payload_frames"] = len(keep)
        nt["packets"] = len(keep)
        out.append(nt)
    return out, {"payload": kept, "null": dropped,
                 "trials_without_sig_len": unknown_trials}


def announce(label: str, index: int, total: int) -> None:
    """Say the phase out loud, so the subject does not have to watch a screen."""
    instr = TRIAL_INSTRUCTIONS.get(label, f"Trial {label}.")
    try:
        subprocess.run(["say", f"Trial {index} of {total}. {instr}"],
                       check=False, capture_output=True)
    except Exception:
        pass


def record_trials(trials_spec, port: str, prompt: bool = False,
                  announce_cues: bool = False,
                  lead_in: float = 0.0, cue: bool = False) -> List[Dict]:
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
        for index, (label, secs) in enumerate(trials_spec, start=1):
            print(f"\n>>> trial '{label}' for {secs:.0f}s - do what the label says",
                  flush=True)
            if announce_cues:
                announce(label, index, len(trials_spec))
                print(f"    {TRIAL_INSTRUCTIONS.get(label, '')}", flush=True)
            if cue:
                _cue(f"Trial {index} of {len(trials_spec)}. "
                     f"{TRIAL_INSTRUCTIONS.get(label, label)} "
                     f"Starting in {int(lead_in)} seconds.")
            if prompt:
                input("    press Enter to start this trial... ")
            if lead_in:
                time.sleep(lead_in)
            if cue:
                _cue("go")
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
                        #: the received frame's signal length. 28 B means the
                        #: frame carried no payload (association upkeep); a
                        #: payload frame is longer. Recorded for every frame so
                        #: the payload selection is auditable after the fact.
                        "sig_len": rec.sig_len,
                        "amplitudes": [round(a, 2) for a in amps],
                    })
                time.sleep(0.005)
            if cue:
                _cue("stop. relax.")
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


def condition_comparison(stats: List[Dict]) -> Dict:
    """Aggregate the trials by condition, so the three conditions can be
    compared directly rather than trial by trial."""
    by_label: Dict[str, List[Dict]] = {}
    for st in stats:
        by_label.setdefault(st["label"], []).append(st)
    out: Dict[str, Dict] = {}
    for label, group in by_label.items():
        amps = [g["total_amplitude"]["mean"] for g in group]
        rssis = [g["rssi"]["mean"] for g in group if g["rssi"]["mean"] is not None]
        out[label] = {
            "trials": len(group),
            "total_amplitude_mean": round(statistics.mean(amps), 2),
            "total_amplitude_spread": round(max(amps) - min(amps), 2),
            "rssi_mean": round(statistics.mean(rssis), 2) if rssis else None,
            "rssi_spread": round(max(rssis) - min(rssis), 2) if rssis else None,
            "per_trial_amplitude": [round(a, 2) for a in amps],
            "per_trial_rssi": [round(r, 2) for r in rssis],
        }
    return out


def cmd_record(args) -> int:
    """Record a session with continuous draining and sensor-time windows.

    The Alpha 002-C audit found the old recorder stopped reading during cues
    and lead-ins, so each trial absorbed a 43-55 s sensor backlog and was
    labelled with one condition. This path uses
    :class:`specter.sensors.esp32.acquisition.TrialRecorder`, which drains
    continuously and cuts trials by the device's own acquisition clock.
    """
    port = args.port
    if not port:
        nodes = find_usb_serial_ports(vid=ESP32_USB_VID, pid=ESP32_USB_PID)
        if not nodes:
            raise SystemExit("no ESP32-S3 native USB node found")
        port = nodes[0]

    base_spec = []
    for spec in args.trial:
        label, _, secs = spec.partition(":")
        base_spec.append((label.strip(), float(secs or 30)))
    if not base_spec:
        raise SystemExit("at least one --trial LABEL:SECONDS is required")
    if not args.consent:
        raise SystemExit(
            "this experiment records a person's movement - pass --consent with a\n"
            "note naming the subject and confirming they were informed and agreed")

    import random
    rng = random.Random(args.seed)
    plan = []
    for rep in range(max(1, args.repeats)):
        order = list(base_spec)
        if args.shuffle:
            rng.shuffle(order)
        for label, secs in order:
            plan.append({"label": label, "seconds": secs, "block": rep})
    print(f"trial order: {[p['label'] for p in plan]}")

    import serial
    from specter.sensors.esp32.acquisition import TrialRecorder, trial_to_json

    ser = serial.Serial(port, baudrate=115200, timeout=0.05)
    raw_path = args.raw_out or (args.out + ".raw")
    rec = TrialRecorder(ser, raw_out=raw_path, guard_s=args.guard,
                        max_gap_s=args.max_gap)
    rec.start_background()
    trials = []

    def cue(ev: str) -> None:
        if not args.cue:
            return
        if ev == "go":
            subprocess.Popen(["say", "go"])
        elif ev == "stop":
            subprocess.Popen(["say", "stop. relax."])

    try:
        for i, p in enumerate(plan, start=1):
            if args.cue:
                text = (f"Trial {i} of {len(plan)}. "
                        f"{TRIAL_INSTRUCTIONS.get(p['label'], p['label'])} "
                        f"Starting in {int(args.lead_in)} seconds.")
                subprocess.Popen(["say", text])
            else:
                print(f"\n>>> trial {i}/{len(plan)} '{p['label']}' "
                      f"for {p['seconds']:.0f}s", flush=True)
            t = rec.run_trial(p["label"], p["seconds"], p["block"], i,
                              lead_in_s=args.lead_in, on_cue=cue)
            trials.append(trial_to_json(t, requested_s=p["seconds"]))
            print(f"    {t.payload_frames} payload, {t.null_frames} null, "
                  f"active {t.active_s:.2f}s, sensor span "
                  f"{t.sensor_span_s:.2f}s, pre {t.excluded_pre} "
                  f"post {t.excluded_post} guard {t.excluded_guard}, "
                  f"max gap {t.max_sensor_gap_s:.3f}s, "
                  f"valid {t.valid}"
                  + (f" ({t.invalid_reason})" if not t.valid else ""),
                  flush=True)
    finally:
        rec.stop_background()
        try:
            ser.close()
        except Exception:
            pass

    out = {
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "port": port,
        "consent": args.consent,
        "method": ("ESP32-S3 SoftAP uplink CSI; one continuously drained "
                   "stream; trials cut by the device acquisition clock"),
        "design": {
            "seed": args.seed, "repeats": args.repeats,
            "shuffle": bool(args.shuffle), "lead_in_s": args.lead_in,
            "guard_s": args.guard, "max_gap_s": args.max_gap,
            "payload_min_sig_len": rec.payload_min_sig_len,
            "trial_order": [p["label"] for p in plan],
            "blocks": [p["block"] for p in plan],
        },
        "raw": raw_path,
        "malformed": rec.malformed,
        "trials": trials,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    valid = sum(1 for t in trials if t["valid"])
    print(f"\nrecording -> {args.out}   raw -> {raw_path}")
    print(f"trials {len(trials)}, valid {valid}, malformed {rec.malformed}")
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
    # Recomputed from the trials, so the features are always the current
    # ones rather than whatever was stored when the recording was made.
    trials = data.get("trials", [])
    if getattr(args, "all_frames", False):
        split = {"payload": sum(len(t.get("samples") or []) for t in trials),
                 "null": 0, "trials_without_sig_len": 0}
        print("\n--- frame selection ---")
        print("  --all-frames: payload and null-data frames are NOT separated")
    else:
        trials, split = payload_only(trials)
        data["trials"] = trials
        print("\n--- frame selection (payload frames only) ---")
        print(f"  payload frames kept {split['payload']}   "
              f"null-data frames dropped {split['null']}   "
              f"trials without sig_len {split['trials_without_sig_len']}")
        if split["trials_without_sig_len"]:
            print("  WARNING: a trial without sig_len was kept unchanged; "
                  "it mixes frame populations and is not comparable")
    stats = [trial_stats(t) for t in trials] if trials else (data.get("stats") or [])
    for s in stats:
        print(f"\n--- {s['label']} ---")
        print(f"  packets {s['packets']}  gaps {s.get('sequence_gaps', 0)}  "
              f"missing {s.get('missing_packets', 0)}  malformed {s.get('malformed', 0)}")
        print(f"  total amplitude  mean {s['total_amplitude']['mean']}  "
              f"std {s['total_amplitude']['std']}  "
              f"min {s['total_amplitude']['min']}  max {s['total_amplitude']['max']}")
        print(f"  rssi             mean {s['rssi']['mean']}  std {s['rssi']['std']}  "
              f"min {s['rssi']['min']}  max {s['rssi']['max']}")
    print("\n--- by condition ---")
    comp = condition_comparison(stats)
    print(f"  {'condition':>12s}{'trials':>8s}{'amp mean':>11s}{'amp spread':>12s}"
          f"{'rssi mean':>11s}{'rssi spread':>12s}")
    for label, c in comp.items():
        print(f"  {label:>12s}{c['trials']:>8d}{c['total_amplitude_mean']:>11.1f}"
              f"{c['total_amplitude_spread']:>12.1f}"
              f"{c['rssi_mean'] if c['rssi_mean'] is not None else 0:>11.1f}"
              f"{c['rssi_spread'] if c['rssi_spread'] is not None else 0:>12.1f}")
        print(f"               per-trial amplitude {c['per_trial_amplitude']}")
        print(f"               per-trial rssi       {c['per_trial_rssi']}")

    # The statistics live in specter.sensors.esp32.experiment, so the tool
    # and the HUD judge a recording with exactly the same code.
    offline = analyse_offline(data)
    feats = offline["features"]
    print("\n--- normalised (gain-free) motion features ---")
    print(f"  {'trial':>28s}{'roughness':>12s}{'rough used':>12s}"
          f"{'amp vol':>10s}{'amp~rssi':>10s}")
    for i, f in enumerate(feats, start=1):
        if not f.get("n"):
            continue
        print(f"  {i:>2d} {f['label']:>25s}{f['roughness']:>12.5f}"
              f"{f['roughness_used']:>12.5f}{f['amp_volatility']:>10.4f}"
              f"{f['amp_rssi_corr']:>10.3f}")

    print("\n--- condition test (one-way ANOVA across the conditions) ---")
    for name, r in offline["test"].items():
        p = r["p"]
        ps = f"{p:.4f}" if p == p else "n/a"
        sig = "  <-- significant at 0.05" if r.get("significant") else ""
        print(f"  {name:>28s}  F = {r['f']:>7.3f}  p = {ps:>7s} "
              f"(F {r['df1']},{r['df2']}){sig}")

    sep = offline["screen"]
    print("\n--- separability (per-carrier screen) ---")
    print(f"  labels {sep.get('labels')}")
    print(f"  max F {sep.get('max_f')}  median F {sep.get('median_f')}")
    print(f"  verdict: {sep.get('verdict')}")

    v = offline["verdict"]
    print("\n--- verdict ---")
    print(f"  {v['claim']}")
    print(f"  {v['detail']}")

    # the blinded analysis: frozen features, permutation test, effect sizes,
    # held-out score and the procedure's own measured false-positive rate.
    trials = trials_from_json(data)
    blinded = analyse_blinded(trials, seed=7, n_perm=500)
    print("\n--- blinded analysis (frozen features) ---")
    print(f"  {'feature':>18s}{'F':>10s}{'p':>10s}{'perm p':>10s}"
          f"{'FPR':>8s}{'held-out':>11s}")
    for name in FEATURE_NAMES:
        om = blinded["omnibus"][name]
        pe = blinded["permutation"][name]
        ho = blinded["held_out"][name]
        pp = f"{pe['empirical_p']:.4f}" if pe["empirical_p"] == pe["empirical_p"] else "n/a"
        fp = f"{pe['false_positive_rate']:.3f}" if pe["false_positive_rate"] is not None else "n/a"
        print(f"  {name:>18s}{om['f']:>10.3f}{om['p']:>10.4f}{pp:>10s}"
              f"{fp:>8s}{ho['held_out_accuracy']:>11.3f}")
    print("\n--- effect sizes (Cohen's d, bootstrap 95% CI) ---")
    for name in FEATURE_NAMES:
        eff = blinded["effects"][name]
        for pair, d in eff["pairs"].items():
            ci = f"CI {d['ci95']}" if d.get("ci95") else \
                f"CI not estimable (n = {d.get('n_per_group')} per group)"
            print(f"  {name:>18s}  {pair:<28s} d = {d['cohens_d']:>7}  {ci}")
    print("\n--- how many trials would have been needed? ---")
    from specter.sensors.esp32.analysis import required_n
    for name in ("roughness_used",):
        eff = blinded["effects"][name]
        best = max((abs(v["cohens_d"]) for v in eff["pairs"].values()
                    if v["cohens_d"] is not None), default=0.0)
        r = required_n(best, k=len(set(blinded["labels_in_analysis_order"])),
                        target_power=0.8)
        print(f"  the largest measured d is {best:.2f}; at that effect size, "
              f"{r['n_per_group_needed']} trials per condition "
              f"({r['total_trials_needed']} in total) reach 80% power")
        perms = blinded["permutation"][name]
        print(f"  the permutation test's smallest attainable p with "
              f"{len(blinded['labels_in_analysis_order'])} trials is "
              f"{perms['min_attainable_p']} - a p at that floor means 'as "
              f"extreme as this design can produce', not 'not significant'")
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
    r.add_argument("--cue", action="store_true",
                   help="speak each trial cue on the host speaker, for an "
                        "operator who is also the subject")
    r.add_argument("--announce", action="store_true",
                   help="say each phase out loud (macOS) so the subject can "
                        "follow the run without watching a screen")
    r.add_argument("--lead-in", type=float, default=0.0,
                   help="seconds to wait after the cue before the trial starts")
    r.add_argument("--repeats", type=int, default=1,
                   help="repeat the whole trial set N times")
    r.add_argument("--shuffle", action="store_true",
                   help="randomise the order of the trials within each "
                        "repetition, so a condition is not correlated with "
                        "the drift of the session")
    r.add_argument("--seed", type=int, default=1,
                   help="seed for --shuffle")
    r.add_argument("--raw-out", default=None,
                   help="write every raw serial line here (default: OUT.raw); "
                        "IQ, PHY metadata and validity flags are preserved")
    r.add_argument("--guard", type=float, default=0.10,
                   help="seconds excluded at each window boundary, because the "
                        "sensor marker at a cue is up to one frame old")
    r.add_argument("--max-gap", type=float, default=1.0,
                   help="a trial whose largest sensor gap exceeds this is "
                        "marked invalid rather than silently analysed")
    r.add_argument("-o", "--out", default="runs/motion.json")
    r.set_defaults(func=cmd_record)

    a = sub.add_parser("analyse", help="analyse a recording offline")
    a.add_argument("path")
    a.add_argument("--figure", default=None,
                   help="also write a per-carrier reference profile PNG")
    a.add_argument("--all-frames", action="store_true",
                   help="do not separate payload from null-data frames "
                        "(diagnostic only; the two populations have different "
                        "PHY rates and their amplitudes are not comparable)")
    a.set_defaults(func=cmd_analyse)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
