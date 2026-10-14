"""LSM9DS1 IMU driver (9DOF Click, MIKROE-1996) + Mahony orientation filter.

Raw accel/gyro/mag become Measurement(kind="imu_raw", frame "body").
The Mahony filter fuses them into Measurement(kind="imu_quat") with a
4x4 covariance that grows when updates are skipped or the field is weak —
the HUD shows uncertainty, never fake precision.

Register map notes (verify against the LSM9DS1 datasheet on hardware):
  accel/gyro @ 0x6B (SA0=1) or 0x6A (SA0=0); mag @ 0x1C/0x1E.
  Full-scale defaults used here: +/-2 g, +/-245 dps, +/-4 gauss.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

SENSOR = "imu"
FRAME = "body"
ALGORITHM_RAW = "lsm9ds1-raw"
ALGORITHM_MAHONY = "mahony-ahrs"

ACCEL_SCALE_G_PER_LSB = 2.0 / 32768.0
GYRO_SCALE_DPS_PER_LSB = 245.0 / 32768.0
MAG_SCALE_GAUSS_PER_LSB = 4.0 / 32768.0


def raw_counts_to_physical(
    accel_counts: Sequence[int], gyro_counts: Sequence[int], mag_counts: Sequence[int]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Signed 16-bit register words -> (accel g, gyro rad/s, mag gauss)."""
    a = np.asarray(list(accel_counts), dtype=float) * ACCEL_SCALE_G_PER_LSB
    g = np.asarray(list(gyro_counts), dtype=float) * GYRO_SCALE_DPS_PER_LSB * np.pi / 180.0
    m = np.asarray(list(mag_counts), dtype=float) * MAG_SCALE_GAUSS_PER_LSB
    if a.shape != (3,) or g.shape != (3,) or m.shape != (3,):
        raise ValueError("accel/gyro/mag must each have 3 axes")
    return a, g, m


def raw_measurement(
    accel_g: Sequence[float],
    gyro_rad_s: Sequence[float],
    mag_gauss: Sequence[float],
    *,
    sensor_id: str = "lsm9ds1-0",
    t_host: Optional[float] = None,
    frame_index: Optional[int] = None,
    sim: bool = False,
) -> Measurement:
    return Measurement(
        sensor=SENSOR,
        kind="imu_raw",
        t_host=t_host if t_host is not None else time.time(),
        frame_id=FRAME,
        value={
            "accel_g": [float(v) for v in accel_g],
            "gyro_rad_s": [float(v) for v in gyro_rad_s],
            "mag_gauss": [float(v) for v in mag_gauss],
            "sim": bool(sim),
        },
        confidence=0.99,
        covariance=np.diag([0.02**2] * 3 + [0.005**2] * 3 + [0.01**2] * 3).tolist(),
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm=ALGORITHM_RAW + ("-sim" if sim else ""),
            frame_index=frame_index,
        ),
    )


class MahonyFilter:
    """Mahony AHRS (IMU + mag). Quaternion state [w,x,y,z], body frame.

    kp: proportional gain; ki: integral (bias) gain. Covariance proxy grows
    with missed corrections so downstream fusion can de-weight it.
    """

    def __init__(self, kp: float = 1.0, ki: float = 0.05, dt: float = 0.01) -> None:
        self.kp, self.ki, self.dt = float(kp), float(ki), float(dt)
        self.q = np.array([1.0, 0.0, 0.0, 0.0])
        self.bias = np.zeros(3)
        self.missed = 0

    @staticmethod
    def _quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        aw, ax, ay, az = a
        bw, bx, by, bz = b
        return np.array([
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ])

    def update(
        self,
        gyro_rad_s: Sequence[float],
        accel_g: Sequence[float],
        mag_gauss: Optional[Sequence[float]] = None,
        dt: Optional[float] = None,
    ) -> np.ndarray:
        dt = self.dt if dt is None else float(dt)
        g = np.asarray(list(gyro_rad_s), dtype=float)
        a = np.asarray(list(accel_g), dtype=float)
        corr = np.zeros(3)
        used = False
        na = float(np.linalg.norm(a))
        if na > 1e-9:
            a_n = a / na
            # estimated gravity direction from current quat (body frame)
            w, x, y, z = self.q
            est = np.array([
                2 * (x * z - w * y),
                2 * (w * x + y * z),
                w * w - x * x - y * y + z * z,
            ])
            corr += np.cross(a_n, est)
            used = True
        if mag_gauss is not None:
            m = np.asarray(list(mag_gauss), dtype=float)
            nm = float(np.linalg.norm(m))
            if nm > 1e-9:
                corr += 0.5 * np.cross(m / nm, np.array([1.0, 0.0, 0.0]))
                used = True
        self.missed = 0 if used else self.missed + 1
        g_corr = g - self.bias + self.kp * corr
        self.bias = self.bias - self.ki * corr * dt
        omega = np.concatenate([[0.0], g_corr])
        dq = 0.5 * self._quat_mul(self.q, omega) * dt
        self.q = self.q + dq
        self.q = self.q / float(np.linalg.norm(self.q))
        return self.q.copy()

    @property
    def covariance(self) -> np.ndarray:
        base = 0.01 + 0.005 * min(self.missed, 50)
        return np.eye(4) * base


