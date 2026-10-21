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
from specter.hud.team_overlay import (
    TeamOverlayState,
    draw_minimap,
    draw_offscreen_arrows,
    draw_peer_contacts,
    draw_teammate_panel,
)
from specter.sensors.base import SensorStatus
from specter.sensors.di188.stats import ChannelState
from specter.sensors.nightvision.camera import COCO_SKELETON

HUD_W, HUD_H = 1280, 800
PANEL_W = 270
TOP_H = 44
FONT = cv2.FONT_HERSHEY_SIMPLEX
GREEN = (90, 255, 120)
AMBER = (40, 200, 255)
WHITE = (235, 235, 235)
DIM = (140, 140, 140)
RED = (60, 60, 235)

MODES = ["OPTICAL", "NIGHT-GREEN", "POD", "ANALOG", "CSI"]


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
    team: object = None  # TeamOverlayState when networking is up; None hides team UI
    analog: object = None  # DaqSnapshot when the DAQ is enabled; None hides the DAQ view
    supervisor: object = None  # SupervisorSnapshot or view dict; None hides the block
    csi: object = None  # CSI view dict; None hides the CSI view


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


def _spark(canvas, points, x, y, w, h, color):
    """Draw a bounded trace of (t, value) pairs."""
    cv2.rectangle(canvas, (x, y), (x + w, y + h), (26, 26, 26), -1)
    vals = [p[1] for p in points]
    if len(vals) < 2:
        return
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi, lo = lo + 1.0, lo - 1.0
    pad = (hi - lo) * 0.15
    lo, hi = lo - pad, hi + pad
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        px = int(x + (i / (n - 1)) * (w - 2) + 1)
        py = int(y + h - 2 - ((v - lo) / (hi - lo)) * (h - 4))
        pts.append((px, py))
    cv2.polylines(canvas, [np.array(pts, np.int32)], False, color, 1, cv2.LINE_AA)


