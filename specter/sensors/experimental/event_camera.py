"""EXPERIMENTAL: Prophesee GenX320 event camera (Starter Kit for Pi 5).

320x320, >140 dB dynamic range, sub-150 us latency over MIPI CSI-2 via the
OpenEB Python API. Uses: seeing through glare/flashing lights, fast-motion
tracking, low-power always-on motion trigger. Real driver lands with the kit
on the bench; this stub defines the Measurement contract + simulator.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from specter.fusion.measurement import Measurement, Provenance

EXPERIMENTAL = True
SENSOR = "event_camera"
FRAME = "genx320-0/image"
ALGORITHM = "genx320-motion-trigger"
W, H = 320, 320


def motion_measurement(boxes_xyxy: Sequence[Sequence[float]],
                       event_rate_kev_s: float,
                       *,
                       sensor_id: str = "genx320-0",
                       frame_index: Optional[int] = None,
                       sim: bool = False) -> Measurement:
    return Measurement(
        sensor=SENSOR,
        kind="event_motion",
        t_host=time.time(),
        frame_id=FRAME,
        value={
            "boxes_xyxy": [[float(v) for v in b] for b in boxes_xyxy],
            "event_rate_kev_s": float(event_rate_kev_s),
            "sim": bool(sim),
        },
        confidence=min(0.7, 0.3 + 0.05 * len(boxes_xyxy)),
        covariance=np.eye(4) * 9.0,
        provenance=Provenance(
            sensor_id=sensor_id, source=SENSOR,
            algorithm=ALGORITHM + ("-sim" if sim else ""),
            frame_index=frame_index,
            notes="EXPERIMENTAL: no hardware verified yet",
        ),
    )


@dataclass
class EventCameraDriver:
    sensor_id: str = "genx320-0"

    def try_open_hardware(self) -> bool:
        try:
            import metavision_sdk_base  # type: ignore  # OpenEB

            return True
        except Exception:
            return False


@dataclass
class SyntheticEventCamera:
    sensor_id: str = "genx320-sim"
    seed: int = 21
    _i: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def read(self) -> Measurement:
        self._i += 1
        x = float(self._rng.uniform(20, W - 80))
        boxes = [[x, 120.0, x + 50.0, 200.0]] if self._i % 3 else []
        return motion_measurement(boxes, event_rate_kev_s=150.0,
                                  sensor_id=self.sensor_id,
                                  frame_index=self._i, sim=True)
