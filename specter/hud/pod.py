"""POD mode: a targeting-pod style thermal view (white-hot / black-hot).

Look: grayscale thermal with automatic contrast (AGC), digital zoom, temporal
noise reduction, a centre reticle, a tracking box that follows the hottest blob,
and telemetry around the edges.

Honesty rules (project core principle):
  * If no thermal sensor is attached, the image is a luminance stand-in from the
    optical camera and the HUD prints "SIM THERMAL" in amber. It never claims
    to be heat.
  * Heading, pitch, range and temperature are drawn only when a Measurement or
    sensor value exists. Otherwise the field shows dashes.
  * The tracker box is labelled with its source and a confidence score.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX
HUD_W, HUD_H = 1280, 800
WHITE = (240, 240, 240)
AMBER = (40, 200, 255)
ZOOMS = (1, 2, 4, 8)
POLARITIES = ("WHT", "BLK")


@dataclass
class PodTelemetry:
    """Optional sensor values. None means 'not measured' and is drawn as dashes."""
    heading_deg: Optional[float] = None     # IMU
    pitch_deg: Optional[float] = None       # IMU
    roll_deg: Optional[float] = None        # IMU
    range_m: Optional[float] = None         # radar, on the tracked target
    range_conf: Optional[float] = None
    target_temp_c: Optional[float] = None   # radiometric thermal only


@dataclass
class PodState:
    polarity: str = "WHT"
    zoom_idx: int = 0
    track_enabled: bool = True
    thermal_is_real: bool = False           # False -> luminance stand-in, labelled SIM
    sensor_label: str = "SIM THERMAL"
    nr_alpha: float = 0.35                  # temporal noise reduction (EMA weight of new frame)
    recording: bool = False
    _acc: Optional[np.ndarray] = field(default=None, repr=False)
    _track: Optional[Tuple[int, int, int, int]] = field(default=None, repr=False)
    _track_conf: float = 0.0

    @property
    def zoom(self) -> int:
        return ZOOMS[self.zoom_idx]

    def cycle_zoom(self) -> None:
        self.zoom_idx = (self.zoom_idx + 1) % len(ZOOMS)

    def toggle_polarity(self) -> None:
        self.polarity = "BLK" if self.polarity == "WHT" else "WHT"


# --------------------------------------------------------------------------- image chain
def to_intensity(frame: np.ndarray) -> np.ndarray:
    """BGR / gray / float temperature array -> float32 single channel."""
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return frame.astype(np.float32)


def denoise(st: PodState, img: np.ndarray) -> np.ndarray:
    """Temporal EMA, the cheap version of multi-frame stacking. Resets on size change."""
    if st._acc is None or st._acc.shape != img.shape:
        st._acc = img.copy()
    else:
        cv2.accumulateWeighted(img, st._acc, st.nr_alpha)
    return st._acc


def agc(img: np.ndarray, lo_pct: float = 1.0, hi_pct: float = 99.0) -> np.ndarray:
    """Percentile contrast stretch to uint8, then local CLAHE for that crisp pod look."""
    lo, hi = np.percentile(img, (lo_pct, hi_pct))
    out = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1)
    u8 = (out * 255).astype(np.uint8)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(u8)


def digital_zoom(img: np.ndarray, zoom: int) -> np.ndarray:
    if zoom <= 1:
        return img
    h, w = img.shape[:2]
    ch, cw = h // zoom, w // zoom
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return cv2.resize(img[y0:y0 + ch, x0:x0 + cw], (w, h), interpolation=cv2.INTER_CUBIC)


def hottest_blob(u8: np.ndarray, min_area_frac: float = 0.0015):
    """Bounding box (x, y, w, h) and score of the largest hot region, or (None, 0)."""
    blur = cv2.GaussianBlur(u8, (9, 9), 0)
    thr = max(int(np.percentile(blur, 97)), 1)
    _, mask = cv2.threshold(blur, thr - 1, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None, 0.0
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[i]
    if area < min_area_frac * u8.size:
        return None, 0.0
    inside = blur[y:y + h, x:x + w].mean()
    contrast = (inside - blur.mean()) / 255.0
    return (int(x), int(y), int(w), int(h)), float(np.clip(contrast * 2.5, 0, 1))


def update_track(st: PodState, u8: np.ndarray) -> None:
    box, score = hottest_blob(u8) if st.track_enabled else (None, 0.0)
    if box is None:
        st._track_conf *= 0.8              # coast, then drop
        if st._track_conf < 0.15:
            st._track = None
        return
    if st._track is not None:               # smooth so the box doesn't jitter
        box = tuple(int(0.6 * a + 0.4 * b) for a, b in zip(st._track, box))
    st._track, st._track_conf = box, 0.7 * st._track_conf + 0.3 * score if st._track else score


# --------------------------------------------------------------------------- drawing
def _t(img, s, org, scale=0.55, color=WHITE, thick=1):
    x, y = org
    cv2.putText(img, s, (x + 1, y + 1), FONT, scale, (0, 0, 0), thick + 1, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def _fmt(v, fmt, dash):
    return dash if v is None else format(v, fmt)


def _reticle(img, cx, cy, col):
    g, L = 18, 60
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(img, (cx + dx * g, cy + dy * g), (cx + dx * L, cy + dy * L), col, 2, cv2.LINE_AA)
    for sx in (-1, 1):                       # corner brackets
        for sy in (-1, 1):
            x, y = cx + sx * 110, cy + sy * 80
            cv2.line(img, (x, y), (x - sx * 22, y), col, 2)
            cv2.line(img, (x, y), (x, y - sy * 22), col, 2)
    cv2.circle(img, (cx, cy), 2, col, -1)


def _heading_tape(img, hdg, col):
    cx, y = HUD_W // 2, 40
    cv2.line(img, (cx - 260, y + 14), (cx + 260, y + 14), col, 1)
    cv2.drawMarker(img, (cx, y + 24), col, cv2.MARKER_TRIANGLE_UP, 12, 2)
    if hdg is None:
        _t(img, "HDG ---", (cx - 38, y + 6), 0.55, col)
        return
    for d in range(-30, 31, 5):
        deg = (hdg + d) % 360
        if deg % 5:
            continue
        x = int(cx + (round(hdg + d) - hdg) * 8.5)
        tall = deg % 10 == 0
        cv2.line(img, (x, y + 14), (x, y + (2 if tall else 8)), col, 1)
        if deg % 30 == 0:
            _t(img, f"{int(deg):03d}", (x - 15, y - 4), 0.45, col)
    _t(img, f"{int(hdg) % 360:03d}", (cx - 18, y + 44), 0.6, col, 2)


def _pitch_ladder(img, pitch, col):
    x = 70
    cv2.line(img, (x, 220), (x, 580), col, 1)
    if pitch is None:
        _t(img, "PIT --", (x - 50, 600), 0.45, col)
        return
    y = int(400 - np.clip(pitch, -45, 45) * 4)
    cv2.drawMarker(img, (x + 10, y), col, cv2.MARKER_TRIANGLE_DOWN, 14, 2)
    _t(img, f"{pitch:+.0f}", (x + 20, y + 5), 0.5, col)


def render_pod(frame: np.ndarray, st: PodState, tel: Optional[PodTelemetry] = None,
               fps: float = 0.0) -> np.ndarray:
    tel = tel or PodTelemetry()
    img = denoise(st, to_intensity(frame))
    u8 = digital_zoom(agc(img), st.zoom)
    if st.polarity == "BLK":
        u8 = 255 - u8
    update_track(st, u8 if st.polarity == "WHT" else 255 - u8)

    h, w = u8.shape
    s = min(HUD_W / w, HUD_H / h)
    nw, nh = int(w * s), int(h * s)
    ox, oy = (HUD_W - nw) // 2, (HUD_H - nh) // 2
    canvas = np.zeros((HUD_H, HUD_W, 3), np.uint8)
    canvas[oy:oy + nh, ox:ox + nw] = cv2.cvtColor(cv2.resize(u8, (nw, nh)), cv2.COLOR_GRAY2BGR)

    col = WHITE if st.polarity == "WHT" else (20, 20, 20)
    label_col = WHITE if st.thermal_is_real else AMBER

    _reticle(canvas, HUD_W // 2, HUD_H // 2, col)
    _heading_tape(canvas, tel.heading_deg, col)
    _pitch_ladder(canvas, tel.pitch_deg, col)

    if st._track is not None:
        x, y, bw, bh = st._track
        p0 = (int(ox + x * s), int(oy + y * s))
        p1 = (int(ox + (x + bw) * s), int(oy + (y + bh) * s))
        cv2.rectangle(canvas, p0, p1, col, 2)
        src = "THERMAL" if st.thermal_is_real else "SIM"
        _t(canvas, f"TRK {src} {st._track_conf:.2f}", (p0[0], max(p0[1] - 8, 90)), 0.5, col)

    # top-left: mode block
    _t(canvas, "SPECTER-X", (20, 34), 0.75, WHITE, 2)  # letterbox bars stay white text
    _t(canvas, f"{st.polarity}  {st.zoom}X  {'TRK' if st._track else 'SRCH'}", (20, 62), 0.6, col)
    _t(canvas, st.sensor_label, (20, 88), 0.55, label_col, 2 if not st.thermal_is_real else 1)
    # top-right
    _t(canvas, time.strftime("%H:%M:%SZ", time.gmtime()), (HUD_W - 150, 34), 0.6, WHITE)
    _t(canvas, f"{fps:4.1f} FPS", (HUD_W - 150, 62), 0.5, col)
    if st.recording:
        cv2.circle(canvas, (HUD_W - 158, 82), 6, (40, 40, 230), -1)
        _t(canvas, "REC", (HUD_W - 145, 88), 0.5, (40, 40, 230), 2)
    # bottom telemetry
    rng = _fmt(tel.range_m, ".1f", "----")
    rc = "" if tel.range_conf is None else f" ({tel.range_conf:.2f})"
    tmp = _fmt(tel.target_temp_c, ".1f", "--.-")
    _t(canvas, f"RNG {rng} M{rc}  [RADAR]", (20, HUD_H - 14), 0.55, WHITE)
    _t(canvas, f"TGT {tmp} C  [THERMAL]", (440, HUD_H - 14), 0.55, WHITE)
    _t(canvas, f"ROLL {_fmt(tel.roll_deg, '+.0f', '--')}  [IMU]", (HUD_W - 230, HUD_H - 14), 0.55, WHITE)
    return canvas
