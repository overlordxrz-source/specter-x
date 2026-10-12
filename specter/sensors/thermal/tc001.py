"""TOPDON TC001 helpers (Stage 2 driver will build on these).

The TC001 enumerates as a UVC camera delivering 256x384 YUYV frames: the upper
256x192 half is the false-colour preview image, the lower 256x192 half carries
the raw thermal data as 16-bit little-endian words split across the two bytes
of each YUYV pixel. The community-reverse-engineered conversion is
    raw16 = lo + (hi << 8);  temp_C = raw16 / 64 - 273.15
Treat that formula as unverified until checked against a reference target.
OpenCV must be told not to convert: cap.set(cv2.CAP_PROP_CONVERT_RGB, 0).
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

TC001_W, TC001_H = 256, 192


def split_frame(raw: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """raw: (384, 256, 2) uint8 YUYV buffer -> (image_bytes (192,256,2), thermal_bytes (192,256,2))."""
    raw = np.asarray(raw)
    if raw.shape[:2] != (2 * TC001_H, TC001_W):
        raise ValueError(f"expected {(2 * TC001_H, TC001_W)}xC frame, got {raw.shape}")
    return raw[:TC001_H], raw[TC001_H:]


def thermal_to_celsius(thermal_bytes: np.ndarray) -> np.ndarray:
    """(192,256,2) uint8 -> (192,256) float32 degrees C."""
    t = np.asarray(thermal_bytes).astype(np.uint16)
    raw16 = t[..., 0] | (t[..., 1] << 8)
    return (raw16.astype(np.float32) / 64.0) - 273.15
