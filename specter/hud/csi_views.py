"""The CSI mode of the HUD: a waterfall, a change trace, and honest counters.

Three panels, in the order an operator reads them:

1. **Subcarrier waterfall** - amplitude against carrier index, scrolling
   right to left in time. This is the primary picture, because the
   interesting behaviour of Wi-Fi CSI is *how the multipath profile moves*,
   and a static bar chart of one packet cannot show that.
2. **Signal change from baseline** - a rolling trace of how far the
   normalised multipath profile is from the recent past.
3. **Compact health** - the link, the sequence, the USB transport and the
   radio, as counters.

The raw spectrum is kept as a **secondary diagnostic** (press ``S``): it is
the right thing to look at when the waterfall looks wrong, and the wrong
thing to look at all the time.

Honesty
-------
The change trace says what it is: a change in the radio path. It does not
say a person was detected. Nothing in this module claims a human was
present; that claim requires a labelled trial, and it belongs to the
experiment, not to the live view.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from specter.hud import theme
from specter.hud.theme import (BG_DEEP, CRIMSON, FAULT, OK, PANEL, ROSE,
                               ROSE_DIM, ROSE_PALE, RULE, RULE_SOFT, TEXT,
                               TEXT_DIM, TEXT_FAINT, T_LABEL, T_MICRO, T_SMALL,
                               T_TITLE, WARN, card, label, rule, text, value,
                               well)

PAD = 16
HEADER_H = 46
WATERFALL_H = 300
TRACE_H = 176
METRICS_H = 174
GAP = 12

#: the colour of a carrier the radio is not populating
UNUSED = (30, 22, 30)
UNUSED_RULE = (62, 48, 60)


def _fmt_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for unit, div in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n:.0f} B"


def _fmt_duration(s) -> str:
    try:
        s = float(s)
    except (TypeError, ValueError):
        return "-"
    if s < 60:
        return f"{s:.1f}s"
    if s < 3600:
        return f"{int(s // 60)}m {int(s % 60):02d}s"
    return f"{int(s // 3600)}h {int((s % 3600) // 60):02d}m"


def _metric(canvas, x, y, w, name, val, color=TEXT, sub=None):
    """One label/value pair in the metrics grid."""
    label(canvas, name, (x, y), TEXT_FAINT, T_MICRO)
    value(canvas, val, (x, y + 19), color, T_LABEL)
    if sub:
        (tw, _), _ = cv2.getTextSize(str(val), theme.FONT, T_LABEL, 1)
        text(canvas, sub, (x + tw + 7, y + 18), T_MICRO, TEXT_FAINT, 1,
             shadow=False)


def _group(canvas, x, y, w, title, rows, title_color=ROSE_DIM):
    """A titled group of metrics inside the health card."""
    label(canvas, title, (x, y), title_color, T_MICRO)
    rule(canvas, x, y + 7, x + w - 14, y + 7, RULE_SOFT)
    col_w = (w - 24) // 2
    for i, (name, val, col, sub) in enumerate(rows):
        gx = x + (i % 2) * (col_w + 10)
        gy = y + 26 + (i // 2) * 52
        _metric(canvas, gx, gy, col_w, name, val, col, sub)


_WATERFALL_LUT = None


def _lut() -> np.ndarray:
    global _WATERFALL_LUT
    if _WATERFALL_LUT is None:
        _WATERFALL_LUT = theme.waterfall_lut()
    return _WATERFALL_LUT


def draw_waterfall(canvas, amp: np.ndarray, used: np.ndarray, peak: float,
                   nulls: Sequence[int], rect: Tuple[int, int, int, int],
                   history_s: float, packet_rate: float):
    """The scrolling subcarrier waterfall.

    Rows are subcarriers, columns are time (newest at the right). The
    carriers the radio is not populating are painted out and labelled, rather
    than being drawn as "no signal" - they carry no information and a reader
    must not mistake them for a deep fade.
    """
    x0, y0, x1, y1 = rect
    well(canvas, x0, y0, x1, y1, BG_DEEP, RULE_SOFT)
    if amp is None or amp.size == 0:
        text(canvas, "NO SUBCARRIER DATA", (x0 + 16, y0 + (y1 - y0) // 2),
             T_LABEL, TEXT_DIM)
        return
    carriers, columns = amp.shape
    bar_w = 10
    px1 = x1 - bar_w - 8
    ww, wh = px1 - x0, y1 - y0
    lut = _lut()
    # scale, then resize in ONE channel, then colour-map: resizing a
    # three-channel image is three times the work for the same picture.
    # The dynamic range inside a packet is narrow, so a scale from zero would
    # spend the whole ramp on the top of it. The scale is therefore taken
    # from the *used* carriers' own 2nd..98th percentile - the unused ones
    # are excluded or they would drag the floor to zero - and the picture is
    # stretched across exactly that range.
    vals = amp[used] if used is not None and used.any() else amp
    if vals.size:
        lo = float(np.percentile(vals, 2.0))
        hi = float(np.percentile(vals, 98.0))
    else:
        lo, hi = 0.0, 1.0
    if hi - lo < 1e-6:
        hi = max(lo + 1e-6, peak * 1e-3)
    norm = np.clip((amp - lo) / (hi - lo), 0.0, 1.0) ** 0.85
    colour = lut[(norm * 255.0).astype(np.uint8)]     # (carriers, columns, 3)
    img = cv2.resize(colour, (ww, wh), interpolation=cv2.INTER_LINEAR)

    # paint out the carriers the radio is not populating
    band_rows = []
    for c in nulls:
        r0 = int(c * wh / carriers)
        r1 = max(r0 + 1, int((c + 1) * wh / carriers))
        img[r0:r1, :] = UNUSED
        band_rows.append((r0, r1))
    canvas[y0:y1, x0:px1] = img

    # the boundary of the unused band, so it is unmistakable
    if nulls:
        c0, c1 = min(nulls), max(nulls)
        r0 = int(c0 * wh / carriers)
        r1 = int((c1 + 1) * wh / carriers)
        for r in (r0, r1):
            if 0 <= r < wh:
                rule(canvas, x0, y0 + r, x1 - 1, y0 + r, UNUSED_RULE)
        # label each contiguous run of unused carriers on its own
        runs = []
        start = prev = nulls[0]
        for c in nulls[1:]:
            if c != prev + 1:
                runs.append((start, prev))
                start = c
            prev = c
        runs.append((start, prev))
        for a, b in runs:
            ra = int(a * wh / carriers)
            rb = int((b + 1) * wh / carriers)
            if rb - ra < 12:
                continue
            name = "DC" if (a == 0 and b == 0) else "UNUSED"
            text(canvas, name, (x0 + 10, y0 + (ra + rb) // 2 + 4), T_MICRO,
                 (104, 92, 108), 1, shadow=False)
            if b > a:
                text(canvas, f"GUARD {b - a + 1}", (x0 + 10, y0 + (ra + rb) // 2 + 16),
                     T_MICRO, (104, 92, 108), 1, shadow=False)

    # carrier index axis
    for c in (0, carriers // 4, carriers // 2, (3 * carriers) // 4, carriers - 1):
        r = int(c * wh / carriers)
        text(canvas, str(c), (x0 - 22, y0 + min(r + 10, wh - 2)), T_MICRO,
             TEXT_FAINT, 1, shadow=False)

    # time axis
    span = max(history_s, 0.1)
    text(canvas, f"-{span:.0f}s", (x0 + 4, y1 + 14), T_MICRO, TEXT_FAINT, 1,
         shadow=False)
    text(canvas, "NOW", (x1 - 30, y1 + 14), T_MICRO, TEXT_DIM, 1, shadow=False)

    # the colour scale
    bx = px1 + 4
    rows = np.linspace(255, 0, max(y1 - y0, 1)).astype(np.uint8)
    bar = np.repeat(lut[rows][:, None, :], bar_w, axis=1)
    canvas[y0:y1, bx:bx + bar_w] = bar
    for txt, ty in ((f"{hi:.0f}", y0 + 9), (f"{lo:.0f}", y1 - 3)):
        (tw, _), _ = cv2.getTextSize(txt, theme.FONT, T_MICRO, 1)
        text(canvas, txt, (bx - 4 - tw, ty), T_MICRO, TEXT_DIM, 1, shadow=False)


def draw_spectrum(canvas, amps: Sequence[float], used: np.ndarray,
                  nulls: Sequence[int], rect: Tuple[int, int, int, int]):
    """The raw spectrum - the secondary diagnostic view."""
    x0, y0, x1, y1 = rect
    well(canvas, x0, y0, x1, y1, BG_DEEP, RULE_SOFT)
    if not amps:
        text(canvas, "NO SPECTRUM", (x0 + 16, y0 + (y1 - y0) // 2), T_LABEL,
             TEXT_DIM)
        return
    n = len(amps)
    peak = max(max(amps), 1e-6)
    ww, wh = x1 - x0, y1 - y0
    pts = []
    for i, a in enumerate(amps):
        px = x0 + int(i / max(n - 1, 1) * (ww - 2)) + 1
        py = y1 - 3 - int((a / peak) * (wh - 8))
        pts.append((px, py))
    pts_a = np.array(pts, np.int32)
    # a filled body under the curve
    poly = np.vstack([pts_a, np.array([[x1 - 2, y1 - 2], [x0 + 2, y1 - 2]],
                                       np.int32)])
    cv2.fillPoly(canvas, [poly], (44, 28, 52))
    cv2.polylines(canvas, [pts_a], False, ROSE, 1, cv2.LINE_AA)
    # mark the unused carriers
    for c in nulls:
        px = x0 + int(c / max(n - 1, 1) * (ww - 2)) + 1
        cv2.line(canvas, (px, y0 + 2), (px, y1 - 2), UNUSED_RULE, 1)
    text(canvas, "RAW SPECTRUM - DIAGNOSTIC", (x0 + 8, y0 + 16), T_MICRO,
         TEXT_DIM, 1, shadow=False)
    text(canvas, f"peak {peak:.0f}", (x1 - 62, y0 + 16), T_MICRO, TEXT_DIM, 1,
         shadow=False)


def draw_change_trace(canvas, trace: np.ndarray, rect: Tuple[int, int, int, int],
                      current: float, baseline_ready: bool):
    """The rolling baseline-relative signal-change trace."""
    x0, y0, x1, y1 = rect
    well(canvas, x0, y0, x1, y1, BG_DEEP, RULE_SOFT)
    if trace is None or trace.size == 0:
        text(canvas, "NO TRACE", (x0 + 16, y0 + (y1 - y0) // 2), T_LABEL,
             TEXT_DIM)
        return
    n = len(trace)
    vals = trace[:n]
    hi = float(np.percentile(vals, 99.5)) if vals.size else 1.0
    lo = 0.0
    hi = max(hi, 1e-6)
    med = float(np.median(vals)) if vals.size else 0.0
    ww, wh = x1 - x0, y1 - y0

    xs = x0 + (np.arange(n) / max(n - 1, 1) * (ww - 2) + 1).astype(np.int32)
    ys = (y1 - 3 - (np.clip(vals, lo, hi) - lo) / (hi - lo) * (wh - 8)).astype(np.int32)
    pts_a = np.stack([xs, ys], axis=1)
    poly = np.vstack([pts_a, np.array([[x1 - 2, y1 - 2], [x0 + 2, y1 - 2]],
                                       np.int32)])
    cv2.fillPoly(canvas, [poly], (38, 24, 46))
    cv2.polylines(canvas, [pts_a], False, ROSE_PALE, 2, cv2.LINE_AA)

    # the median, as the reference level
    my = y1 - 3 - int((min(med, hi) - lo) / (hi - lo) * (wh - 8))
    for x in range(x0 + 2, x1 - 2, 12):
        rule(canvas, x, my, x + 6, my, (78, 60, 84))
    text(canvas, f"median {med * 100:.2f}%", (x1 - 92, my - 5), T_MICRO,
         TEXT_FAINT, 1, shadow=False)

    # the current value
    if len(xs):
        cv2.circle(canvas, (int(xs[-1]), int(ys[-1])), 3, ROSE_PALE, -1,
                   cv2.LINE_AA)
    for txt, ty in (("0", y1 - 2), (f"{hi * 100:.2f}%", y0 + 10)):
        (tw, _), _ = cv2.getTextSize(txt, theme.FONT, T_MICRO, 1)
        text(canvas, txt, (x0 - 6 - tw, ty), T_MICRO, TEXT_DIM, 1, shadow=False)
    if not baseline_ready:
        text(canvas, "BASELINE LEARNING", (x1 - 130, y0 + 16), T_MICRO, WARN, 1,
             shadow=False)


def draw_csi_dashboard(canvas, view: Optional[Dict], x0: int, y0: int,
                       w: int, h: int, show_spectrum: bool = False):
    """The CSI mode. ``view`` carries the analysis state and the counters."""
    if view is None:
        text(canvas, "CSI NOT ENABLED", (x0 + 30, y0 + 60), T_TITLE, TEXT_DIM, 2)
        return

    # --- header: who is talking, and is the link healthy -------------------
    state = str(view.get("link_state") or "N/A")
    state_col = theme.health_color(state)
    card(canvas, x0, y0, x0 + w, y0 + HEADER_H, PANEL, RULE)
    theme.accent_bar(canvas, x0, y0, x0 + 3, y0 + HEADER_H, CRIMSON, 2)
    text(canvas, "CSI", (x0 + PAD, y0 + 30), T_TITLE, ROSE, 2)
    cv2.circle(canvas, (x0 + PAD + 78, y0 + 24), 5, state_col, -1, cv2.LINE_AA)
    text(canvas, state, (x0 + PAD + 92, y0 + 30), T_LABEL, state_col, 1)

    src = view.get("source_mac") or "-"
    ch = view.get("source_channel")
    text(canvas, f"SOURCE {src}   CH {ch if ch is not None else '-'}",
         (x0 + 240, y0 + 30), T_SMALL, TEXT, 1)
    if view.get("source_changes"):
        text(canvas, f"SOURCE CHANGED x{view['source_changes']}",
             (x0 + 240, y0 + 15), T_MICRO, WARN, 1, shadow=False)
    text(canvas, f"RSSI {view.get('rssi', '-')} dBm   NOISE {view.get('noise_floor', '-')} dBm",
         (x0 + 560, y0 + 30), T_SMALL, TEXT, 1)
    text(canvas, f"USED {view.get('used_carriers', 0)}/{view.get('total_carriers', 0)}",
         (x0 + 810, y0 + 30), T_SMALL, TEXT_DIM, 1)

    y = y0 + HEADER_H + GAP

    # --- the waterfall ------------------------------------------------------
    card(canvas, x0, y, x0 + w, y + WATERFALL_H, PANEL, RULE)
    label(canvas, "Subcarrier waterfall", (x0 + PAD, y + 22), ROSE_DIM, T_LABEL)
    text(canvas, f"{view.get('total_carriers', 0)} carriers -> time"
                 f"   {view.get('packets_per_s', 0):.0f} pkt/s"
                 f"   {view.get('history_s', 0):.0f}s of history",
         (x0 + PAD + 210, y + 22), T_MICRO, TEXT_FAINT, 1, shadow=False)
    text(canvas, "[S] SPECTRUM" if not show_spectrum else "[S] WATERFALL",
         (x0 + w - 118, y + 22), T_MICRO, ROSE_DIM, 1, shadow=False)
    rule(canvas, x0 + PAD, y + 30, x0 + w - PAD, y + 30, RULE_SOFT)

    wrect = (x0 + PAD + 26, y + 40, x0 + w - PAD - 22, y + WATERFALL_H - 26)
    used_mask = view.get("used_mask")
    used_mask = (np.asarray(used_mask, bool) if used_mask is not None
                 else np.ones(int(view.get("total_carriers") or 1), bool))
    if show_spectrum:
        draw_spectrum(canvas, view.get("amplitudes") or [],
                      used_mask, view.get("null_carriers") or [], wrect)
    else:
        draw_waterfall(canvas, view.get("waterfall"),
                       used_mask,
                       float(view.get("peak") or 1.0),
                       view.get("null_carriers") or [], wrect,
                       float(view.get("history_s") or 0.0),
                       float(view.get("packets_per_s") or 0.0))
    y += WATERFALL_H + GAP

    # --- the change trace ---------------------------------------------------
    card(canvas, x0, y, x0 + w, y + TRACE_H, PANEL, RULE)
    label(canvas, "Signal change from baseline", (x0 + PAD, y + 22), ROSE_DIM,
          T_LABEL)
    text(canvas, "mean |delta| of the normalised multipath profile"
                 "   -   RF PATH CHANGE, NOT A HUMAN DETECTION",
         (x0 + PAD + 250, y + 22), T_MICRO, WARN, 1, shadow=False)
    rule(canvas, x0 + PAD, y + 30, x0 + w - PAD, y + 30, RULE_SOFT)
    trect = (x0 + PAD + 40, y + 40, x0 + w - PAD - 22, y + TRACE_H - 26)
    draw_change_trace(canvas, view.get("trace"), trect,
                      float(view.get("change") or 0.0),
                      bool(view.get("baseline_ready")))
    y += TRACE_H + GAP

    # --- compact health -----------------------------------------------------
    card(canvas, x0, y, x0 + w, y + METRICS_H, PANEL, RULE)
    gw = (w - 2 * PAD) // 4
    gx = x0 + PAD
    state_col = theme.health_color(view.get("link_state"))

    _group(canvas, gx, y + 18, gw, "Link", [
        ("state", str(view.get("link_state") or "-"), state_col, None),
        ("packets/s", f"{view.get('packets_per_s', 0):.1f}", TEXT, None),
        ("packets", f"{view.get('packets', 0)}", TEXT, None),
        ("uptime", _fmt_duration(view.get("uptime_s", 0)), TEXT_DIM, None),
    ])
    _group(canvas, gx + gw, y + 18, gw, "Sequence", [
        ("id first", str(view.get("first_id", "-")), TEXT_DIM, None),
        ("id last", str(view.get("last_id", "-")), TEXT_DIM, None),
        ("gaps", str(view.get("gaps", 0)),
         FAULT if view.get("gaps") else TEXT, None),
        ("missing", str(view.get("missing_packets", 0)),
         FAULT if view.get("missing_packets") else TEXT, None),
    ])
    _group(canvas, gx + 2 * gw, y + 18, gw, "Transport", [
        ("malformed", str(view.get("malformed", 0)),
         FAULT if view.get("malformed") else TEXT, None),
        ("dropped", str(view.get("dropped", 0)),
         WARN if view.get("dropped") else TEXT, None),
        ("bytes", _fmt_bytes(view.get("bytes", 0)), TEXT, None),
        ("silence", f"{view.get('silence_s', 0):.2f}s",
         WARN if float(view.get("silence_s") or 0) > 2 else TEXT, None),
    ])
    _group(canvas, gx + 3 * gw, y + 18, gw, "Radio", [
        ("rssi", f"{view.get('rssi', '-')} dBm", TEXT, None),
        ("noise floor", f"{view.get('noise_floor', '-')} dBm", TEXT_DIM, None),
        ("carriers used", f"{view.get('used_carriers', 0)}",
         TEXT, f"of {view.get('total_carriers', 0)}"),
        ("baseline", "LOCKED" if view.get("baseline_ready") else "LEARNING",
         OK if view.get("baseline_ready") else WARN, None),
    ])

    # the source history: the CSI source is the transmitter of the frame the
    # board heard, and on a guest network that can change underfoot.
    hist = view.get("source_history") or []
    rule(canvas, x0 + PAD, y + METRICS_H - 34, x0 + w - PAD, y + METRICS_H - 34,
         RULE_SOFT)
    if hist:
        text(canvas, "CSI SOURCE HISTORY", (x0 + PAD, y + METRICS_H - 16),
             T_MICRO, TEXT_FAINT, 1, shadow=False)
        text(canvas, "  |  ".join(hist[-2:])[:110], (x0 + PAD + 130,
             y + METRICS_H - 16), T_MICRO, WARN, 1, shadow=False)
    else:
        text(canvas, "CSI SOURCE UNCHANGED SINCE THE LINK CAME UP",
             (x0 + PAD, y + METRICS_H - 16), T_MICRO, TEXT_FAINT, 1,
             shadow=False)
