"""Per-unit pose estimation: error-state-style EKF in a shared local ENU frame.

Fuses IMU (prediction), GNSS (outdoor absolute, anchors the ENU origin at
the first fix) and UWB ranges to peers (relative). A visual-odometry hook
(update_vo) is reserved for later stages.

Frames: internally metres in local ENU (x east, y north, z up). GNSS fixes
arrive in frame "wgs84" and are converted at the anchor. With no GNSS the
filter keeps a relative frame from UWB + IMU and reports mode "REL" so the
HUD can say so honestly. Every pose carries covariance; uncertainty is
reported as RMSE = sqrt(trace(P_pos)) — never a fake-precise point.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from specter.fusion.measurement import Measurement

EARTH_R_M = 6_371_000.0
GNSS_TIMEOUT_S = 5.0

# Receiver-side validity contract for a GNSS update. These are deliberately
# conservative guards, not a substitute for the receiver's own fix flags or a
# geoid/ellipsoid conversion.
GNSS_VALID_FIX_TYPE = 3          # UBX FIX_3D; NMEA fallback maps usable GGA to 3
GNSS_MIN_SATELLITES = 4
GNSS_MAX_SATELLITES = 64
GNSS_LAT_LIMIT_DEG = 90.0
GNSS_LON_LIMIT_DEG = 180.0
GNSS_MIN_ALT_M = -1_000.0
GNSS_MAX_ALT_M = 20_000.0
GNSS_MAX_FUTURE_S = 1.0
GNSS_TIME_EPSILON_S = 1e-6
GNSS_ALT_DATUMS = frozenset({"wgs84_hae", "msl"})


def _finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _fix_integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _fix_covariance(value) -> np.ndarray:
    if value is None:
        raise ValueError("GNSS covariance is required")
    try:
        covariance = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("GNSS covariance must be a finite 3x3 matrix") from exc
    if covariance.shape != (3, 3) or not np.isfinite(covariance).all():
        raise ValueError("GNSS covariance must be a finite 3x3 matrix")
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1e-10):
        raise ValueError("GNSS covariance must be symmetric")
    if (np.diag(covariance) <= 0.0).any():
        raise ValueError("GNSS covariance must have positive variances")
    try:
        smallest = float(np.linalg.eigvalsh(covariance).min())
    except np.linalg.LinAlgError as exc:
        raise ValueError("GNSS covariance is invalid") from exc
    if smallest < -1e-10:
        raise ValueError("GNSS covariance must be positive semidefinite")
    return covariance


def latlon_to_enu(lat: float, lon: float, alt: float,
                  anchor: Tuple[float, float, float]) -> np.ndarray:
    """Equirectangular projection about anchor (lat0, lon0, alt0). Good for team areas."""
    lat0, lon0, alt0 = anchor
    d_lat = math.radians(lat - lat0)
    d_lon = math.radians(lon - lon0)
    x = d_lon * EARTH_R_M * math.cos(math.radians(lat0))
    y = d_lat * EARTH_R_M
    return np.array([x, y, alt - alt0], dtype=float)


def enu_to_latlon(enu: np.ndarray, anchor: Tuple[float, float, float]) -> Tuple[float, float, float]:
    lat0, lon0, alt0 = anchor
    x, y, z = (float(v) for v in enu)
    lat = lat0 + math.degrees(y / EARTH_R_M)
    lon = lon0 + math.degrees(x / (EARTH_R_M * math.cos(math.radians(lat0))))
    return lat, lon, alt0 + z


@dataclass
class UnitPose:
    unit_id: str
    position: np.ndarray       # (3,) ENU metres
    velocity: np.ndarray       # (3,) m/s
    covariance: np.ndarray     # (6,6) [pos; vel]
    mode: str = "REL"          # "REL" | "GNSS"
    anchor: Optional[Tuple[float, float, float]] = None
    t: float = 0.0
    measurement_ids: List[str] = field(default_factory=list)

    @property
    def pos_rmse(self) -> float:
        return float(np.sqrt(max(np.trace(self.covariance[:3, :3]), 0.0)))

    def hud_badge(self) -> str:
        return f"POSE: {self.mode} ±{self.pos_rmse:.1f}m"


class PoseEKF:
    """6-state [pos, vel] Kalman filter with GNSS + UWB-range updates."""

    def __init__(self, unit_id: str,
                 init_pos_std: float = 5.0, init_vel_std: float = 1.0,
                 accel_noise: float = 0.5, allow_simulated: bool = False) -> None:
        if not isinstance(allow_simulated, bool):
            raise ValueError("allow_simulated must be boolean")
        self.unit_id = unit_id
        self.allow_simulated = allow_simulated
        self.x = np.zeros(6)
        self.P = np.diag([init_pos_std**2] * 3 + [init_vel_std**2] * 3)
        self.accel_noise = float(accel_noise)
        self.anchor: Optional[Tuple[float, float, float]] = None
        self.mode = "REL"
        self._last_gnss_t: Optional[float] = None
        self._gnss_alt_datum: Optional[str] = None
        self._t = 0.0
        self.measurement_ids: List[str] = []
        self._started = False

    # -- core ----------------------------------------------------------
    def _ensure_started(self, t: float) -> None:
        if not self._started:
            self._t = t
            self._started = True

    def predict(
        self,
        dt: float,
        accel_enu: Optional[np.ndarray] = None,
        t: Optional[float] = None,
    ) -> UnitPose:
        dt = float(dt)
        next_t = self._t + dt if t is None else float(t)
        if not math.isfinite(dt) or dt < 0 or not math.isfinite(next_t):
            raise ValueError("prediction requires finite nonnegative dt and time")
        if self._started and next_t < self._t:
            raise ValueError("prediction time cannot move backwards")
        F = np.eye(6)
        F[:3, 3:] = np.eye(3) * dt
        u = np.zeros(6)
        if accel_enu is not None:
            a = np.asarray(accel_enu, float).reshape(3)
            u[:3] = 0.5 * a * dt * dt
            u[3:] = a * dt
        self.x = F @ self.x + u
        G = np.vstack([np.eye(3) * 0.5 * dt * dt, np.eye(3) * dt])
        self.P = F @ self.P @ F.T + (G @ G.T) * self.accel_noise**2
        self._ensure_started(next_t)
        self._t = next_t
        self._refresh_mode()
        return self.pose()

    def update_gnss(self, m: Measurement) -> UnitPose:
        """Apply a validated 3D GNSS fix.

        Validation happens entirely before state mutation. ``t_host`` is local
        host time; it must be finite, nonnegative and not move backwards.
        A small forward tolerance covers ordinary scheduling jitter. The
        receiver's altitude datum is explicit and cannot change after anchor.
        """
        if m.kind != "gnss_fix":
            raise ValueError(f"expected gnss_fix, got {m.kind}")
        if m.sensor != "gnss" or m.frame_id != "wgs84":
            raise ValueError("GNSS fix must be sensor 'gnss' in frame 'wgs84'")
        if not isinstance(m.value, dict):
            raise ValueError("GNSS value object required")
        v = m.value
        fix_type = _fix_integer(v.get("fix_type"), "fix_type")
        if fix_type != GNSS_VALID_FIX_TYPE:
            raise ValueError("a 3D GNSS fix is required")
        num_sv = _fix_integer(v.get("num_sv"), "num_sv")
        if not GNSS_MIN_SATELLITES <= num_sv <= GNSS_MAX_SATELLITES:
            raise ValueError("GNSS satellite count outside receiver contract")
        sim = v.get("sim")
        if not isinstance(sim, bool):
            raise ValueError("GNSS sim marker must be an explicit boolean")
        if sim and not self.allow_simulated:
            raise ValueError("simulated GNSS requires explicit allow_simulated")
        alt_datum = v.get("alt_datum")
        if not isinstance(alt_datum, str) or alt_datum not in GNSS_ALT_DATUMS:
            raise ValueError("explicit supported GNSS altitude datum required")
        lat = _finite_number(v.get("lat_deg"), "latitude")
        lon = _finite_number(v.get("lon_deg"), "longitude")
        alt = _finite_number(v.get("alt_m"), "altitude")
        if not -GNSS_LAT_LIMIT_DEG <= lat <= GNSS_LAT_LIMIT_DEG:
            raise ValueError("latitude outside geographic bounds")
        if not -GNSS_LON_LIMIT_DEG <= lon <= GNSS_LON_LIMIT_DEG:
            raise ValueError("longitude outside geographic bounds")
        if not GNSS_MIN_ALT_M <= alt <= GNSS_MAX_ALT_M:
            raise ValueError("altitude outside geographic bounds")
        h_acc = _finite_number(v.get("h_acc_m"), "horizontal accuracy")
        v_acc = _finite_number(v.get("v_acc_m"), "vertical accuracy")
        if h_acc <= 0.0 or v_acc <= 0.0:
            raise ValueError("GNSS accuracy must be positive")
        if m.confidence is None:
            raise ValueError("GNSS confidence must be explicit")
        confidence = _finite_number(m.confidence, "confidence")
        if not 0.0 < confidence <= 1.0:
            raise ValueError("GNSS confidence must be in (0, 1]")
        covariance = _fix_covariance(m.covariance)
        timestamp = _finite_number(m.t_host, "t_host")
        if timestamp < 0.0:
            raise ValueError("GNSS t_host must be nonnegative")
        if m.t_sensor is not None:
            _finite_number(m.t_sensor, "t_sensor")
        # The first valid GNSS fix may establish the wall-clock epoch even if
        # prediction started from t=0. Once GNSS time is established, reports
        # must not move backwards or jump implausibly far ahead.
        if self._last_gnss_t is not None:
            if timestamp < self._t - GNSS_TIME_EPSILON_S:
                raise ValueError("GNSS timestamp is older than the filter clock")
            if timestamp > self._t + GNSS_MAX_FUTURE_S:
                raise ValueError("GNSS timestamp is too far in the future")
        if self._gnss_alt_datum is not None and alt_datum != self._gnss_alt_datum:
            raise ValueError("GNSS altitude datum changed after anchor")
        if self.anchor is None:
            self.anchor = (lat, lon, alt)
            # First fix defines the origin: snap state there, keep velocity.
            self.x[:3] = 0.0
        self._gnss_alt_datum = alt_datum
        z = latlon_to_enu(lat, lon, alt, self.anchor)
        H = np.hstack([np.eye(3), np.zeros((3, 3))])
        self._linear_update(z, H, covariance)
        self._last_gnss_t = timestamp
        self._ensure_started(timestamp)
        self._t = timestamp
        self.measurement_ids.append(m.id)
        self._refresh_mode()
        return self.pose()

    def update_range(self, m: Measurement, peer_pos: np.ndarray,
                     peer_cov3: Optional[np.ndarray] = None,
                     t: Optional[float] = None) -> UnitPose:
        """Range update against a peer at known ENU peer_pos (3,) with 3x3 cov."""
        if m.kind != "range":
            raise ValueError(f"expected range, got {m.kind}")
        peer = np.asarray(peer_pos, float).reshape(3)
        d_meas = float(m.value["distance_m"])
        std = max(float(m.value["std_m"]), 1e-3)
        diff = self.x[:3] - peer
        d_pred = float(np.linalg.norm(diff))
        if d_pred < 1e-3:
            # Co-located: no bearing information; inflate slightly, keep honest.
            self.P[:3, :3] += np.eye(3) * 0.01
            return self.pose()
        u = diff / d_pred
        H = np.hstack([u.reshape(1, 3), np.zeros((1, 3))])
        r_eff = std * std
        if peer_cov3 is not None:
            Pp = np.asarray(peer_cov3, float).reshape(3, 3)
            r_eff += float(u @ Pp @ u)
        # Nonlinear h(x) = |x - peer|: innovate against d_pred, not H @ x.
        self._linear_update(np.array([d_meas]), H, np.array([[r_eff]]),
                            z_pred=np.array([d_pred]))
        self.measurement_ids.append(m.id)
        if t is not None:
            self._t = t
        self._refresh_mode()
        return self.pose()

    def update_vo(self, delta_enu: np.ndarray, cov3: np.ndarray,
                  measurement_id: str = "") -> UnitPose:
        """Visual-odometry hook (reserved): relative position delta in ENU."""
        d = np.asarray(delta_enu, float).reshape(3)
        H = np.hstack([np.eye(3), np.zeros((3, 3))])
        z = self.x[:3] + d
        self._linear_update(z, H, np.asarray(cov3, float).reshape(3, 3))
        if measurement_id:
            self.measurement_ids.append(measurement_id)
        return self.pose()

    # -- internals ------------------------------------------------------
    def _linear_update(self, z: np.ndarray, H: np.ndarray, R: np.ndarray,
                       z_pred: Optional[np.ndarray] = None) -> None:
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        innov = z - (H @ self.x if z_pred is None else z_pred)
        self.x = self.x + K @ innov
        self.P = (np.eye(6) - K @ H) @ self.P
        self.P = 0.5 * (self.P + self.P.T)  # keep symmetric

    def _refresh_mode(self) -> None:
        if self.anchor is not None and self._last_gnss_t is not None and (
            self._t - self._last_gnss_t
        ) <= GNSS_TIMEOUT_S:
            self.mode = "GNSS"
        else:
            self.mode = "REL"

    def pose(self) -> UnitPose:
        return UnitPose(
            unit_id=self.unit_id,
            position=self.x[:3].copy(),
            velocity=self.x[3:].copy(),
            covariance=self.P.copy(),
            mode=self.mode,
            anchor=self.anchor,
            t=self._t,
            measurement_ids=list(self.measurement_ids),
        )
