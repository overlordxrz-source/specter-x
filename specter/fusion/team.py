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


def _vector3(value, where: str) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where} must be a finite 3-vector") from exc
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError(f"{where} must be a finite 3-vector")
    return vector


def _covariance3(value, where: str) -> np.ndarray:
    try:
        covariance = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where} must be a finite 3x3 covariance") from exc
    if covariance.shape != (3, 3) or not np.isfinite(covariance).all():
        raise ValueError(f"{where} must be a finite 3x3 covariance")
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1e-10):
        raise ValueError(f"{where} must be symmetric")
    if (np.diag(covariance) < 0.0).any():
        raise ValueError(f"{where} cannot have negative variance")
    try:
        smallest = float(np.linalg.eigvalsh(covariance).min())
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{where} is not valid covariance") from exc
    if smallest < -1e-10:
        raise ValueError(f"{where} must be positive semidefinite")
    return covariance


def _evidence_ids(ids, where: str) -> list[str]:
    try:
        values = list(ids)
    except TypeError as exc:
        raise ValueError(f"{where} must be an iterable of IDs") from exc
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{where} must contain nonempty string IDs")
    return list(dict.fromkeys(values))


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
    # "single" / "independent" / "shared_evidence"; shared evidence is not
    # precision-fused and therefore retains one source's covariance.
    fusion_status: str = "single"


@dataclass
class _LocalEntry:
    track_id: int
    position: np.ndarray
    covariance: np.ndarray
    sensor: str
    measurement_ids: List[str]
    confidence: float
    label: str
    observed_at: float
    frame_id: str


@dataclass
class _PeerEntry:
    report: TrackReport
    position: np.ndarray
    covariance: np.ndarray
    observed_at: Optional[float]  # mapped local time; None means unknown
    frame_id: str


@dataclass
class _Contribution:
    position: np.ndarray
    covariance: np.ndarray
    contributor: Tuple[str, str]
    measurement_ids: Tuple[str, ...]
    confidence: float
    label: str
    observed_at: float
    local: bool


