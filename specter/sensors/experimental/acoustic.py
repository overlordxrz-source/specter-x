"""EXPERIMENTAL: miniDSP UMA-16 v2 acoustic camera (16-mic USB array, Acoular).

Uses: direction of voices/calls for help, alarms, gunshots; overlays a
sound heatmap. Real beamforming (Acoular) lands with the array on the bench;
this stub defines the Measurement contract + simulator.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

EXPERIMENTAL = True
SENSOR = "acoustic"
FRAME = "body"
ALGORITHM = "uma16-doa"
N_MICS = 16


def doa_measurement(azimuth_deg: float, elevation_deg: float, level_db: float,
                    kind_label: str = "voice",
                    *,
                    sensor_id: str = "uma16-0",
                    frame_index: Optional[int] = None,
                    sim: bool = False) -> Measurement:
    return Measurement(
        sensor=SENSOR,
        kind="sound_doa",
        t_host=time.time(),
        frame_id=FRAME,
        value={
            "azimuth_deg": float(azimuth_deg),
            "elevation_deg": float(elevation_deg),
            "level_db": float(level_db),
            "label": kind_label,
            "sim": bool(sim),
        },
        confidence=0.5,
        covariance=np.diag([8.0**2, 8.0**2, 6.0**2]),
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm=ALGORITHM + ("-sim" if sim else ""),
            frame_index=frame_index,
            notes="EXPERIMENTAL: no hardware verified yet",
        ),
    )


@dataclass
class AcousticArrayDriver:
    sensor_id: str = "uma16-0"

    def try_open_hardware(self) -> bool:
        try:
            import sounddevice  # type: ignore

            return True
        except Exception:
            return False


@dataclass
class SyntheticAcousticArray:
    sensor_id: str = "uma16-sim"
    seed: int = 22
    _i: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def read(self) -> Measurement:
        self._i += 1
        return doa_measurement(
            azimuth_deg=float(self._rng.uniform(-60, 60)),
            elevation_deg=float(self._rng.uniform(-10, 20)),
            level_db=72.0, kind_label="voice",
            sensor_id=self.sensor_id, frame_index=self._i, sim=True)
