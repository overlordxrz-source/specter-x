"""BNO085 IMU driver (kept supported alongside LSM9DS1).

Hardware path uses adafruit-circuitpython-bno08x when installed; imports are
lazy so CI never touches hardware. Rotation-vector reports become
Measurement(kind="imu_quat") in frame "body" with a covariance derived from
the BNO085 accuracy field (the chip runs its own internal fusion).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

SENSOR = "imu"
FRAME = "body"
ACCURACY_TO_COV = {0: 0.10, 1: 0.05, 2: 0.02, 3: 0.005}


def quat_measurement(
    quat_wxyz: Sequence,
    *,
    sensor_id: str = "bno085-0",
    accuracy: int = 2,
    t_host: Optional[float] = None,
    frame_index: Optional[int] = None,
    sim: bool = False,
) -> Measurement:
    try:
        q = np.asarray(list(quat_wxyz), dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("quaternion must be a finite 4-vector") from exc
    if q.shape != (4,) or not np.isfinite(q).all():
        raise ValueError("quaternion must be a finite 4-vector")
    scale = float(np.max(np.abs(q)))
    if scale == 0:
        raise ValueError("zero quaternion")
    # Scaling first avoids both overflow and underflow for finite inputs.
    q = q / scale
    q = (q / np.linalg.norm(q)).tolist()
    var = ACCURACY_TO_COV.get(int(accuracy), 0.10)
    return Measurement(
        sensor=SENSOR,
        kind="imu_quat",
        t_host=t_host if t_host is not None else time.time(),
        frame_id=FRAME,
        value={"quat_wxyz": q, "accuracy": int(accuracy), "sim": bool(sim)},
        confidence=0.9 if int(accuracy) >= 2 else 0.5,
        covariance=np.eye(4) * var,
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm="bno085-rotation-vector" + ("-sim" if sim else ""),
            frame_index=frame_index,
        ),
    )


@dataclass
class Bno085Driver:
    """Thin host-side BNO085 wrapper. Real I2C path is optional."""

    sensor_id: str = "bno085-0"
    _i: int = 0

    def report(self, quat_wxyz: Sequence, accuracy: int = 2) -> Measurement:
        measurement = quat_measurement(
            quat_wxyz, sensor_id=self.sensor_id,
            accuracy=accuracy, frame_index=self._i + 1,
        )
        self._i += 1
        return measurement

    def try_open_hardware(self) -> bool:
        """True if an I2C BNO085 answers; False otherwise (never raises)."""
        try:
            import board  # type: ignore
            import busio  # type: ignore
            from adafruit_bno08x.i2c import BNO08X_I2C  # type: ignore

            i2c = busio.I2C(board.SCL, board.SDA)
            BNO08X_I2C(i2c)
            return True
        except Exception:
            return False

    def read_hardware(self) -> Optional[Measurement]:
        return None  # full polling loop lands with stage-2 field testing


@dataclass
class SyntheticBno085:
    sensor_id: str = "bno085-sim"
    _i: int = 0

    def read(self, yaw_rad: float = 0.0) -> Measurement:
        self._i += 1
        q = [float(np.cos(yaw_rad / 2)), 0.0, 0.0, float(np.sin(yaw_rad / 2))]
        return quat_measurement(q, sensor_id=self.sensor_id, accuracy=3,
                                frame_index=self._i, sim=True)
