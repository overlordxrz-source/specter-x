"""Team HUD overlays: teammates, peer contacts, mini-map, off-screen arrows.

Everything drawn here derives from Measurements (peer tracks keep their
Measurement ids) or pose/sensor records — the provenance rule covers the
network too. Peer contacts print `SRC: <UNIT>/<SENSOR> conf 0.xx`.
Without a heading reference the main view shows no arrows (never faked);
the north-up mini-map always works.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX
TEAM_GREEN = (90, 255, 120)
TEAM_BLUE = (255, 190, 80)
PEER_ORANGE = (60, 170, 255)
WHITE = (235, 235, 235)
DIM = (140, 140, 140)
RED = (70, 70, 240)


def _text(img, s, org, scale=0.5, color=WHITE, thick=1):
    x, y = int(org[0]), int(org[1])
    cv2.putText(img, s, (x + 1, y + 1), FONT, scale, (0, 0, 0), thick, cv2.LINE_AA)
    cv2.putText(img, s, (x, y), FONT, scale, color, thick, cv2.LINE_AA)


@dataclass
class TeammateView:
    unit_id: str
    distance_m: float
    bearing_deg: float      # compass bearing from own position (0 = north)
    behind_wall: bool = False  # set from latest UWB NLOS flag
    mode: str = "REL"
    rmse_m: float = 99.0

    def label(self) -> str:
        wall = " behind wall" if self.behind_wall else ""
        return f"{self.unit_id} {self.distance_m:.0f}m {self.bearing_deg:03.0f}deg{wall}"


@dataclass
class PeerContactView:
    position_enu: np.ndarray
    hud_tag: str            # "SRC: <UNIT>/<SENSOR> conf 0.xx"
    label: str = "contact"
    confidence: float = 0.5

    def short(self) -> str:
        return f"{self.label} {self.hud_tag}"


@dataclass
class TeamOverlayState:
    own_pos_enu: np.ndarray = field(default_factory=lambda: np.zeros(3))
    own_yaw_deg: Optional[float] = None  # compass heading; None = unknown
    teammates: List[TeammateView] = field(default_factory=list)
    contacts: List[PeerContactView] = field(default_factory=list)
    pose_badge: str = "POSE: REL ±--"
    fov_half_deg: float = 35.0


def bearing_between(own: np.ndarray, other: np.ndarray) -> Tuple[float, float]:
    """(distance_m, compass_bearing_deg) of other seen from own (ENU)."""
    d = np.asarray(other, float).reshape(3) - np.asarray(own, float).reshape(3)
    dist = float(np.linalg.norm(d[:2]))
    return dist, (math.degrees(math.atan2(d[0], d[1])) + 360.0) % 360.0


def relative_bearing(bearing_deg: float, own_yaw_deg: float) -> float:
    """Signed [-180, 180] bearing relative to heading."""
    return (bearing_deg - own_yaw_deg + 540.0) % 360.0 - 180.0


def offscreen_arrows(state: TeamOverlayState) -> List[Tuple[str, float, str]]:
    """(kind, rel_bearing_deg, text) for teammates/contacts outside the FOV.

    Empty when heading is unknown — arrows need a heading, and we do not
    invent one. Caller draws triangles at the screen edge along rel bearing.
    """
    if state.own_yaw_deg is None:
        return []
    out: List[Tuple[str, float, str]] = []
    for t in state.teammates:
        rel = relative_bearing(t.bearing_deg, state.own_yaw_deg)
        if abs(rel) > state.fov_half_deg:
            out.append(("teammate", rel, t.label()))
    for c in state.contacts:
        dist, brg = bearing_between(state.own_pos_enu, c.position_enu)
        rel = relative_bearing(brg, state.own_yaw_deg)
        if abs(rel) > state.fov_half_deg:
            out.append(("contact", rel, f"{c.label} {dist:.0f}m {c.hud_tag}"))
    return out


def draw_teammate_panel(img: np.ndarray, state: TeamOverlayState,
                        x: int, y: int) -> int:
    """Side-panel teammate list. Returns the y below the block."""
    _text(img, "TEAM", (x, y), 0.55, TEAM_GREEN, 1)
    y += 22
    _text(img, state.pose_badge, (x, y), 0.45, TEAM_BLUE, 1)
    y += 22
    if not state.teammates:
        _text(img, "no teammates heard", (x, y), 0.42, DIM)
        return y + 20
    for t in state.teammates:
        col = TEAM_GREEN if not t.behind_wall else PEER_ORANGE
        _text(img, t.label(), (x, y), 0.42, col)
        y += 20
        _text(img, f"  {t.mode} rmse {t.rmse_m:.1f}m", (x, y), 0.36, DIM)
        y += 18
    return y


def draw_peer_contacts(img: np.ndarray, state: TeamOverlayState,
                       x: int, y: int) -> int:
    _text(img, "PEER TRACKS", (x, y), 0.55, TEAM_GREEN, 1)
    y += 22
    if not state.contacts:
        _text(img, "none", (x, y), 0.42, DIM)
        return y + 20
    for c in state.contacts:
        dist, _ = bearing_between(state.own_pos_enu, c.position_enu)
        _text(img, f"{c.label} {dist:.0f}m", (x, y), 0.45, PEER_ORANGE, 1)
        y += 18
        _text(img, c.hud_tag[:44], (x, y), 0.38, WHITE)
        y += 18
    return y


def draw_offscreen_arrows(img: np.ndarray, state: TeamOverlayState,
                          view_x: int, view_y: int, view_w: int, view_h: int) -> None:
    """Edge triangles for out-of-FOV teammates/tracks (needs heading)."""
    for kind, rel, text in offscreen_arrows(state):
        side = -1 if rel < 0 else 1
        ax = view_x + (30 if side < 0 else view_w - 30)
        ay = view_y + view_h // 2
        col = TEAM_BLUE if kind == "teammate" else PEER_ORANGE
        tip = (ax + side * 22, ay)
        cv2.fillPoly(img, [np.array(
            [[ax - side * 10, ay - 12], tip, [ax - side * 10, ay + 12]])], col)
        tx = ax - side * 10 - (len(text) * 7 if side > 0 else 0)
        _text(img, text[:30], (int(tx), ay + 26), 0.38, col)


def draw_minimap(img: np.ndarray, state: TeamOverlayState,
                 x: int, y: int, size: int = 230) -> None:
    """North-up top-down map: own unit (centre-ish), teammates, peer tracks."""
    cv2.rectangle(img, (x, y), (x + size, y + size), (20, 20, 20), -1)
    cv2.rectangle(img, (x, y), (x + size, y + size), (80, 80, 80), 1)
    _text(img, "MAP N^", (x + 6, y + 18), 0.45, TEAM_GREEN, 1)
    pts = [state.own_pos_enu[:2]] + [np.asarray(t_bearing_pos(state, t)[:2])
                                     for t in state.teammates
                                     ] + [c.position_enu[:2] for c in state.contacts]
    if not pts:
        return
    allp = np.array([np.asarray(p, float).reshape(2) for p in pts])
    span = max(float(np.ptp(allp, axis=0).max()), 4.0)
    centre = allp.mean(axis=0)
    sc = (size - 30) / span

    def to_px(p) -> Tuple[int, int]:
        e, n = np.asarray(p, float).reshape(2) - centre
        return int(x + size / 2 + e * sc), int(y + size / 2 - n * sc)

    for c in state.contacts:
        cx, cy = to_px(c.position_enu[:2])
        cv2.drawMarker(img, (cx, cy), PEER_ORANGE, cv2.MARKER_DIAMOND, 12, 2)
    for t in state.teammates:
        tx, ty = to_px(t_bearing_pos(state, t)[:2])
        col = TEAM_BLUE if not t.behind_wall else DIM
        cv2.drawMarker(img, (tx, ty), col, cv2.MARKER_TRIANGLE_UP, 14, 2)
        _text(img, t.unit_id[:8], (tx + 8, ty), 0.36, col)
    ox, oy = to_px(state.own_pos_enu[:2])
    cv2.drawMarker(img, (ox, oy), TEAM_GREEN, cv2.MARKER_TILTED_CROSS, 14, 2)
    _text(img, "YOU", (ox + 8, oy), 0.36, TEAM_GREEN)
    _text(img, f"{span:.0f}m", (x + size - 44, y + size - 8), 0.36, DIM)


def t_bearing_pos(state: TeamOverlayState, t: TeammateView) -> np.ndarray:
    """Teammate ENU from own position + range/bearing (flat-earth, local use)."""
    brg = math.radians(t.bearing_deg)
    e = state.own_pos_enu[0] + t.distance_m * math.sin(brg)
    n = state.own_pos_enu[1] + t.distance_m * math.cos(brg)
    return np.array([e, n, state.own_pos_enu[2]])


def teammate_from_pose(unit_id: str, own_pos: np.ndarray,
                       peer_pos: Sequence[float], mode: str = "REL",
                       rmse_m: float = 99.0, behind_wall: bool = False) -> TeammateView:
    dist, brg = bearing_between(np.asarray(own_pos, float), np.asarray(peer_pos, float))
    return TeammateView(unit_id, dist, brg, behind_wall, mode, rmse_m)


def contact_from_report_tag(source_unit: str, source_sensor: str, confidence: float,
                            position_enu: Sequence[float],
                            label: str = "contact") -> PeerContactView:
    return PeerContactView(
        np.asarray(position_enu, float).reshape(3),
        f"SRC: {source_unit}/{source_sensor.upper()} conf {confidence:.2f}",
        label, float(confidence))
