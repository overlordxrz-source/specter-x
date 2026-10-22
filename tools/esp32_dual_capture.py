#!/usr/bin/env python3
"""Dual-channel capture: the USB CDC stream and the board's own console.

The ESP32-S3 has two USB paths to the same application:

* the **native USB CDC** port, which carries the CSI CSV stream;
* the **CH343 UART0 bridge**, which carries the ESP-IDF log *and* a second
  copy of the same CSV stream, at **921600 baud** (the console UART rate
  from the example's ``sdkconfig.defaults`` - reading it at 115200 produces
  garbage, which is what made it look like a dead channel).

Reading both at once is what separates the candidate causes of a silent
interval, because they leave different traces:

| what happened | USB CDC | UART0 console |
|---|---|---|
| the device stopped producing CSI | silent | **silent** |
| the USB output path stalled | silent | **still printing CSI** |
| the board lost its association | silent | ``wifi:state: ... -> disconnected`` |
| the board rebooted | silent | a fresh boot banner, and the ids restart at 0 |
| the board re-associates to another AP | resumes | ``wifi:connected with <other ssid>`` |

Nothing here resets, flashes or reconfigures anything. The tool only reads.

    python3 tools/esp32_dual_capture.py --seconds 2400 -o runs/soak/dual.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from typing import Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

USB_PORT = "/dev/cu.usbmodem1101"
UART_PORT = "/dev/cu.usbmodem5B901602281"
UART_BAUD = 921600

LOG_RE = re.compile(rb"^[IWED]\s*\(\d+\)")
CSI_RE = re.compile(rb"^CSI_DATA,")


class Channel:
    """One serial channel, read in its own thread."""

    def __init__(self, name: str, port: str, baud: int):
        self.name = name
        self.port = port
        self.baud = baud
        self.bytes = 0
        self.lines = 0
        self.csi_lines = 0
        self.log_lines = 0
        self.last_byte = time.time()
        self.last_csi = time.time()
        self.last_log = time.time()
        self.errors: List[str] = []
        # reentrant: _run() holds it while it calls _consume()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.recent_logs: List[Dict] = []
        self.recent_csi: List[Dict] = []
        #: every log line the device ever printed, with a timestamp
        self.all_logs: List[Dict] = []

    def start(self) -> bool:
        import serial
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
        except Exception as exc:
            self.errors.append(f"open: {exc}")
            return False
        self._thread = threading.Thread(target=self._run, name=self.name,
                                        daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                n = self._ser.in_waiting
            except Exception as exc:
                self.errors.append(f"in_waiting: {exc}")
                break
            if n:
                try:
                    data = self._ser.read(n)
                except Exception as exc:
                    self.errors.append(f"read: {exc}")
                    break
                if data:
                    with self._lock:
                        self.bytes += len(data)
                        self.last_byte = time.time()
                        buf += data
                        while b"\n" in buf:
                            line, _, buf = buf.partition(b"\n")
                            self._consume(line)
            else:
                time.sleep(0.002)

    def _consume(self, line: bytes) -> None:
        line = line.strip()
        if not line:
            return
        now = time.time()
        with self._lock:
            self.lines += 1
            if CSI_RE.match(line):
                self.csi_lines += 1
                self.last_csi = now
                if len(self.recent_csi) < 40:
                    self.recent_csi.append({"t": round(now, 3),
                                            "head": line[:90].decode(
                                                "utf-8", "replace")})
            elif LOG_RE.match(line):
                self.log_lines += 1
                self.last_log = now
                self.recent_logs.append({"t": round(now, 3),
                                         "text": line[:200].decode(
                                             "utf-8", "replace")})
                # The whole point of the console channel is the device's own
                # account of what it did during an outage, so every log line
                # is kept with its timestamp - not just the tail.
                self.all_logs.append({"t": round(now, 3),
                                       "text": line[:300].decode(
                                           "utf-8", "replace")})

    def stop(self) -> None:
        self._stop.set()
        try:
            self._ser.close()
        except Exception:
            pass

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "name": self.name, "port": self.port, "baud": self.baud,
                "bytes": self.bytes, "lines": self.lines,
                "csi_lines": self.csi_lines, "log_lines": self.log_lines,
                "last_byte": self.last_byte, "last_csi": self.last_csi,
                "last_log": self.last_log,
            }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=2400.0)
    ap.add_argument("--usb-port", default=USB_PORT)
    ap.add_argument("--uart-port", default=UART_PORT)
    ap.add_argument("--uart-baud", type=int, default=UART_BAUD)
    ap.add_argument("--silence-after", type=float, default=5.0)
    ap.add_argument("-o", "--out", default="runs/soak/dual_capture.json")
    args = ap.parse_args(argv)

    usb = Channel("usb_cdc", args.usb_port, 115200)
    uart = Channel("uart0_console", args.uart_port, args.uart_baud)
    if not usb.start():
        print("could not open the USB CDC port:", usb.errors)
        return 2
    if not uart.start():
        print("could not open the UART0 console:", uart.errors)
        usb.stop()
        return 2

    print(f"capturing {args.usb_port} and {args.uart_port}@{args.uart_baud} "
          f"for {args.seconds:.0f}s", flush=True)
    t0 = time.time()
    events: List[Dict] = []
    samples: List[Dict] = []
    last_sample = 0.0
    try:
        while time.time() - t0 < args.seconds:
            time.sleep(0.5)
            now = time.time()
            u = usb.snapshot()
            a = uart.snapshot()
            usb_silence = now - u["last_csi"]
            uart_silence = now - a["last_csi"]
            if now - last_sample >= 15.0:
                last_sample = now
                samples.append({
                    "t": round(now - t0, 1),
                    "usb_bytes": u["bytes"], "usb_csi": u["csi_lines"],
                    "uart_bytes": a["bytes"], "uart_csi": a["csi_lines"],
                    "uart_log": a["log_lines"],
                    "usb_csi_silence_s": round(usb_silence, 2),
                    "uart_csi_silence_s": round(uart_silence, 2),
                })
            if usb_silence > args.silence_after:
                ev = {
                    "t": round(now - t0, 1),
                    "event": "usb_silence",
                    "usb_silence_s": round(usb_silence, 1),
                    "uart_csi_silence_s": round(uart_silence, 1),
                    "uart_last_log_s_ago": round(now - a["last_log"], 1),
                    "uart_log_tail": [l["text"] for l in uart.recent_logs[-12:]],
                    "uart_csi_tail": [c["head"] for c in uart.recent_csi[-3:]],
                }
                events.append(ev)
                print(f"  [{now - t0:7.1f}s] USB SILENT {usb_silence:.0f}s | "
                      f"UART csi silent {uart_silence:.0f}s | "
                      f"last log {now - a['last_log']:.0f}s ago", flush=True)
                # do not re-report the same silence
                while events and events[-1]["event"] == "usb_silence" \
                        and now - events[-1]["t"] < 30:
                    events.pop()
                time.sleep(30)
    finally:
        usb.stop()
        uart.stop()

    report = {
        "window_s": round(time.time() - t0, 1),
        "usb": usb.snapshot(),
        "uart": uart.snapshot(),
        "samples": samples,
        "events": events,
        "device_log": uart.all_logs,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    u = usb.snapshot()
    a = uart.snapshot()
    print(f"\nUSB : {u['bytes']} bytes, {u['csi_lines']} CSI lines, "
          f"{u['log_lines']} log lines")
    print(f"UART: {a['bytes']} bytes, {a['csi_lines']} CSI lines, "
          f"{a['log_lines']} log lines")
    print(f"silences on the USB channel: {len(events)}")
    print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
