"""Unified IMU layer: accepts BNO085 *or* LSM9DS1, one Measurement stream.

Both chips yield kind="imu_quat" in frame "body" plus kind="imu_raw" where
available, so fusion and HUD code never branches on hardware. `select` picks
the driver explicitly; "auto" prefers whichever answers on I2C (LSM9DS1
first on the Click Shield build, BNO085 otherwise).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .bno085 import Bno085Driver, SyntheticBno085
from .lsm9ds1 import Lsm9ds1Driver, MahonyFilter, SyntheticLsm9ds1

DRIVERS = ("auto", "lsm9ds1", "bno085")


@dataclass
class ImuLayer:
    which: str = "auto"
    lsm9ds1: Lsm9ds1Driver | None = None
    bno085: Bno085Driver | None = None

    def __post_init__(self) -> None:
        if self.which not in DRIVERS:
            raise ValueError(f"which must be one of {DRIVERS}, got {self.which!r}")
        if self.lsm9ds1 is None:
            self.lsm9ds1 = Lsm9ds1Driver()
        if self.bno085 is None:
            self.bno085 = Bno085Driver()
        if self.which == "auto":
            self.which = self._autodetect()

    def _autodetect(self) -> str:
        try:  # LSM9DS1 first: it is the Click Shield IMU on i2c-1.
            import smbus2  # type: ignore

            bus = smbus2.SMBus(1)
            try:
                for addr in (0x6B, 0x6A):
                    try:
                        bus.read_byte_data(addr, 0x0F)
                        return "lsm9ds1"
                    except OSError:
                        continue
            finally:
                bus.close()
        except Exception:
            pass
        if self.bno085 is not None and self.bno085.try_open_hardware():
            return "bno085"
        return "lsm9ds1"  # default: parsing/filter path works without hardware

    @property
    def active(self) -> str:
        return self.which

    def synthetic(self, which: Optional[str] = None):
        w = which or (self.which if self.which in ("lsm9ds1", "bno085") else "lsm9ds1")
        return SyntheticLsm9ds1() if w == "lsm9ds1" else SyntheticBno085()


__all__ = [
    "DRIVERS", "ImuLayer",
    "Bno085Driver", "Lsm9ds1Driver", "MahonyFilter",
    "SyntheticBno085", "SyntheticLsm9ds1",
]
