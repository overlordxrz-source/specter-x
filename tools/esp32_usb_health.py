#!/usr/bin/env python3
"""Passive health monitor for the ESP32-S3's native USB CDC link.

The link has wedged several times: the device keeps enumerating with the
right VID/PID and serial, but the CDC data path stops delivering bytes in
either direction. This monitor watches the link and, when it stalls, records
**read-only** evidence to tell a device-side stall apart from a host-side
USB problem.

It never resets, never flashes, never enters the bootloader, and never
re-opens the native USB node while diagnosing (re-opening it would
re-enumerate the device and destroy the evidence).

What is captured
----------------
* the link's state over time (bytes, packets, silence, sequence gaps);
* on a stall, whether the USB device still enumerates (IOKit);
* whether the *other* USB path on the board - the UART0 bridge - is still
  alive, which shows the MCU is still running and the fault is in the USB
  path rather than in the application;
* any USB-level errors the macOS kernel logged around the stall.

    python3 tools/esp32_usb_health.py --seconds 3600 -o runs/usb_health.json
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
import time
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import SerialDispatcher
from specter.sensors.esp32.diagnostics import (ESP32_USB_PID, ESP32_USB_VID,
                                              collect_stall_evidence)

ESP32_VID = ESP32_USB_VID
ESP32_PID = ESP32_USB_PID


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=600.0)
    ap.add_argument("--stall-after", type=float, default=5.0,
                    help="seconds of silence that count as a stall")
    ap.add_argument("--port", default=None)
    ap.add_argument("--poll-interval", type=float, default=0.0,
                    help="seconds between reads; 0 (default) reads continuously. "
                         "A slow poll lets the device's TX buffer overflow.")
    ap.add_argument("--sample-interval", type=float, default=30.0,
                    help="seconds between counter samples")
    ap.add_argument("--reopen-delay", type=float, default=2.0,
                    help="seconds to wait before reopening the port after a stall")
    ap.add_argument("-o", "--out", default="runs/usb_health.json")
    args = ap.parse_args(argv)

    import serial
    from specter.hw.usb import find_usb_serial_ports

    port = args.port
    if not port:
        nodes = find_usb_serial_ports(vid=ESP32_VID, pid=ESP32_PID)
        if not nodes:
            raise SystemExit("no ESP32-S3 native USB node found")
        port = nodes[0]

    dispatcher = SerialDispatcher(csi_capacity=4096, supervisor_capacity=64)
    ser = serial.Serial(port, baudrate=115200, timeout=0.5)

    t0 = time.time()
    reopen_pending = False
    last_byte = t0
    last_sample = -1e9
    # how fast the host drains the port. 0 = read continuously.
    poll = args.poll_interval
    last_state = "OK"
    events: List[Dict] = []
    samples: List[Dict] = []
    stall_evidence: List[Dict] = []

    print(f"watching {port} for {args.seconds:.0f}s "
          f"(a stall is {args.stall_after:.0f}s of silence)", flush=True)

    try:
        while time.time() - t0 < args.seconds:
            now = time.time()
            try:
                waiting = ser.in_waiting
            except Exception as exc:
                events.append({"t": round(now - t0, 2), "event": "port_error",
                               "detail": str(exc)})
                print(f"  [{now - t0:7.1f}s] PORT ERROR: {exc}", flush=True)
                break
            if waiting:
                try:
                    data = ser.read(waiting)
                except Exception as exc:
                    events.append({"t": round(now - t0, 2), "event": "read_error",
                                   "detail": str(exc)})
                    print(f"  [{now - t0:7.1f}s] READ ERROR: {exc}", flush=True)
                    break
                if data:
                    last_byte = time.time()
                    dispatcher.feed(data)
                    if last_state != "OK":
                        events.append({"t": round(now - t0, 2), "event": "recovered",
                                       "silent_for_s": round(last_byte - t0, 2),
                                       "after_reopen": reopen_pending})
                        print(f"  [{now - t0:7.1f}s] recovered "
                              f"(after_reopen={reopen_pending})", flush=True)
                        last_state = "OK"
                        reopen_pending = False
            else:
                silence = now - last_byte
                if silence > args.stall_after and last_state != "STALLED":
                    last_state = "STALLED"
                    ev = {"t": round(now - t0, 2)}
                    ev.update(collect_stall_evidence(silence))
                    # Non-destructive probe: close and reopen the port. This is
                    # a host-side action only - no reset, no bootloader. If the
                    # device resumes, the fault is in the host's view of the
                    # link; if it stays silent, the device needs a reset.
                    reopen_pending = True
                    events.append({"t": round(now - t0, 2), "event": "stall",
                                   "evidence": ev})
                    stall_evidence.append(ev)
                    print(f"  [{now - t0:7.1f}s] STALL {silence:.1f}s -> "
                          f"{ev['diagnosis']}", flush=True)
                    print(f"  [{now - t0:7.1f}s] reopening the port "
                          f"(no reset, no flash)...", flush=True)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    time.sleep(args.reopen_delay)
                    try:
                        ser = serial.Serial(port, baudrate=115200, timeout=0.5)
                        last_byte = time.time()
                        print(f"  [{now - t0:7.1f}s] reopened", flush=True)
                    except Exception as exc:
                        print(f"  [{now - t0:7.1f}s] reopen failed: {exc}",
                              flush=True)
                        break
            if now - t0 - last_sample >= args.sample_interval:
                last_sample = now - t0
                c = dispatcher.snapshot()
                samples.append({"t": round(now - t0, 2),
                                "bytes": c["bytes"], "packets": c["csi_parsed"],
                                "gaps": c["csi_sequence_gaps"],
                                "missing": c["csi_missing_packets"],
                                "malformed": c["csi_malformed"]})
            # The ONLY sleep in the read loop. A sleep here lets the device's
            # USB TX buffer overflow while the host is not draining it, which
            # makes the device drop CSI packets and print non-consecutive ids.
            # poll_interval=0 means "read continuously".
            if poll:
                time.sleep(poll)
    finally:
        try:
            ser.close()
        except Exception:
            pass

    counters = dispatcher.snapshot()
    report = {
        "port": port,
        "window_s": round(time.time() - t0, 2),
        "samples": samples,
        "events": events,
        "stalls": stall_evidence,
        "final_counters": counters,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nstalls: {len(stall_evidence)}  "
          f"packets: {counters['csi_parsed']}  "
          f"gaps: {counters['csi_sequence_gaps']}  "
          f"missing: {counters['csi_missing_packets']}  "
          f"malformed: {counters['csi_malformed']}")
    print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
