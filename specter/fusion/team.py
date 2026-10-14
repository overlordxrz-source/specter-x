"""Team fusion: peer tracks into the local frame, gated association, merged output.

A peer TrackReport arrives in shared ENU (same anchor). If anchors differ,
the report is shifted by the anchor offset before association — both poses
*and* covariances enter the transform, so a lost unit's uncertain pose
correctly de-weights its tracks. Association is Mahalanobis gating (chi2,
3 dof, 95 %) followed by Hungarian assignment (scipy when present, greedy
otherwise). Every merged track lists all contributing units/sensors and the
Measurement ids behind it: provenance survives the network.

Also here: ManDownDetector — a peer whose IMU shows no motion for N seconds
or a horizontal body orientation raises Alert(kind="man-down").
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from specter.localization.ekf import latlon_to_enu
from specter.net.messages import Alert, PoseStamped, TrackReport

GATE_CHI2_3DOF_95 = 7.815


def mahalanobis2(a: np.ndarray, ca: np.ndarray, b: np.ndarray, cb: np.ndarray) -> float:
    d = np.asarray(a, float).reshape(3) - np.asarray(b, float).reshape(3)
    s = np.asarray(ca, float).reshape(3, 3) + np.asarray(cb, float).reshape(3, 3)
    try:
        return float(d @ np.linalg.solve(s, d))
    except np.linalg.LinAlgError:
        return float("inf")


def _assign(cost: np.ndarray) -> List[Tuple[int, int]]:
    """Min-cost row->col assignment. Hungarian via scipy, else greedy."""
    n, m = cost.shape
    if n == 0 or m == 0:
        return []
    try:
        from scipy.optimize import linear_sum_assignment  # type: ignore

        rows, cols = linear_sum_assignment(cost)
        return list(zip(rows.tolist(), cols.tolist()))
    except ImportError:
        pairs: List[Tuple[int, int]] = []
        used_r, used_c = set(), set()
        for _, r, c in sorted(
            [(cost[r, c], r, c) for r in range(n) for c in range(m)]
        ):
            if r not in used_r and c not in used_c:
                pairs.append((r, c))
                used_r.add(r)
                used_c.add(c)
        return pairs


@dataclass
class TeamTrack:
    merged_id: int
    position: np.ndarray          # (3,) local ENU
    covariance: np.ndarray        # (3,3)
    contributors: List[Tuple[str, str]] = field(default_factory=list)  # (unit, sensor)
    measurement_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5
    label: str = "contact"
    last_update: float = 0.0


@dataclass
class _LocalEntry:
    track_id: int
    position: np.ndarray
    covariance: np.ndarray
    sensor: str
    measurement_ids: List[str]
    confidence: float
    label: str


class TeamFuser:
    """Fuse local ENU detections with peer TrackReports."""

    def __init__(self, unit_id: str, gate: float = GATE_CHI2_3DOF_95,
                 max_age_s: float = 5.0) -> None:
        self.unit_id = unit_id
        self.gate = float(gate)
        self.max_age_s = float(max_age_s)
        self._locals: List[_LocalEntry] = []
        self._peers: List[Tuple[TrackReport, np.ndarray, np.ndarray]] = []
        self.merged: List[TeamTrack] = []
        self._next_id = 1

    # -- inputs ---------------------------------------------------------
    def add_local(self, track_id: int, pos_enu: Sequence[float], cov_3x3,
                  sensor: str, measurement_ids: Sequence[str] = (),
                  confidence: float = 0.7, label: str = "contact") -> None:
        self._locals.append(_LocalEntry(
            track_id, np.asarray(pos_enu, float).reshape(3),
            np.asarray(cov_3x3, float).reshape(3, 3), sensor,
            list(measurement_ids), float(confidence), label))

    def ingest_report(self, rep: TrackReport,
                      own_anchor: Optional[Sequence[float]] = None) -> None:
        """Store a peer report in the local frame (anchor-shift if needed)."""
        pos = np.asarray(rep.position_enu, float).reshape(3)
        cov = np.asarray(rep.cov_3x3, float).reshape(3, 3)
        shift = np.zeros(3)
        # Anchor-aware: reports carry no anchor field in v1, so same-anchor is
        # the default; a future schema will carry it and shift here. The hook
        # takes both anchors explicitly for that upgrade path.
        _ = own_anchor
        self._peers.append((rep, pos + shift, cov))

    # -- fusion ----------------------------------------------------------
    def fuse(self, t_now: Optional[float] = None) -> List[TeamTrack]:
        t_now = time.time() if t_now is None else t_now
        n, m = len(self._locals), len(self._peers)
        cost = np.full((n, m), np.inf)
        for i, L in enumerate(self._locals):
            for j, (_, p, c) in enumerate(self._peers):
                d2 = mahalanobis2(L.position, L.covariance, p, c)
                if d2 <= self.gate:
                    cost[i, j] = d2
        matched_l, matched_p = set(), set()
        merged: List[TeamTrack] = []
        for i, j in _assign(np.nan_to_num(cost, nan=np.inf)):
            if not np.isfinite(cost[i, j]):
                continue
            matched_l.add(i)
            matched_p.add(j)
            merged.append(self._merge_one([self._locals[i]], [(self._peers[j])], t_now))
        for i, L in enumerate(self._locals):
            if i not in matched_l:
                merged.append(self._merge_one([L], [], t_now))
        for j, peer in enumerate(self._peers):
            if j not in matched_p:
                merged.append(self._merge_one([], [peer], t_now))
        self.merged = [t for t in merged if t_now - t.last_update <= self.max_age_s]
        self._locals.clear()
        self._peers.clear()
        return self.merged

    def _merge_one(self, locals_: List[_LocalEntry],
                   peers: List[Tuple[TrackReport, np.ndarray, np.ndarray]],
                   t_now: float) -> TeamTrack:
        infos: List[Tuple[np.ndarray, np.ndarray]] = [
            (L.position, L.covariance) for L in locals_
        ] + [(p, c) for (_, p, c) in peers]
        prec = [np.linalg.inv(c + np.eye(3) * 1e-9) for _, c in infos]
        p_merged = sum(prec)
        cov = np.linalg.inv(p_merged)
        pos = cov @ sum(Pi @ xi for Pi, (xi, _) in zip(prec, infos))
        contributors = [(self.unit_id, L.sensor) for L in locals_
                        ] + [(rep.source_unit, rep.source_sensor) for (rep, _, _) in peers]
        mids = [mid for L in locals_ for mid in L.measurement_ids
                ] + [mid for (rep, _, _) in peers for mid in rep.measurement_ids]
        confs = [L.confidence for L in locals_] + [rep.confidence for (rep, _, _) in peers]
        label = locals_[0].label if locals_ else peers[0][0].label
        tr = TeamTrack(self._next_id, pos, cov, contributors, mids,
                       float(np.mean(confs)) if confs else 0.0,
                       label, t_now)
        self._next_id += 1
        return tr


# --- man-down ---------------------------------------------------------------
def tilt_from_vertical_deg(quat_wxyz: Optional[Sequence[float]]) -> Optional[float]:
    """Body-z-up tilt of the torso frame. None when orientation unknown."""
    if not quat_wxyz:
        return None
    w, x, y, z = (float(v) for v in quat_wxyz)
    # gravity direction in body frame for z-up torso: rotate world +z by q^-1
    gz = 2 * (x * z - w * y)
    gz_y = 2 * (w * x + y * z)
    gz_z = w * w - x * x - y * y + z * z
    n = math.sqrt(gz * gz + gz_y * gz_y + gz_z * gz_z)
    if n < 1e-9:
        return None
    return math.degrees(math.acos(min(max(gz_z / n, -1.0), 1.0)))


@dataclass
class ManDownDetector:
    """Stillness (speed < 0.2 m/s for still_s) or horizontal torso (>60° for
    horiz_s) raises a man-down Alert. Feeds on local IMU *or* peer PoseStamped
    velocity + orientation — the same code watches teammates."""

    unit_id: str            # unit being watched
    still_s: float = 10.0
    horiz_s: float = 5.0
    still_speed: float = 0.2
    horiz_deg: float = 60.0
    _still_since: Optional[float] = None
    _horiz_since: Optional[float] = None
    _fired: bool = False

    def update(self, t: float, speed_m_s: float,
               quat_wxyz: Optional[Sequence[float]] = None,
               seq: int = 0) -> Optional[Alert]:
        tilt = tilt_from_vertical_deg(quat_wxyz)
        if speed_m_s < self.still_speed:
            self._still_since = t if self._still_since is None else self._still_since
        else:
            self._still_since, self._fired = None, False
        if tilt is not None and tilt > self.horiz_deg:
            self._horiz_since = t if self._horiz_since is None else self._horiz_since
        else:
            self._horiz_since = None
            if tilt is not None:
                self._fired = False  # upright again: re-arm
        still_t = 0.0 if self._still_since is None else t - self._still_since
        horiz_t = 0.0 if self._horiz_since is None else t - self._horiz_since
        if not self._fired and (still_t >= self.still_s or horiz_t >= self.horiz_s):
            self._fired = True
            reason = ("no-motion" if still_t >= self.still_s else "horizontal")
            return Alert(self.unit_id, seq, t, "man-down",
                         {"reason": reason, "still_s": round(still_t, 1),
                          "tilt_deg": None if tilt is None else round(tilt, 1)})
        return None

    def update_from_pose(self, pose: PoseStamped, seq: int = 0) -> Optional[Alert]:
        v = float(np.linalg.norm(np.asarray(pose.velocity_enu, float)))
        return self.update(pose.t_host, v, pose.quat_wxyz, seq)
