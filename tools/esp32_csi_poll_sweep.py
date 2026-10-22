#!/usr/bin/env python3
"""Measure the host's USB read cadence against the ESP32-S3's CSI loss.

The ESP32-S3 prints one CSI line per callback through the ROM's USB-serial
path. That path has a small TX FIFO. When the host does not drain the CDC
endpoint fast enough, the FIFO overflows: the device drops whole packets
(their sequence ids are skipped) and the lines that do arrive can be
truncated (they fail to parse). Sustained overflow eventually wedges the
device's USB TX path, and only a device reset recovers it.

This sweep runs the *same* read loop at a series of poll intervals and
reports, for each:

* packets received and the device's id span -> what fraction of the
  packets the device produced actually arrived;
* sequence gaps, missing packets and malformed lines -> the corruption
  that the overflow produces;
* bytes/s -> how much of the link the host is actually using.

    python3 tools/esp32_csi_poll_sweep.py --seconds 60 \
        --intervals 0,0.002,0.005,0.01,0.02,0.05 -o runs/soak/poll_sweep.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Dict, List

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import SerialDispatcher  # noqa: E402

RESET_PORT = "/dev/cu.usbmodem5B901602281"
RESET_BAUD = "115200"


def device_reset() -> bool:
    """Hard-reset the board over the UART bridge (never the native USB path)."""
    try:
        subprocess.run(
            ["esptool", "--port", RESET_PORT, "--baud", RESET_BAUD,
             "--after", "hard-reset", "chip-id"],
            capture_output=True, text=True, timeout=90, check=False)
    except Exception as exc:  # pragma: no cover - diagnostics only
        print(f"    reset failed: {exc}", flush=True)
        return False
    return True


def wait_for_stream(port: str, timeout: float = 25.0) -> bool:
    """Wait until the device is printing again."""
    import serial
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ser = serial.Serial(port, 115200, timeout=0.5)
        except Exception:
            time.sleep(0.5)
            continue
        try:
            t0 = time.time()
            buf = b""
            while time.time() - t0 < 4.0:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    if buf.count(b"CSI_DATA,") > 5:
                        return True
        except Exception:
            pass
        finally:
            ser.close()
        time.sleep(0.5)
    return False


def run_arm(port: str, seconds: float, interval: float) -> Dict:
    """Read for `seconds` at the given poll interval and score the result."""
    import serial
    dispatcher = SerialDispatcher(csi_capacity=4096, supervisor_capacity=64)
    ser = serial.Serial(port, 115200, timeout=0.5)
    t0 = time.time()
    last_byte = t0
    while time.time() - t0 < seconds:
        n = ser.in_waiting
        if n:
            data = ser.read(n)
            if data:
                last_byte = time.time()
                dispatcher.feed(data)
        elif interval:
            time.sleep(interval)
    window = time.time() - t0
    ser.close()
    c = dispatcher.snapshot()
    first = c.get("csi_first_seq") or 0
    last = c.get("csi_last_seq") or 0
    span = max(last - first + 1, 1)
    received = c.get("csi_parsed", 0)
    return {
        "poll_interval_s": interval,
        "window_s": round(window, 2),
        "packets_received": received,
        "device_id_span": span,
        "received_fraction": round(received / span, 4),
        "gaps": c.get("csi_sequence_gaps", 0),
        "missing": c.get("csi_missing_packets", 0),
        "malformed": c.get("csi_malformed", 0),
        "bytes": c.get("bytes", 0),
        "bytes_per_s": round(c.get("bytes", 0) / max(window, 1e-9), 1),
        "packets_per_s": round(received / max(window, 1e-9), 1),
        "stalled": (time.time() - last_byte) > 5.0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="seconds per arm")
    ap.add_argument("--intervals", default="0,0.002,0.005,0.01,0.02,0.05",
                    help="comma separated poll intervals in seconds; 0 = continuous")
    ap.add_argument("--port", default=None)
    ap.add_argument("--recover", action="store_true", default=True,
                    help="reset the board before each arm (default)")
    ap.add_argument("--no-recover", dest="recover", action="store_false")
    ap.add_argument("-o", "--out", default="runs/soak/poll_sweep.json")
    args = ap.parse_args(argv)

    import serial
    from specter.hw.usb import find_usb_serial_ports
    from specter.sensors.esp32.diagnostics import ESP32_USB_PID, ESP32_USB_VID

    port = args.port
    if not port:
        nodes = find_usb_serial_ports(vid=ESP32_USB_VID, pid=ESP32_USB_PID)
        if not nodes:
            raise SystemExit("no ESP32-S3 native USB node found")
        port = nodes[0]

    intervals = [float(x) for x in args.intervals.split(",") if x.strip()]
    arms: List[Dict] = []
    for interval in intervals:
        label = "continuous" if interval == 0 else f"{interval * 1000:.0f} ms"
        print(f"\n=== arm: poll {label}, {args.seconds:.0f}s ===", flush=True)
        if args.recover:
            print("  resetting the board...", flush=True)
            device_reset()
            if not wait_for_stream(port):
                print("  device did not come back", flush=True)
                arms.append({"poll_interval_s": interval, "error": "no stream"})
                continue
        try:
            arm = run_arm(port, args.seconds, interval)
        except Exception as exc:
            print(f"  arm failed: {exc}", flush=True)
            arms.append({"poll_interval_s": interval, "error": str(exc)})
            continue
        arms.append(arm)
        print(f"  received {arm['packets_received']} packets "
              f"({arm['packets_per_s']:.0f}/s, {arm['bytes_per_s']:.0f} B/s)", flush=True)
        print(f"  of the device's {arm['device_id_span']} ids -> "
              f"{arm['received_fraction'] * 100:.1f}% arrived", flush=True)
        print(f"  gaps {arm['gaps']}  missing {arm['missing']}  "
              f"malformed {arm['malformed']}", flush=True)

    report = {"port": port, "seconds_per_arm": args.seconds, "arms": arms}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print("\n--- summary ---")
    print(f"{'poll':>12s}{'pkt/s':>9s}{'B/s':>10s}{'arrived':>10s}"
          f"{'gaps':>8s}{'missing':>10s}{'malformed':>11s}")
    for a in arms:
        if "error" in a:
            print(f"{a['poll_interval_s']:>12}{a['error']:>28}")
            continue
        name = "continuous" if a["poll_interval_s"] == 0 else \
            f"{a['poll_interval_s'] * 1000:.0f} ms"
        print(f"{name:>12}{a['packets_per_s']:>9.0f}{a['bytes_per_s']:>10.0f}"
              f"{a['received_fraction'] * 100:>9.1f}%{a['gaps']:>8d}"
              f"{a['missing']:>10d}{a['malformed']:>11d}")
    print(f"\nreport -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
