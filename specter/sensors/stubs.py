"""Lightweight presence probes for sensors that arrive in later stages.

They never fabricate data: they only report whether hardware appears present.
"""
from __future__ import annotations

import glob
import os

from .base import Health, SensorStatus


def probe_thermal() -> SensorStatus:
    # TC001 enumerates as a UVC device; Stage 2 will identify it by USB VID:PID (verify with lsusb).
    return SensorStatus("thermal", "THERMAL TC001", Health.NOT_INSTALLED, "stage 2")


def probe_radar() -> SensorStatus:
    ports = sorted(glob.glob("/dev/serial/by-id/*XDS110*") + glob.glob("/dev/serial/by-id/*CP210*"))
    if ports:
        return SensorStatus("radar", "RADAR IWR6843", Health.DEGRADED, "port seen; stage 3 driver")
    return SensorStatus("radar", "RADAR IWR6843", Health.NOT_INSTALLED, "stage 3")


def probe_wifi_csi() -> SensorStatus:
    return SensorStatus("wifi_csi", "WIFI CSI ESP32", Health.NOT_INSTALLED, "stage 3")


def probe_imu() -> SensorStatus:
    if os.path.exists("/dev/i2c-1"):
        return SensorStatus("imu", "IMU BNO085", Health.NOT_INSTALLED, "i2c bus ok; stage 2")
    return SensorStatus("imu", "IMU BNO085", Health.NOT_INSTALLED, "stage 2")


def probe_hailo() -> SensorStatus:
    if glob.glob("/dev/hailo*"):
        return SensorStatus("hailo", "HAILO-8L", Health.OK, "device present (unused, stage 5)")
    return SensorStatus("hailo", "HAILO-8L", Health.NOT_INSTALLED, "optional")
