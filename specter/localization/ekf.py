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
                 accel_noise: float = 0.5) -> None:
        self.unit_id = unit_id
        self.x = np.zeros(6)
        self.P = np.diag([init_pos_std**2] * 3 + [init_vel_std**2] * 3)
        self.accel_noise = float(accel_noise)
        self.anchor: Optional[Tuple[float, float, float]] = None
        self.mode = "REL"
        self._last_gnss_t: Optional[float] = None
        self._t = 0.0
        self.measurement_ids: List[str] = []
        self._started = False

    # -- core ----------------------------------------------------------
    def _ensure_started(self, t: float) -> None:
        if not self._started:
            self._t = t
            self._started = True

    def predict(self, dt: float, accel_enu: Optional[np.ndarray] = None,
                t: Optional[float] = None) -> UnitPose:
        dt = max(float(dt), 1e-6)
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
        if t is not None:
            self._ensure_started(t)
            self._t = t
        else:
            self._ensure_started(self._t)
        self._refresh_mode()
        return self.pose()

    def update_gnss(self, m: Measurement) -> UnitPose:
        if m.kind != "gnss_fix":
            raise ValueError(f"expected gnss_fix, got {m.kind}")
        v = m.value
        if self.anchor is None:
            self.anchor = (float(v["lat_deg"]), float(v["lon_deg"]), float(v["alt_m"]))
            # First fix defines the origin: snap state there, keep velocity.
            self.x[:3] = 0.0
        z = latlon_to_enu(float(v["lat_deg"]), float(v["lon_deg"]),
                          float(v["alt_m"]), self.anchor)
        H = np.hstack([np.eye(3), np.zeros((3, 3))])
        R = np.asarray(m.covariance, float).reshape(3, 3)
        if R.shape != (3, 3):
            raise ValueError(f"gnss covariance must be 3x3, got {R.shape}")
        self._linear_update(z, H, R)
        self._last_gnss_t = m.t_host
        self._ensure_started(m.t_host)
        self._t = m.t_host
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
        self._linear_update(np.array([d_meas]), H, np.array([[r_eff]]))
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
    def _linear_update(self, z: np.ndarray, H: np.ndarray, R: np.ndarray) -> None:
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ (z - H @ self.x)
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
