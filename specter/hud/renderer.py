"""OpenCV HUD for the 7" 1280x800 touchscreen.

The HUD only draws things that arrive as Measurements (with provenance) or
SensorStatus records. Every overlay is tagged with its source.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Sequence

import cv2
import numpy as np

from specter.fusion.measurement import Measurement
from specter.sensors.base import SensorStatus
from specter.sensors.nightvision.camera import COCO_SKELETON

HUD_W, HUD_H = 1280, 800
PANEL_W = 270
TOP_H = 44
FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN = (90, 255, 120)
AMBER = (40, 200, 255)
WHITE = (235, 235, 235)
DIM = (140, 140, 140)

MODES = ["OPTICAL", "NIGHT-GREEN", "POD"]


@dataclass
class HudState:
    mode: str = "OPTICAL"
    fps: float = 0.0
    infer_ms: float = 0.0
    sensors: List[SensorStatus] = field(default_factory=list)
    poses: List[Measurement] = field(default_factory=list)
    pose_active: bool = False
    ticker: Sequence[str] = ()
    source_name: str = ""
    session: str = ""


def _text(img, s, org, scale=0.55, color=WHITE, thick=1):
    x, y = org
    cv2.putText(img, s, (x + 1, y + 1), FONT, scale, (0, 0, 0), thick, cv2.LINE_AA)  # drop shadow
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def _letterbox(img: np.ndarray, W: int, H: int):
    h, w = img.shape[:2]
    s = min(W / w, H / h)
    nw, nh = int(round(w * s)), int(round(h * s))
    ox, oy = (W - nw) // 2, (H - nh) // 2
    return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR), s, ox, oy


def _apply_mode(img: np.ndarray, mode: str) -> np.ndarray:
    if mode == "NIGHT-GREEN":
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        g = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(g)
        return cv2.merge([(g * 0.25).astype(np.uint8), g, (g * 0.35).astype(np.uint8)])
    return img


def render(image: np.ndarray, st: HudState) -> np.ndarray:
    canvas = np.zeros((HUD_H, HUD_W, 3), np.uint8)
    view_w, view_h = HUD_W - PANEL_W, HUD_H - TOP_H
    view, s, ox, oy = _letterbox(_apply_mode(image, st.mode), view_w, view_h)
    oy += TOP_H
    canvas[oy:oy + view.shape[0], ox:ox + view.shape[1]] = view

    # --- pose overlays (each carries its own provenance tag) ---------------
    for m in st.poses:
        kps = np.asarray(m.value["keypoints_xy"], float) * s + (ox, oy)
        kc = np.asarray(m.value["keypoint_conf"], float)
        col = GREEN if m.sensor != "synthetic" else AMBER
        for a, b in COCO_SKELETON:
            if kc[a] > 0.3 and kc[b] > 0.3:
                cv2.line(canvas, tuple(map(int, kps[a])), tuple(map(int, kps[b])), col, 2, cv2.LINE_AA)
        for (x, y), c in zip(kps, kc):
            if c > 0.3:
                cv2.circle(canvas, (int(x), int(y)), 4, col, -1, cv2.LINE_AA)
        x0, y0, x1, y1 = (np.asarray(m.value["bbox_xyxy"], float) * s + (ox, oy, ox, oy)).astype(int)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), col, 1)
        _text(canvas, m.hud_tag, (x0, max(TOP_H + 16, y0 - 8)), 0.55, col, 1)

    # --- top bar ------------------------------------------------------------
    cv2.rectangle(canvas, (0, 0), (HUD_W, TOP_H), (18, 18, 18), -1)
    cv2.line(canvas, (0, TOP_H), (HUD_W, TOP_H), GREEN, 1)
    _text(canvas, "SPECTER-X", (14, 31), 0.9, GREEN, 2)
    _text(canvas, f"MODE {st.mode}", (210, 29), 0.6, WHITE)
    _text(canvas, f"{st.fps:5.1f} FPS", (420, 29), 0.6, WHITE)
    _text(canvas, f"POSE {st.infer_ms:5.1f} ms", (550, 29), 0.6, DIM)
    _text(canvas, "TGT LOCK" if st.pose_active else "NO TGT", (740, 29), 0.6,
          GREEN if st.pose_active else DIM, 1)
    _text(canvas, time.strftime("%H:%M:%S"), (HUD_W - 110, 29), 0.6, WHITE)

    # --- sensor health panel -----------------------------------------------
    px = HUD_W - PANEL_W
    cv2.rectangle(canvas, (px, TOP_H + 1), (HUD_W, HUD_H), (14, 14, 14), -1)
    cv2.line(canvas, (px, TOP_H), (px, HUD_H), (60, 60, 60), 1)
    _text(canvas, "SENSOR HEALTH", (px + 14, TOP_H + 30), 0.6, GREEN, 1)
    y = TOP_H + 62
    for ss in st.sensors:
        cv2.circle(canvas, (px + 22, y - 5), 7, ss.health.bgr, -1, cv2.LINE_AA)
        _text(canvas, ss.label, (px + 38, y), 0.52, WHITE)
        _text(canvas, ss.health.value, (px + 190, y), 0.48, ss.health.bgr)
        if ss.detail:
            _text(canvas, ss.detail[:30], (px + 38, y + 19), 0.40, DIM)
        y += 48

    # --- event ticker ---------------------------------------------------------
    y = HUD_H - 18 * max(1, len(st.ticker)) - 30
    _text(canvas, "EVENTS", (px + 14, y), 0.5, GREEN)
    for line in st.ticker:
        y += 18
        _text(canvas, line[:38], (px + 14, y), 0.36, DIM)
    _text(canvas, f"src:{st.source_name}  sess:{st.session[-6:]}", (12, HUD_H - 10), 0.42, DIM)
    return canvas