@dataclass
class Lsm9ds1Driver:
    """Host-side LSM9DS1: raw words in, Measurements out (no hardware at import)."""

    sensor_id: str = "lsm9ds1-0"
    mahony: MahonyFilter = field(default_factory=MahonyFilter)
    _i: int = 0

    def ingest(
        self,
        accel_counts: Sequence[int],
        gyro_counts: Sequence[int],
        mag_counts: Sequence[int],
        dt: Optional[float] = None,
    ) -> Tuple[Measurement, Measurement]:
        self._i += 1
        a, g, m = raw_counts_to_physical(accel_counts, gyro_counts, mag_counts)
        raw = raw_measurement(a, g, m, sensor_id=self.sensor_id, frame_index=self._i)
        q = self.mahony.update(g, a, m, dt=dt)
        quat = Measurement(
            sensor=SENSOR,
            kind="imu_quat",
            t_host=raw.t_host,
            frame_id=FRAME,
            value={"quat_wxyz": [float(v) for v in q], "sim": False},
            confidence=0.85 if self.mahony.missed == 0 else 0.4,
            covariance=self.mahony.covariance,
            provenance=Provenance(
                sensor_id=self.sensor_id, source=SENSOR,
                algorithm=ALGORITHM_MAHONY, frame_index=self._i, parents=(raw.id,),
            ),
        )
        return raw, quat


@dataclass
class SyntheticLsm9ds1:
    """CI synthetic LSM9DS1: level, facing slowly-varying yaw, tiny noise."""

    sensor_id: str = "lsm9ds1-sim"
    yaw_rate_rad_s: float = 0.1
    seed: int = 7
    _i: int = 0
    _yaw: float = 0.0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        self._filt = MahonyFilter()

    def read(self, dt: float = 0.01) -> Tuple[Measurement, Measurement]:
        self._i += 1
        self._yaw += self.yaw_rate_rad_s * dt
        a = np.array([0.0, 0.0, 1.0]) + self._rng.normal(0, 0.01, 3)
        g = np.array([0.0, 0.0, self.yaw_rate_rad_s]) + self._rng.normal(0, 0.002, 3)
        m = np.array([np.cos(self._yaw), np.sin(self._yaw), 0.0]) * 0.5
        m = m + self._rng.normal(0, 0.005, 3)
        raw = raw_measurement(a, g, m, sensor_id=self.sensor_id,
                              frame_index=self._i, sim=True)
        q = self._filt.update(g, a, m, dt=dt)
        quat = Measurement(
            sensor=SENSOR,
            kind="imu_quat",
            t_host=raw.t_host,
            frame_id=FRAME,
            value={"quat_wxyz": [float(v) for v in q], "sim": True},
            confidence=0.85,
            covariance=self._filt.covariance,
            provenance=Provenance(
                sensor_id=self.sensor_id, source=SENSOR,
                algorithm=ALGORITHM_MAHONY + "-sim", frame_index=self._i,
                parents=(raw.id,),
            ),
        )
        return raw, quat
