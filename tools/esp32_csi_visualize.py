#!/usr/bin/env python3
"""Offline CSI visualisation from a recorded session.

Reads a SPECTER-X session log (JSONL) containing ``csi_summary``
measurements and renders two panels:

* **subcarrier amplitudes** over time - one line per carrier, from the
  amplitudes carried in each measurement;
* **packet statistics** over time - packets/s, sequence gaps, missing
  packets, malformed records and dropped queue entries.

It works on a recording, so a run can be reviewed long after the hardware is
disconnected.

    python3 tools/esp32_csi_visualize.py runs/session.jsonl -o runs/csi.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def load_summaries(path: str) -> List[Dict]:
    """Pull the csi_summary measurements out of a session log."""
    out: List[Dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = rec.get("measurement")
            if not m or m.get("kind") != "csi_summary":
                continue
            value = m.get("value") or {}
            out.append({
                "t": rec.get("t_host", 0.0),
                "t_sensor": m.get("t_sensor"),
                "id": value.get("id"),
                "first_id": value.get("first_id"),
                "last_id": value.get("last_id"),
                "packets": value.get("packets", 0),
                "packets_per_s": value.get("packets_per_s", 0.0),
                "gaps": value.get("gaps", 0),
                "missing": value.get("missing_packets", 0),
                "malformed": value.get("malformed", 0),
                "dropped": value.get("dropped", 0),
                "unknown": value.get("unknown_lines", 0),
                "link": value.get("link_state"),
                "rssi": value.get("rssi"),
                "channel": value.get("channel"),
                "ap": value.get("ap_mac"),
                "amplitudes": value.get("amplitudes") or [],
            })
    out.sort(key=lambda r: r["t"])
    return out


def _draw_stats_panel(canvas, rows, times, x0, y0, w, h):
    """Packet statistics as a small OpenCV line/bar plot."""
    import numpy as np
    cv2 = _cv2()
    cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (18, 18, 18), -1)
    cv2.putText(canvas, "packets/s", (x0 + 10, y0 + 18), _font(), 0.45, (150, 200, 255), 1)
    if len(times) < 2:
        return
    t0, t1 = times[0], times[-1]
    span = max(t1 - t0, 1e-6)
    vals = [r["packets_per_s"] for r in rows]
    vmax = max(vals) or 1.0

    def px(t):
        return int(x0 + 8 + (t - t0) / span * (w - 16))

    def py(v):
        return int(y0 + h - 24 - (v / vmax) * (h - 46))

    prev = None
    for t, v in zip(times, vals):
        p = (px(t), py(v))
        if prev:
            cv2.line(canvas, prev, p, (150, 200, 255), 1, cv2.LINE_AA)
        prev = p
    for key, label, colour in (("gaps", "gaps", (80, 80, 235)),
                               ("missing", "missing", (60, 165, 255)),
                               ("malformed", "malformed", (40, 200, 255)),
                               ("dropped", "dropped", (245, 113, 167))):
        tot = sum(r[key] for r in rows)
        if not tot:
            continue
        cv2.putText(canvas, f"{label} {tot}", (x0 + 10, y0 + h - 8 + 0),
                    _font(), 0.4, colour, 1)
    cv2.putText(canvas, f"{vmax:.0f}", (x0 + 4, y0 + 24), _font(), 0.4, (140, 140, 140), 1)


def plot(rows: List[Dict], out_path: str, title: str = "") -> str:
    """Render the two panels with OpenCV (no extra dependency)."""
    import numpy as np
    cv2 = _cv2()
    if not rows:
        raise SystemExit("no csi_summary measurements in that file")

    t0 = rows[0]["t"]
    times = [r["t"] - t0 for r in rows]
    width = max(len(r["amplitudes"]) for r in rows)

    W, H = 1400, 900
    canvas = np.full((H, W, 3), 12, np.uint8)

    # --- subcarrier amplitude heatmap --------------------------------------
    matrix = np.full((len(rows), width), np.nan)
    for i, r in enumerate(rows):
        amp = r["amplitudes"][:width]
        matrix[i, :len(amp)] = amp
    finite = matrix[np.isfinite(matrix)]
    peak = float(finite.max()) if finite.size else 1.0
    norm = np.nan_to_num(matrix / (peak or 1.0), nan=0.0)
    heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
    heat = cv2.resize(heat, (W - 40, 430), interpolation=cv2.INTER_NEAREST)
    canvas[70:70 + heat.shape[0], 20:20 + heat.shape[1]] = heat

    cv2.putText(canvas, f"CSI subcarrier amplitude over time  ({width} carriers, peak {peak:.0f})",
                (20, 50), _font(), 0.7, (235, 235, 235), 1)
    cv2.putText(canvas, f"ap {rows[-1].get('ap')}  ch {rows[-1].get('channel')}  "
                       f"rssi {rows[-1].get('rssi')} dBm  link {rows[-1].get('link')}  "
                       f"{len(rows)} samples  {times[-1]:.1f}s",
                (20, 68), _font(), 0.5, (140, 140, 140), 1)

    # --- packet statistics --------------------------------------------------
    cv2.putText(canvas, "packet statistics", (20, 512), _font(), 0.6, (90, 255, 120), 1)
    _draw_stats_panel(canvas, rows, times, 20, 522, W - 40, 250)
    cv2.putText(canvas, f"time {times[0]:.1f}s -> {times[-1]:.1f}s",
                (20, H - 16), _font(), 0.45, (140, 140, 140), 1)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cv2.imwrite(out_path, canvas)
    return out_path


def _cv2():
    import cv2
    return cv2


def _font():
    import cv2
    return cv2.FONT_HERSHEY_SIMPLEX


def summarise(rows: List[Dict]) -> str:
    if not rows:
        return "no measurements"
    last = rows[-1]
    lines = [
        f"samples            : {len(rows)}",
        f"wall time          : {rows[-1]['t'] - rows[0]['t']:.1f} s",
        f"packets (logged)   : {sum(r['packets'] for r in rows)}",
        f"id first..last     : {rows[0].get('first_id')}..{last.get('last_id')}",
        f"sequence gaps      : {sum(r['gaps'] for r in rows)}",
        f"missing packets    : {sum(r['missing'] for r in rows)}",
        f"malformed records  : {sum(r['malformed'] for r in rows)}",
        f"dropped queue      : {sum(r['dropped'] for r in rows)}",
        f"unknown lines      : {sum(r['unknown'] for r in rows)}",
        f"mean packets/s     : {sum(r['packets_per_s'] for r in rows) / len(rows):.2f}",
        f"link states        : {sorted({r['link'] for r in rows})}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="SPECTER-X session log (.jsonl)")
    ap.add_argument("-o", "--out", default=None, help="output PNG")
    ap.add_argument("--title", default="")
    args = ap.parse_args(argv)

    rows = load_summaries(args.session)
    print(summarise(rows))
    out = args.out or os.path.splitext(args.session)[0] + "_csi.png"
    plot(rows, out, args.title)
    print(f"\nfigure -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
