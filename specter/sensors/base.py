"""Sensor health model shared by every sensor driver and the HUD."""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Health(str, Enum):
    OK = "OK"
    SIMULATED = "SIM"          # data is synthetic; HUD must say so
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"        # expected but not responding
    NOT_INSTALLED = "N/A"      # planned for a later stage / not attached

    @property
    def bgr(self):
        return {
            Health.OK: (80, 220, 80),
            Health.SIMULATED: (255, 200, 60),
            Health.DEGRADED: (40, 190, 255),
            Health.OFFLINE: (60, 60, 240),
            Health.NOT_INSTALLED: (130, 130, 130),
        }[self]


@dataclass
class SensorStatus:
    key: str            # "nightvision", "thermal", ...
    label: str          # short HUD name
    health: Health
    detail: str = ""
    last_update: Optional[float] = None
    rate_hz: Optional[float] = None

    def touch(self, rate_hz: Optional[float] = None) -> None:
        self.last_update = time.time()
        if rate_hz is not None:
            self.rate_hz = rate_hz
