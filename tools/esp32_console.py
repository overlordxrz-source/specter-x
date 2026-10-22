#!/usr/bin/env python3
"""Read the ESP32-S3's own console log.

The board has two USB paths. The native CDC carries the CSI stream; the
CH343 bridge carries the **ESP-IDF log** - at **921600 baud**, the rate in
the firmware's ``sdkconfig.defaults``. Reading it at 115200 produces
garbage, which is what made this channel look dead in checkpoint 007.

That log is the instrument for the lab work: it says when the board
associates, when it roams, and what it thinks is happening. During a
silence on the CSI channel, it is the only thing that can say why.

    python3 tools/esp32_console.py --seconds 30
    python3 tools/esp32_console.py --port /dev/cu.usbmodem5B901602281
"""
from __future__ import annotations

import argparse
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

DEFAULT_PORT = "/dev/cu.usbmodem5B901602281"
DEFAULT_BAUD = 921600


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD,
                    help="the console rate; 921600, NOT 115200")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after this many seconds (0 = until Ctrl-C)")
    ap.add_argument("--out", default=None, help="also write the log here")
    ap.add_argument("--quiet", action="store_true",
                    help="do not echo to the terminal")
    args = ap.parse_args(argv)

    import serial
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:
        print(f"could not open {args.port}: {exc}", file=sys.stderr)
        return 2

    sink = open(args.out, "w", encoding="utf-8") if args.out else None
    print(f"reading {args.port} at {args.baud} baud "
          f"({'Ctrl-C to stop' if not args.seconds else f'for {args.seconds:.0f}s'})",
          flush=True)
    t0 = time.time()
    buf = b""
    try:
        while True:
            n = ser.in_waiting
            if n:
                chunk = ser.read(n)
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        line, _, buf = buf.partition(b"\n")
                        text = line.decode("utf-8", "replace").rstrip("\r")
                        if text.strip():
                            if not args.quiet:
                                print(text, flush=True)
                            if sink:
                                sink.write(text + "\n")
            else:
                time.sleep(0.01)
            if args.seconds and (time.time() - t0) >= args.seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        if sink:
            sink.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
