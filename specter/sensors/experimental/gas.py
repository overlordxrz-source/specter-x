"""EXPERIMENTAL: gas sensor (CO/CO2) for fire: environmental danger overlay.

Thresholds follow common occupational guidance (CO 35 ppm 8-h TWA danger
ramp; CO2 1000 ppm stuffy / 5000 ppm dangerous) — advisory only, this
prototype is not certified safety gear and the HUD says so.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

EXPERIMENTAL = True
SENSOR = "gas"
FRAME = "body"
ALGORITHM = "gas-advisory-v1"

CO_WARN_PPM, CO_DANGER_PPM = 35.0, 200.0
CO2_WARN_PPM, CO2_DANGER_PPM = 1000.0, 5000.0


def danger_level(co_ppm: float, co2_ppm: float) -> str:
    if co_ppm >= CO_DANGER_PPM or co2_ppm >= CO2_DANGER_PPM:
        return "DANGER"
    if co_ppm >= CO_WARN_PPM or co2_ppm >= CO2_WARN_PPM:
        return "WARN"
    return "OK"


def gas_measurement(co_ppm: float, co2_ppm: float,
                    *,
                    sensor_id: str = "gas-0",
                    frame_index: Optional[int] = None,
                    sim: bool = False) -> Measurement:
    if co_ppm < 0 or co2_ppm < 0:
        raise ValueError("concentrations must be non-negative")
    return Measurement(
        sensor=SENSOR,
        kind="gas",
        t_host=time.time(),
        frame_id=FRAME,
        value={
            "co_ppm": float(co_ppm), "co2_ppm": float(co2_ppm),
            "danger": danger_level(co_ppm, co2_ppm), "sim": bool(sim),
        },
        confidence=0.6,
        covariance=np.diag([2.0**2, 50.0**2]),
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm=ALGORITHM + ("-sim" if sim else ""),
            frame_index=frame_index,
            notes="EXPERIMENTAL advisory only — not certified safety gear",
        ),
    )


@dataclass
class GasDriver:
    sensor_id: str = "gas-0"

    def try_open_hardware(self) -> bool:
        return False  # sensor not on the bench yet


@dataclass
class SyntheticGas:
    sensor_id: str = "gas-sim"
    seed: int = 24
    _i: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def read(self, co_ppm: Optional[float] = None) -> Measurement:
        self._i += 1
        co = 5.0 + abs(float(self._rng.normal(0, 2))) if co_ppm is None else co_ppm
        return gas_measurement(co, 450.0, sensor_id=self.sensor_id,
                               frame_index=self._i, sim=True)
