"""Meridian Innovation SenXor 160x120 EVK driver (UNVERIFIED until hardware arrives).

Status: candidate hardware, USB via `pysenxor-lite` when installed. The raw
per-pixel °C path is implemented against the pysenxor-lite frame dict
convention; every Measurement from this driver is marked UNVERIFIED
(confidence capped at 0.3) until checked against a reference target next to
the TC001. SyntheticSenxor feeds CI with SIM-labelled frames.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from .interface import thermal_measurement

SENSOR_ID = "senxor-0"
ALGORITHM = "senxor-raw"
VERIFIED = False  # flip only after reference-target check on real hardware
W, H = 160, 120


def frame_dict_to_celsius(frame: object) -> np.ndarray:
    """pysenxor-lite frame -> (120,160) float32 °C. Accepts dict or ndarray."""
    if isinstance(frame, np.ndarray):
        a = frame.astype(np.float32)
        if a.shape != (H, W):
            raise ValueError(f"expected {(H, W)}, got {a.shape}")
        return a
    if isinstance(frame, dict):
        for key in ("temperature", "temp", "celsius", "frame"):
            if key in frame:
                return frame_dict_to_celsius(frame[key])
        raise ValueError(f"frame dict keys {sorted(frame)} carry no temperature field")
    raise TypeError(f"cannot convert {type(frame)} to celsius")


@dataclass
class SenxorDriver:
    sensor_id: str = SENSOR_ID
    verified: bool = VERIFIED  # UNVERIFIED until hardware check
    _i: int = 0
    _dev: object = None

    def try_open_hardware(self) -> bool:
        try:
            import pysenxor_lite  # type: ignore

            self._dev = pysenxor_lite  # handle kept; streaming starts on read
            return True
        except Exception:
            return False

    def ingest(self, celsius: np.ndarray):
        from specter.fusion.measurement import Measurement

        self._i += 1
        c = np.asarray(celsius, dtype=np.float32)
        if c.shape != (H, W):
            raise ValueError(f"SenXor frame must be {(H, W)}, got {c.shape}")
        m: Measurement = thermal_measurement(
            c, sensor_id=self.sensor_id, algorithm=ALGORITHM,
            frame_index=self._i, verified=self.verified,
        )
        return c, m

    def read_hardware(self) -> Optional[Tuple[np.ndarray, object]]:
        return None  # streaming lands with the EVK on the bench


@dataclass
class SyntheticSenxor:
    """CI stand-in: warm blob on a gradient, always SIM-labelled, UNVERIFIED math."""

    sensor_id: str = "senxor-sim"
    seed: int = 3
    _i: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def read(self) -> Tuple[np.ndarray, object]:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        base = 22.0 + 4.0 * (xx / W) + 2.0 * (yy / H)
        cx, cy = W * 0.55, H * 0.45
        blob = 14.0 * np.exp(-(((xx - cx) / 18.0) ** 2 + ((yy - cy) / 14.0) ** 2))
        noise = self._rng.normal(0, 0.3, (H, W)).astype(np.float32)
        c = (base + blob + noise).astype(np.float32)
        self._i += 1
        m = thermal_measurement(
            c, sensor_id=self.sensor_id, algorithm=ALGORITHM + "-sim",
            frame_index=self._i, sim=True, verified=False,
        )
        return c, m
