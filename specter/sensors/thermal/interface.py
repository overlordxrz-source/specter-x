"""Shared thermal interface: TC001 and SenXor sit behind the same driver API.

Every thermal driver yields Measurement(kind="thermal_frame") with per-frame
min/mean/max °C plus covariance, and exposes read_celsius() for raw per-pixel
temperature. The HUD renders only the Measurement, never the raw array.
"""

from __future__ import annotations

import time
from typing import Optional, Protocol, Tuple

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

SENSOR = "thermal"
FRAME = "thermal"


def thermal_measurement(
    celsius: np.ndarray,
    *,
    sensor_id: str,
    algorithm: str,
    t_host: Optional[float] = None,
    frame_index: Optional[int] = None,
    sim: bool = False,
    verified: bool = False,
) -> Measurement:
    c = np.asarray(celsius, dtype=float)
    if c.ndim != 2 or not c.size or not np.isfinite(c).all():
        raise ValueError("thermal frame must be a nonempty finite 2D array")
    if sim and verified:
        raise ValueError("simulation cannot verify a physical thermal conversion")
    return Measurement(
        sensor=SENSOR,
        kind="thermal_frame",
        t_host=t_host if t_host is not None else time.time(),
        frame_id=FRAME,
        value={
            "width": int(c.shape[1]) if c.ndim == 2 else 0,
            "height": int(c.shape[0]) if c.ndim == 2 else 0,
            "min_c": float(np.min(c)) if c.size else 0.0,
            "mean_c": float(np.mean(c)) if c.size else 0.0,
            "max_c": float(np.max(c)) if c.size else 0.0,
            "sim": bool(sim),
            "verified": bool(verified),
            "spatial_variance_c2": float(np.var(c)),
        },
        # Pixel variation is scene structure, not calibrated error uncertainty.
        confidence=None,
        covariance=None,
        provenance=Provenance(
            sensor_id=sensor_id,
            source=SENSOR,
            algorithm=algorithm,
            frame_index=frame_index,
            notes=None
            if verified
            else "UNVERIFIED: conversion not checked on hardware",
        ),
    )


class ThermalDriver(Protocol):
    sensor_id: str

    def read_celsius(self) -> Tuple[np.ndarray, Measurement]:
        """Return (H,W float32 °C array, provenance Measurement)."""
        ...
