"""EXPERIMENTAL: IWR6843 vital-signs mode (breathing / heart rate).

Same radar silicon as Stage 3, different DSP chain: micro-Doppler phase
tracks chest displacement of still, trapped people. Real chain lands with
bench data; this stub defines the Measurement contract + simulator.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

EXPERIMENTAL = True
SENSOR = "vitals_radar"
FRAME = "radar"
ALGORITHM = "iwr6843-vitals"


def vitals_measurement(range_m: float, breath_bpm: float, heart_bpm: float,
                       *,
                       sensor_id: str = "iwr6843-vit",
                       frame_index: Optional[int] = None,
                       sim: bool = False) -> Measurement:
    if not (4.0 <= breath_bpm <= 40.0):
        raise ValueError(f"implausible breath rate {breath_bpm}")
    return Measurement(
        sensor=SENSOR,
        kind="vitals",
        t_host=time.time(),
        frame_id=FRAME,
        value={
            "range_m": float(range_m),
            "breath_bpm": float(breath_bpm),
            "heart_bpm": float(heart_bpm),
            "sim": bool(sim),
        },
        confidence=0.4,
        covariance=np.diag([0.3**2, 2.0**2, 5.0**2]),
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm=ALGORITHM + ("-sim" if sim else ""),
            frame_index=frame_index,
            notes="EXPERIMENTAL: needs still subject + bench validation",
        ),
    )


@dataclass
class VitalsDriver:
    sensor_id: str = "iwr6843-vit"

    def try_open_hardware(self) -> bool:
        return False  # DSP chain not implemented yet


@dataclass
class SyntheticVitals:
    sensor_id: str = "iwr6843-vit-sim"
    seed: int = 23
    _i: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def read(self) -> Measurement:
        self._i += 1
        return vitals_measurement(
            range_m=4.5,
            breath_bpm=float(self._rng.normal(14, 1.5)),
            heart_bpm=float(self._rng.normal(72, 4)),
            sensor_id=self.sensor_id, frame_index=self._i, sim=True)