class TeamFuser:
    """Fuse local ENU detections with peer TrackReports.

    A peer report carries sender host/report time, not an acquisition time.
    Its age is therefore unknown unless the caller supplies a clock offset
    (``peer_time - local_time``) at ingest. Unknown, stale or future reports
    are never admitted. Anchor transforms are not implemented: local and
    peer inputs must declare the same shared frame.

    Precision fusion is only allowed when every contribution carries
    non-empty, pairwise-disjoint parent IDs. Otherwise the newest
    contribution represents the track with its own covariance and the
    result is marked ``shared_evidence``. This avoids treating duplicated or
    looped evidence as independent measurements.
    """

    def __init__(self, unit_id: str, gate: float = GATE_CHI2_3DOF_95,
                 max_age_s: float = 5.0, max_future_s: float = 1.0,
                 frame_id: str = "enu") -> None:
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError("unit_id must be a nonempty string")
        if not math.isfinite(float(gate)) or float(gate) <= 0.0:
            raise ValueError("gate must be finite and positive")
        if not math.isfinite(float(max_age_s)) or float(max_age_s) < 0.0:
            raise ValueError("max_age_s must be finite and nonnegative")
        if not math.isfinite(float(max_future_s)) or float(max_future_s) < 0.0:
            raise ValueError("max_future_s must be finite and nonnegative")
        if not isinstance(frame_id, str) or not frame_id:
            raise ValueError("frame_id must be a nonempty string")
        self.unit_id = unit_id
        self.gate = float(gate)
        self.max_age_s = float(max_age_s)
        self.max_future_s = float(max_future_s)
        self.frame_id = frame_id
        self._locals: List[_LocalEntry] = []
        self._peers: List[_PeerEntry] = []
        self.merged: List[TeamTrack] = []
        self._next_id = 1

    # -- inputs ---------------------------------------------------------
    def add_local(self, track_id: int, pos_enu: Sequence[float], cov_3x3,
                  sensor: str, measurement_ids: Sequence[str] = (),
                  confidence: float = 0.7, label: str = "contact",
                  *, t_host: Optional[float] = None,
                  frame_id: Optional[str] = None) -> None:
        frame = self.frame_id if frame_id is None else frame_id
        if not isinstance(frame, str) or not frame:
            raise ValueError("frame_id must be a nonempty string")
        if frame != self.frame_id:
            raise ValueError(
                f"local frame {frame!r} does not match fuser frame {self.frame_id!r}"
            )
        if t_host is None:
            observed_at = time.time()
        else:
            observed_at = float(t_host)
            if not math.isfinite(observed_at) or observed_at < 0.0:
                raise ValueError("local t_host must be finite and nonnegative")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be finite in [0, 1]")
        self._locals.append(_LocalEntry(
            track_id, _vector3(pos_enu, "local position"),
            _covariance3(cov_3x3, "local covariance"), sensor,
            _evidence_ids(measurement_ids, "local measurement_ids"),
            confidence, label, observed_at, frame))

    def ingest_report(self, rep: TrackReport,
                      own_anchor: Optional[Sequence[float]] = None,
                      *, clock_offset_s: Optional[float] = None) -> None:
        """Store a peer report in the local frame.

        ``clock_offset_s`` is the established mapping ``peer_t - local_t``.
        Omit it when age is unknown; the report will not be fused. Anchor
        shifting is not implemented and passing ``own_anchor`` is rejected
        rather than inventing a transform.
        """
        if own_anchor is not None:
            raise ValueError("anchor transform is not implemented; use a shared frame")
        if not isinstance(rep, TrackReport):
            raise TypeError("TrackReport required")
        frame = getattr(rep, "frame_id", "enu")
        if not isinstance(frame, str) or not frame:
            raise ValueError("peer frame_id must be a nonempty string")
        if frame != self.frame_id:
            raise ValueError(
                f"peer frame {frame!r} does not match fuser frame {self.frame_id!r}"
            )
        report_time = float(rep.t_host)
        if not math.isfinite(report_time) or report_time < 0.0:
            raise ValueError("peer t_host must be finite and nonnegative")
        if clock_offset_s is None:
            observed_at = None
        else:
            offset = float(clock_offset_s)
            if not math.isfinite(offset):
                raise ValueError("clock_offset_s must be finite")
            observed_at = report_time - offset
            if not math.isfinite(observed_at) or observed_at < 0.0:
                raise ValueError("mapped peer time must be finite and nonnegative")
        self._peers.append(_PeerEntry(
            rep, _vector3(rep.position_enu, "peer position"),
            _covariance3(rep.cov_3x3, "peer covariance"), observed_at, frame))

    # -- fusion ----------------------------------------------------------
    def _eligible(self, observed_at: Optional[float], t_now: float) -> bool:
        if observed_at is None or not math.isfinite(observed_at):
            return False
        age = t_now - observed_at
        return -self.max_future_s <= age <= self.max_age_s

    def fuse(self, t_now: Optional[float] = None) -> List[TeamTrack]:
        t_now = time.time() if t_now is None else float(t_now)
        if not math.isfinite(t_now) or t_now < 0.0:
            raise ValueError("t_now must be finite and nonnegative")
        locals_ = [entry for entry in self._locals
                   if self._eligible(entry.observed_at, t_now)]
        peers = [entry for entry in self._peers
                 if self._eligible(entry.observed_at, t_now)]
        n, m = len(locals_), len(peers)
        cost = np.full((n, m), np.inf)
        for i, local in enumerate(locals_):
            for j, peer in enumerate(peers):
                d2 = mahalanobis2(
                    local.position, local.covariance, peer.position, peer.covariance
                )
                if d2 <= self.gate:
                    cost[i, j] = d2
        matched_l, matched_p = set(), set()
        merged: List[TeamTrack] = []
        for i, j in _assign(np.nan_to_num(cost, nan=np.inf)):
            if not np.isfinite(cost[i, j]):
                continue
            matched_l.add(i)
            matched_p.add(j)
            merged.append(self._merge_one([locals_[i]], [peers[j]]))
        for i, local in enumerate(locals_):
            if i not in matched_l:
                merged.append(self._merge_one([local], []))
        for j, peer in enumerate(peers):
            if j not in matched_p:
                merged.append(self._merge_one([], [peer]))
        self.merged = [track for track in merged
                       if self._eligible(track.last_update, t_now)]
        self._locals.clear()
        self._peers.clear()
        return self.merged

    @staticmethod
    def _fusion_status(contributions: Sequence[_Contribution]) -> str:
        if len(contributions) <= 1:
            return "single"
        seen: set[str] = set()
        for contribution in contributions:
            ids = set(contribution.measurement_ids)
            if not ids or seen.intersection(ids):
                return "shared_evidence"
            seen.update(ids)
        return "independent"

    def _merge_one(self, locals_: List[_LocalEntry],
                   peers: List[_PeerEntry]) -> TeamTrack:
        contributions = [
            _Contribution(
                local.position, local.covariance, (self.unit_id, local.sensor),
                tuple(local.measurement_ids), local.confidence, local.label,
                local.observed_at, True,
            )
            for local in locals_
        ] + [
            _Contribution(
                peer.position, peer.covariance,
                (peer.report.source_unit, peer.report.source_sensor),
                tuple(_evidence_ids(peer.report.measurement_ids, "peer measurement_ids")),
                peer.report.confidence, peer.report.label,
                peer.observed_at, False,
            )
            for peer in peers
        ]
        if not contributions:
            raise ValueError("cannot merge an empty observation set")
        status = self._fusion_status(contributions)
        contributors = [contribution.contributor for contribution in contributions]
        measurement_ids = list(dict.fromkeys(
            measurement_id
            for contribution in contributions
            for measurement_id in contribution.measurement_ids
        ))
        last_update = max(contribution.observed_at for contribution in contributions)
        if status == "independent":
            precisions = [
                np.linalg.inv(contribution.covariance + np.eye(3) * 1e-9)
                for contribution in contributions
            ]
            information = sum(precisions)
            covariance = np.linalg.inv(information)
            position = covariance @ sum(
                precision @ contribution.position
                for precision, contribution in zip(precisions, contributions)
            )
            confidence = float(np.mean(
                [contribution.confidence for contribution in contributions]
            ))
            label = locals_[0].label if locals_ else peers[0].report.label
        else:
            selected = max(
                contributions,
                key=lambda contribution: (contribution.observed_at, contribution.local),
            )
            position = selected.position
            covariance = selected.covariance
            confidence = selected.confidence
            label = selected.label
        track = TeamTrack(
            self._next_id,
            position,
            covariance,
            contributors,
            measurement_ids,
            confidence,
            label,
            last_update,
            status,
        )
        self._next_id += 1
        return track

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
