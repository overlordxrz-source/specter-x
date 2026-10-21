#!/usr/bin/env python3
"""SPECTER-X DI-188 tool: probe, monitor, dashboard, record, calibrate, stability.

Examples
--------
    python3 tools/di188.py probe
    python3 tools/di188.py dashboard --rate 200
    python3 tools/di188.py monitor --rate 500 --duration 60
    python3 tools/di188.py record --rate 200 --out runs/di188.csv
    python3 tools/di188.py stability --minutes 30
    python3 tools/di188.py calibrate --channel 0

Nothing here flashes firmware or installs drivers. The instrument already runs
the DI-188 protocol firmware; we only speak its documented command set.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.di188 import (CalibrationSet, DI188Driver, DI188Error,
                                   ChannelSpec, Di188Dashboard, default_specs,
                                   run_stability_test, save_stability_report)

DEFAULT_CAL = os.path.join(REPO, "specter", "calibration", "di188.json")


def _channels(arg: str) -> List[int]:
    return [int(x) for x in arg.split(",") if x.strip() != ""]


def _build_specs(channels: List[int], connected: List[int], floating: List[int],
                 sources: List[str]) -> List[ChannelSpec]:
    specs = default_specs(max(channels) + 1 if channels else 4)
    by_index = {s.index: s for s in specs}
    for spec in specs:
        if spec.index in floating:
            spec.connected = False
        elif spec.index in connected:
            spec.connected = True
    for item in sources:
        if "=" not in item:
            continue
        idx_s, _, src = item.partition("=")
        try:
            idx = int(idx_s)
        except ValueError:
            continue
        if idx in by_index:
            by_index[idx].source = src
            if by_index[idx].connected is None:
                by_index[idx].connected = True
    return [by_index[i] for i in sorted(by_index) if i in channels] or specs


def _load_calibration(path: Optional[str], channels: List[int],
                       identity, device_cal) -> CalibrationSet:
    if path and os.path.exists(path):
        cal = CalibrationSet.load(path)
        print(f"calibration: loaded {path} ({cal.basis_label()})")
        return cal
    profile = device_cal.profile if device_cal is not None else "unknown"
    cal = CalibrationSet.nominal(profile, channels,
                                 device_serial=identity.serial_number,
                                 device_model=identity.model_name)
    print(f"calibration: none found -> nominal/UNCALIBRATED (profile={profile})")
    return cal


# --------------------------------------------------------------------- probe

def cmd_probe(args) -> int:
    with DI188Driver(args.port).open() as dev:
        ident = dev.read_identity()
        print("== identity ==")
        print(json.dumps(ident.as_dict(), indent=2))
        try:
            cal = dev.read_device_calibration()
        except DI188Error as exc:
            print(f"device calibration: unavailable ({exc})")
            return 0
        print("\n== instrument digital calibration (read from device flash) ==")
        print(json.dumps(cal.as_dict(), indent=2))
        print("\nprofile:", cal.profile,
              "| nominal full scale:", {"di188_pm10v": "+/-10 V",
                                        "xiao_0_3v3": "0-3.3 V"}.get(cal.profile, "unknown"))
        print("NOTE: 'last_cal_date' 6214F19E and key 0123456789ABCDEF are the")
        print("      open-source firmware defaults, i.e. this unit was NOT")
        print("      calibrated by DATAQ. Counts are device-calibrated only.")
    return 0


# ------------------------------------------------------------------- monitor

def cmd_monitor(args) -> int:
    channels = _channels(args.channels)
    with DI188Driver(args.port).open() as dev:
        ident = dev.read_identity()
        device_cal = dev.read_device_calibration()
        cal = _load_calibration(args.calibration, channels, ident, device_cal)
        specs = _build_specs(channels, _channels(args.connected),
                             _channels(args.floating), args.source or [])
        realised = dev.configure(channels, args.rate)
        print(f"{ident.model_name} on {ident.port} | rate {realised:g} Hz "
              f"| calibration {cal.basis_label()}")
        for spec in specs:
            print(f"  CH{spec.index + 1} ({spec.terminal}): {spec.state().value} "
                  f"{spec.source or ''}")
        if any(s.state().value != "CONNECTED" for s in specs):
            print("\n  !! Unconnected channels are reported as FLOATING/NOISE.")
            print("     Their numbers are ADC noise, not measurements.")

        from specter.sensors.di188 import ChannelMonitor
        monitor = ChannelMonitor(specs)
        dev.start()
        t0 = time.time()
        n = 0
        try:
            for sample in dev.stream():
                monitor.add(sample.values)
                n += 1
                if n % max(1, int(realised * args.interval)) == 0:
                    _print_stats(monitor, cal, realised, time.time() - t0)
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            dev.stop()
        print("\nfinal:")
        _print_stats(monitor, cal, realised, time.time() - t0)
    return 0


def _print_stats(monitor, cal, rate, elapsed) -> None:
    reports = monitor.report(cal)
    print(f"\n--- t={elapsed:7.1f}s  {rate:g} Hz ---")
    for r in reports:
        flag = "" if r.state.is_measurement else "  [FLOATING/NOISE]"
        v = "n/a" if r.volts_mean is None else f"{r.volts_mean:+.4f} V"
        print(f"  CH{r.index + 1} {r.label:>4} state={r.state.value:<10} "
              f"last={r.stats.last if r.stats.last is not None else 0:>8.1f} counts  "
              f"mean={r.stats.mean:>8.2f} std={r.stats.std:>7.2f} "
              f"pp={r.stats.peak_to_peak:>7.1f}  volts_mean={v}{flag}")


# ----------------------------------------------------------------- dashboard

def cmd_dashboard(args) -> int:
    channels = _channels(args.channels)
    with DI188Driver(args.port).open() as dev:
        ident = dev.read_identity()
        device_cal = dev.read_device_calibration()
        cal = _load_calibration(args.calibration, channels, ident, device_cal)
        specs = _build_specs(channels, _channels(args.connected),
                             _channels(args.floating), args.source or [])
        dash = Di188Dashboard(dev, specs, cal, channels, args.rate)
        dash.start()
        url = dash.serve(port=args.http_port, block=False)
        print(f"\n  DI-188 dashboard: {url}")
        print(f"  {ident.model_name} serial {ident.serial_number} on {ident.port}")
        print(f"  calibration basis: {cal.basis_label()}")
        print("  press Ctrl-C to stop\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nshutting down")
        finally:
            dash.shutdown()
            time.sleep(0.3)
    return 0


# -------------------------------------------------------------------- record

def cmd_record(args) -> int:
    from specter.sensors.di188 import CsvRecorder, build_provenance
    channels = _channels(args.channels)
    out = args.out or time.strftime("di188_%Y%m%d_%H%M%S.csv")
    with DI188Driver(args.port).open() as dev:
        ident = dev.read_identity()
        device_cal = dev.read_device_calibration()
        cal = _load_calibration(args.calibration, channels, ident, device_cal)
        specs = _build_specs(channels, _channels(args.connected),
                             _channels(args.floating), args.source or [])
        realised = dev.configure(channels, args.rate)
        reports = []
        from specter.sensors.di188 import ChannelMonitor
        reports = ChannelMonitor(specs).report(cal)
        provenance = build_provenance(ident, device_cal, cal, channels, realised, reports)
        rec = CsvRecorder(out, channels, provenance)
        print(f"recording -> {out}  ({realised:g} Hz, channels {channels})")
        dev.start()
        n = 0
        try:
            for sample in dev.stream():
                volts = [cal.to_volts(ch, v) for ch, v in zip(channels, sample.values)]
                rec.write(sample.t, sample.index, sample.values, volts)
                n += 1
                if n % 1000 == 0:
                    print(f"  {n} frames")
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            dev.stop()
            rec.close()
        print(f"wrote {rec.rows} rows to {out}")
    return 0


# ----------------------------------------------------------------- stability

def cmd_stability(args) -> int:
    channels = _channels(args.channels)
    out = args.out or time.strftime("di188_stability_%Y%m%d_%H%M%S.json")
    with DI188Driver(args.port).open() as dev:
        ident = dev.read_identity()
        print(f"stability test: {args.minutes} min @ {args.rate:g} Hz on {ident.port}")
        t0 = time.time()

        def progress(report, elapsed):
            print(f"  t={elapsed:7.1f}s frames={report.frames_received:<8} "
                  f"stalls={report.stall_events} malformed={report.malformed_lines}")

        report = run_stability_test(dev, channels, args.rate,
                                     duration_s=args.minutes * 60.0,
                                     progress=progress)
        print("\n" + report.summary())
        save_stability_report(report, out)
        print(f"\nreport -> {out}")
    return 0 if report.ok else 2


# ----------------------------------------------------------------- calibrate

def cmd_calibrate(args) -> int:
    """Interactive two-point calibration against a known reference.

    Requires a real reference source - see docs/di188-wiring.md. Nothing is
    written until the fit is saved.
    """
    channels = _channels(args.channels)
    with DI188Driver(args.port).open() as dev:
        ident = dev.read_identity()
        device_cal = dev.read_device_calibration()
        realised = dev.configure(channels, args.rate)
        print(f"calibration on {ident.model_name} ({realised:g} Hz)")
        print("Apply the reference voltage to the channel, then enter its value.")
        print("Use at least two levels with a wide span (e.g. 0.000 V and 1.500 V).")
        points: List[tuple] = []
        try:
            while True:
                raw = input("reference volts (blank to finish) > ").strip()
                if not raw:
                    break
                volts = float(raw)
                print("  capturing 200 frames...")
                dev.start()
                vals = []
                for sample in dev.stream():
                    vals.append(float(sample.values[args.channel]))
                    if len(vals) >= 200:
                        break
                dev.stop()
                mean = sum(vals) / len(vals)
                print(f"  mean counts = {mean:.2f}  at {volts:+.4f} V")
                points.append((mean, volts))
        except (KeyboardInterrupt, EOFError):
            print("\naborted")
            return 1
        if len(points) < 2:
            print("need at least two points - nothing written")
            return 1
        from specter.sensors.di188.calibration import fit_linear
        gain, offset, rms = fit_linear(points)
        print(f"\nfit: volts = {gain:.9g} * counts + {offset:.9g}   rms residual {rms*1000:.3f} mV")
        cal = CalibrationSet.nominal(device_cal.profile, channels,
                                     device_serial=ident.serial_number,
                                     device_model=ident.model_name)
        from specter.sensors.di188 import ChannelCalibration
        for ch in channels:
            cal.channels[ch] = ChannelCalibration(
                gain=gain, offset=offset, basis="measured",
                method=f"least-squares fit over {len(points)} reference points",
                reference=args.reference or "operator-supplied reference",
                uncertainty_v=rms, points=points)
        cal.notes = f"channels {channels} calibrated together against {args.reference or 'a reference'}"
        out = args.out or DEFAULT_CAL
        cal.save(out)
        print(f"saved -> {out}")
    return 0


# ------------------------------------------------------------------------ main

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="di188", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None, help="serial node (default: auto-detect)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--channels", default="0,1,2,3")
        p.add_argument("--rate", type=float, default=100.0)
        p.add_argument("--calibration", default=DEFAULT_CAL)
        p.add_argument("--connected", default="", help="channels with a source attached")
        p.add_argument("--floating", default="", help="channels declared floating")
        p.add_argument("--source", action="append", default=[],
                       help="CH=<what is plugged in>, e.g. --source 0=battery+")

    p = sub.add_parser("probe", help="device identity + instrument calibration")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("monitor", help="live statistics in the terminal")
    common(p)
    p.add_argument("--interval", type=float, default=2.0)
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("dashboard", help="real-time dashboard in a browser")
    common(p)
    p.add_argument("--http-port", type=int, default=8765)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("record", help="record to CSV")
    common(p)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("stability", help="long-run stability test")
    common(p)
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_stability)

    p = sub.add_parser("calibrate", help="interactive calibration vs a reference")
    common(p)
    p.add_argument("--channel", type=int, default=0)
    p.add_argument("--reference", default="", help="describe the reference source")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_calibrate)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except DI188Error as exc:
        print(f"DI-188 error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
