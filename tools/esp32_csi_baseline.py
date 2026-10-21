#!/usr/bin/env python3
"""Reproducible CSI baseline for the ESP32-S3.

Measures, over a fixed window on the board's native USB CDC port:

* **throughput** - packets/s and bytes/s;
* **sequence gaps** - missing packets, using the upstream ``id`` counter;
* **timing** - inter-arrival interval distribution and the device's own
  ``local_timestamp`` spacing;
* **USB recovery** - whether the link stayed up, how long any outage was, and
  whether it came back on its own.

It reads only. It never resets, flashes or erases anything: a "recovery" here
means the link came back by itself, and the report records the outage so it
can be compared against a manual reset.

    python3 tools/esp32_csi_baseline.py --seconds 60 --out runs/csi_baseline.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import SerialDispatcher
from specter.hw.usb import find_usb_serial_ports

ESP32_USB_VID = 0x303A
ESP32_USB_PID = 0x1001


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(pct / 100.0 * len(ordered)))
    return ordered[idx]


def run(port: Optional[str], seconds: float, rate_hz: float) -> dict:
    import serial

    if not port:
        nodes = find_usb_serial_ports(vid=ESP32_USB_VID, pid=ESP32_USB_PID)
        if not nodes:
            raise SystemExit("no ESP32-S3 native USB node found")
        port = nodes[0]

    dispatcher = SerialDispatcher(csi_capacity=4096, supervisor_capacity=256)
    ser = serial.Serial(port, baudrate=115200, timeout=0.5)
    t_start = time.time()
    t_last_byte = t_start
    outages: List[dict] = []
    try:
        while time.time() - t_start < seconds:
            waiting = ser.in_waiting
            if waiting:
                data = ser.read(waiting)
                now = time.time()
                if now - t_last_byte > 1.0 and not outages:
                    pass
                t_last_byte = now
                dispatcher.feed(data)
            else:
                now = time.time()
                if now - t_last_byte > 1.0:
                    outages.append({"at_s": round(now - t_start, 3),
                                    "silent_for_s": round(now - t_last_byte, 3)})
                time.sleep(0.002)
    finally:
        try:
            ser.close()
        except Exception:
            pass

    elapsed = time.time() - t_start
    counters = dispatcher.snapshot()
    records = dispatcher.csi.drain()

    arrivals = [r.received_at for r in records]
    intervals = [arrivals[i] - arrivals[i - 1] for i in range(1, len(arrivals))]
    device_ts = [r.local_timestamp for r in records]
    device_intervals = [device_ts[i] - device_ts[i - 1] for i in range(1, len(device_ts))]

    bytes_total = counters.get("bytes", 0)
    # the bounded queue may have dropped records, so the authoritative count is
    # the parser's, not the queue depth
    parsed = counters.get("csi_parsed", 0)
    report = {
        "port": port,
        "window_s": round(elapsed, 3),
        "throughput": {
            "packets": parsed,
            "packets_per_s": round(parsed / elapsed, 2) if elapsed else 0.0,
            "bytes_per_s": round(bytes_total / elapsed, 1) if elapsed else 0.0,
            "csi_iq_values": sum(len(r.iq) for r in records),
            "queue_dropped": counters.get("csi_dropped", 0),
        },
        "sequence": {
            "first_id": counters.get("csi_first_seq"),
            "last_id": counters.get("csi_last_seq"),
            "gaps": counters.get("csi_sequence_gaps", 0),
            "missing_packets": counters.get("csi_missing_packets", 0),
        },
        "timing": {
            "arrival_median_ms": round(statistics.median(intervals) * 1e3, 3)
            if intervals else 0.0,
            "arrival_p95_ms": round(_percentile(intervals, 95) * 1e3, 3),
            "arrival_max_ms": round(max(intervals) * 1e3, 3) if intervals else 0.0,
            "device_interval_median_us": round(statistics.median(device_intervals), 1)
            if device_intervals else 0.0,
            "device_interval_p95_us": round(_percentile(device_intervals, 95), 1),
        },
        "link": {
            "outages": outages,
            "outage_count": len(outages),
            "recovered_by_itself": bool(records) and bool(outages),
        },
        "counters": counters,
        "ap": {
            "macs": sorted({r.mac for r in records}),
            "rssi_min": min((r.rssi for r in records), default=None),
            "rssi_max": max((r.rssi for r in records), default=None),
            "channels": sorted({r.channel for r in records}),
        },
    }
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--rate", type=float, default=0.0,
                    help="expected packet rate, for a pass/fail check (0 = no check)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    report = run(args.port, args.seconds, args.rate)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"\nreport -> {args.out}")

    ok = report["sequence"]["missing_packets"] == 0
    if args.rate:
        ok = ok and report["throughput"]["packets_per_s"] >= args.rate * 0.9
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