def draw_analog_view(canvas, snap, x0, y0, w, h):
    """The DI-188 view: four channels, their state, and the calibration basis.

    A channel with no source attached is drawn as FLOATING / NOISE. Its counts
    are still shown (they are real ADC readings) but no volt value is drawn
    and the panel says in words that the reading is noise, not a measurement.
    """
    if snap is None:
        _text(canvas, "DAQ DISABLED", (x0 + 30, y0 + 60), 0.9, DIM, 2)
        return

    head = (f"{snap.model or 'DI-188'}  serial {snap.serial or '?'}  port {snap.port or '?'}"
            f"   {snap.rate_hz:g} Hz   frames {snap.frames}")
    _text(canvas, head, (x0 + 24, y0 + 26), 0.58, WHITE, 1)
    _text(canvas, f"CAL: {snap.calibration_basis}", (x0 + 24, y0 + 52), 0.55,
          AMBER if "UNCALIBRATED" in snap.calibration_basis else GREEN, 1)

    banner_y = y0 + 76
    if not snap.any_measurement:
        cv2.rectangle(canvas, (x0 + 20, banner_y), (x0 + w - 20, banner_y + 34),
                      (30, 22, 6), -1)
        cv2.rectangle(canvas, (x0 + 20, banner_y), (x0 + w - 20, banner_y + 34),
                      AMBER, 1)
        _text(canvas, "FLOATING INPUTS - VALUES ARE ADC NOISE, NOT MEASUREMENTS",
              (x0 + 34, banner_y + 23), 0.62, AMBER, 1)

    grid_y = banner_y + 48
    card_w = (w - 60) // 2
    card_h = (h - (grid_y - y0) - 40) // 2
    # the DI-188 has four channels; if more are configured, draw the first
    # four rather than letting the grid overflow the panel
    for i, ch in enumerate(snap.channels[:4]):
        cx = x0 + 20 + (i % 2) * (card_w + 20)
        cy = grid_y + (i // 2) * (card_h + 16)
        floating = ch.state is not ChannelState.CONNECTED
        col = AMBER if floating else GREEN
        cv2.rectangle(canvas, (cx, cy), (cx + card_w, cy + card_h), (20, 20, 20), -1)
        cv2.rectangle(canvas, (cx, cy), (cx + card_w, cy + card_h), col, 1)
        _text(canvas, f"{ch.label}  {ch.terminal}", (cx + 16, cy + 30), 0.62, WHITE, 1)
        badge = "FLOATING / NOISE" if floating else "CONNECTED"
        _text(canvas, badge, (cx + 16, cy + 56), 0.55, col, 1)
        counts = ch.stats.last if ch.stats.last is not None else 0.0
        _text(canvas, f"{counts:+.1f}", (cx + 16, cy + 100), 0.95, WHITE, 2)
        _text(canvas, "counts", (cx + 130, cy + 100), 0.5, DIM, 1)
        if floating:
            _text(canvas, "no source connected - not a measurement",
                  (cx + 16, cy + 124), 0.44, AMBER, 1)
        else:
            volts = "n/a" if ch.volts is None else f"{ch.volts:+.4f} V"
            _text(canvas, f"{volts}  ({ch.calibration_basis})",
                  (cx + 16, cy + 124), 0.5, GREEN, 1)
        _text(canvas, f"mean {ch.stats.mean:+.2f}   std {ch.stats.std:.2f}"
                      f"   min {ch.stats.minimum if ch.stats.n else 0:+.1f}"
                      f"   max {ch.stats.maximum if ch.stats.n else 0:+.1f}",
              (cx + 16, cy + 148), 0.46, DIM, 1)
        _spark(canvas, snap.series.get(ch.index, []), cx + 16, cy + 160,
               card_w - 32, max(40, card_h - 176), col)


def _get(obj, key, default=None):
    """Read a field from a dataclass snapshot or from a plain dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def draw_supervisor_block(canvas, snap, x, y):
    """Compact supervisor telemetry in the right-hand panel.

    The identity line is only drawn once the device has introduced itself -
    an unknown identity is stated, never guessed.
    """
    if snap is None:
        return y
    value = _get(snap, "state", "N/A")
    if hasattr(value, "value"):
        value = value.value
    available = _get(snap, "available", True)
    col = {"OK": GREEN, "DEGRADED": AMBER, "OFFLINE": RED}.get(value, DIM)
    if not available:
        col = AMBER
    _text(canvas, "SUPERVISOR", (x, y), 0.58, GREEN, 1)
    _text(canvas, value if available else "N/A", (x + 190, y), 0.5, col, 1)
    y += 20
    if not available:
        _text(canvas, "telemetry not available", (x, y), 0.44, AMBER, 1)
        y += 16
        detail = str(_get(snap, "detail", ""))[:30]
        if detail:
            _text(canvas, detail, (x, y), 0.38, DIM, 1)
            y += 15
        return y
    ident = _get(snap, "identity", None)
    if ident is None:
        _text(canvas, "identity not reported", (x, y), 0.44, AMBER, 1)
        y += 17
    else:
        board = ident.get("board", "") if isinstance(ident, dict) else ident.board
        chip = ident.get("chip", "") if isinstance(ident, dict) else ident.chip
        mac = ident.get("mac", "") if isinstance(ident, dict) else ident.mac
        fwv = ident.get("fw_version", "") if isinstance(ident, dict) else ident.fw_version
        fwb = ident.get("fw_build", "") if isinstance(ident, dict) else ident.fw_build
        _text(canvas, f"{board[:22]} {chip[:12]}", (x, y), 0.42, WHITE, 1)
        y += 16
        _text(canvas, f"mac {mac}", (x, y), 0.40, DIM, 1)
        y += 15
        _text(canvas, f"fw {fwv} ({fwb[:12]})", (x, y), 0.40, DIM, 1)
        y += 16
    _text(canvas, f"up {_get(snap, 'uptime_s', 0.0):.1f}s   hb {_get(snap, 'heartbeat_seq', 0)}",
          (x, y), 0.42, WHITE, 1)
    y += 16
    _text(canvas, f"hb age {_get(snap, 'heartbeat_age_s', 0.0):.1f}s   "
                  f"missed {_get(snap, 'missed_heartbeats', 0)}",
          (x, y), 0.40, DIM, 1)
    y += 15
    _text(canvas, f"dev health {_get(snap, 'device_health', 'UNKNOWN')}", (x, y),
          0.40, DIM, 1)
    y += 16
    return y


def draw_csi_view(canvas, view, x0, y0, w, h):
    """Subcarrier amplitudes and packet statistics for the CSI link."""
    if view is None:
        _text(canvas, "CSI NOT ENABLED", (x0 + 30, y0 + 60), 0.9, DIM, 2)
        return

    state = str(view.get("link_state", "N/A"))
    col = {"CONNECTED": GREEN, "STALLED": AMBER, "DISCONNECTED": RED,
           "ERROR": RED, "CONNECTING": AMBER}.get(state, DIM)
    _text(canvas, "CSI", (x0 + 24, y0 + 30), 0.9, GREEN, 2)
    _text(canvas, state, (x0 + 100, y0 + 30), 0.6, col, 1)
    _text(canvas, str(view.get("ap_mac", "-")), (x0 + 200, y0 + 30), 0.55, WHITE, 1)
    _text(canvas, f"ch {view.get('channel', '-')}   {view.get('rssi', '-')} dBm",
          (x0 + 400, y0 + 30), 0.55, WHITE, 1)
    _text(canvas, f"board {view.get('board_mac', '-')}", (x0 + 600, y0 + 30),
          0.5, DIM, 1)
    _text(canvas, f"dev ts {view.get('local_timestamp', '-')} us", (x0 + 800, y0 + 30),
          0.5, DIM, 1)

    # --- subcarrier amplitude scope ---------------------------------------
    scope_x = x0 + 30
    scope_y = y0 + 60
    scope_w = w - 60
    scope_h = int(h * 0.46)
    cv2.rectangle(canvas, (scope_x, scope_y), (scope_x + scope_w, scope_y + scope_h),
                  (12, 12, 12), -1)
    amps = view.get("amplitudes") or []
    if amps:
        peak = max(amps) or 1.0
        n = len(amps)
        bw = max(1, int(scope_w / n))
        for i, a in enumerate(amps):
            bh = int((a / peak) * (scope_h - 12))
            x = scope_x + 2 + i * bw
            cv2.rectangle(canvas, (x, scope_y + scope_h - 2 - bh),
                          (x + bw - 1, scope_y + scope_h - 2),
                          (90, 170, 255), -1)
        _text(canvas, f"subcarrier amplitude  ({n} carriers, peak {peak:.0f})",
              (scope_x + 8, scope_y + scope_h + 16), 0.45, DIM, 1)
        _text(canvas, "0", (scope_x + 4, scope_y + scope_h - 6), 0.4, DIM, 1)
        _text(canvas, str(n - 1), (scope_x + scope_w - 24, scope_y + scope_h - 6),
              0.4, DIM, 1)
    else:
        _text(canvas, "no subcarrier data yet", (scope_x + 12, scope_y + scope_h // 2),
              0.5, DIM, 1)

    # --- packet statistics -------------------------------------------------
    sy = scope_y + scope_h + 34
    cols = [
        ("packets", view.get("packets", 0)),
        ("packets/s", f"{view.get('packets_per_s', 0.0):.1f}"),
        ("id range", f"{view.get('first_id', '-')}..{view.get('last_id', '-')}"),
        ("seq gaps", view.get("gaps", 0)),
        ("missing", view.get("missing_packets", 0)),
        ("malformed", view.get("malformed", 0)),
        ("dropped", view.get("dropped", 0)),
        ("unknown lines", view.get("unknown_lines", 0)),
        ("silence", f"{view.get('silence_s', 0.0):.2f}s"),
        ("reconnects", view.get("reconnects", 0)),
        ("uptime", f"{view.get('uptime_s', 0.0):.0f}s"),
        ("bytes", view.get("bytes", 0)),
    ]
    for i, (label, value) in enumerate(cols):
        cx = x0 + 40 + (i % 6) * 160
        cy = sy + (i // 6) * 46
        _text(canvas, label, (cx, cy), 0.44, DIM, 1)
        bad = label in ("seq gaps", "missing", "malformed", "dropped", "unknown lines") \
            and value
        _text(canvas, str(value), (cx, cy + 22), 0.6,
              RED if bad else WHITE, 1)


def render(image: np.ndarray, st: HudState) -> np.ndarray:
    canvas = np.zeros((HUD_H, HUD_W, 3), np.uint8)
    view_w, view_h = HUD_W - PANEL_W, HUD_H - TOP_H
    if st.mode == "ANALOG":
        draw_analog_view(canvas, st.analog, 0, TOP_H, view_w, view_h)
        view, s, ox, oy = None, 1.0, 0, TOP_H
    elif st.mode == "CSI":
        draw_csi_view(canvas, st.csi, 0, TOP_H, view_w, view_h)
        view, s, ox, oy = None, 1.0, 0, TOP_H
    else:
        view, s, ox, oy = _letterbox(_apply_mode(image, st.mode), view_w, view_h)
        oy += TOP_H
        canvas[oy:oy + view.shape[0], ox:ox + view.shape[1]] = view

    # --- pose overlays (each carries its own provenance tag) ---------------
    for m in (st.poses if st.mode not in ("ANALOG", "CSI") else []):
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
    team = st.team if isinstance(st.team, TeamOverlayState) else None
    if team is not None:
        _text(canvas, team.pose_badge[:24], (880, 29), 0.55, AMBER, 1)
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

    # --- supervisor block -----------------------------------------------------
    # In CSI mode the view already carries the link state and the health list
    # carries the supervisor row, so the block is left out to keep the panel
    # from colliding with the event ticker.
    if st.supervisor is not None and st.mode != "CSI":
        y = draw_supervisor_block(canvas, st.supervisor, px + 14, y + 6) + 6

    # --- team block (teammates + peer tracks, provenance-tagged) ------------
    if team is not None:
        y = draw_teammate_panel(canvas, team, px + 14, y + 6) + 6
        y = draw_peer_contacts(canvas, team, px + 14, y) + 6

    # --- event ticker ---------------------------------------------------------
    y = HUD_H - 18 * max(1, len(st.ticker)) - 30
    _text(canvas, "EVENTS", (px + 14, y), 0.5, GREEN)
    for line in st.ticker:
        y += 18
        _text(canvas, line[:38], (px + 14, y), 0.36, DIM)
    _text(canvas, f"src:{st.source_name}  sess:{st.session[-6:]}", (12, HUD_H - 10), 0.42, DIM)
    if team is not None and (team.teammates or team.contacts):
        draw_minimap(canvas, team, 12, HUD_H - 252, 230)
        draw_offscreen_arrows(canvas, team, 0, TOP_H, HUD_W - PANEL_W, HUD_H - TOP_H)
    return canvas
