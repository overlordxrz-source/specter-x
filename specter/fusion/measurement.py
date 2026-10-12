"""Measurement: the single unit of information that flows through SPECTER-X.

Core principle: every detection carries provenance (which sensor, when, how
confident, in which coordinate frame, produced by which algorithm). The HUD
renders Measurements only, so nothing unsourced can reach the screen.
"""
from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np

# Canonical sensor identifiers. The HUD label ("SRC: OPTICAL") comes from here.
SENSOR_LABELS = {
    "nightvision": "OPTICAL",
    "thermal": "THERMAL",
    "radar": "RADAR",
    "wifi_csi": "WIFI-CSI",
    "imu": "IMU",
    "synthetic": "SYNTHETIC",
    "fusion": "FUSED",
}


@dataclass(frozen=True)
class Provenance:
    """Where a measurement came from and how it was produced."""

    sensor_id: str                      # e.g. "imx462-0", "tc001-0", "iwr6843-0"
    source: str                         # one of SENSOR_LABELS keys
    algorithm: str                      # e.g. "yolo11n-pose", "raw", "cfar"
    model_version: Optional[str] = None
    frame_index: Optional[int] = None   # sensor-native frame counter
    parents: tuple = ()                 # ids of measurements this was derived from
    notes: Optional[str] = None

    @property
    def label(self) -> str:
        return SENSOR_LABELS.get(self.source, self.source.upper())


def _to_jsonable(obj: Any) -> Any:
    """Convert numpy types / tuples into plain JSON types (recursively)."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


@dataclass
class Measurement:
    sensor: str                          # SENSOR_LABELS key
    kind: str                            # "pose2d", "point_cloud", "imu_quat", ...
    t_host: float                        # host monotonic-ish wall clock (time.time())
    frame_id: str                        # coordinate frame, e.g. "cam_nv", "radar", "body"
    value: Any                           # payload (dict / list / scalar); JSON-serialisable after conversion
    provenance: Provenance
    t_sensor: Optional[float] = None     # sensor-native timestamp (s), if available
    confidence: Optional[float] = None   # scalar in [0,1]
    covariance: Optional[list] = None    # NxN, in frame_id units
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self) -> None:
        if not self.sensor:
            raise ValueError("Measurement.sensor is required (provenance principle)")
        if not self.frame_id:
            raise ValueError("Measurement.frame_id is required")
        if self.confidence is not None:
            c = float(self.confidence)
            if not (0.0 <= c <= 1.0):
                raise ValueError(f"confidence must be in [0,1], got {c}")
            self.confidence = c
        if self.covariance is not None:
            cov = np.asarray(self.covariance, dtype=float)
            if cov.ndim != 2 or cov.shape[0] != cov.shape[1]:
                raise ValueError(f"covariance must be square, got shape {cov.shape}")
            if not np.allclose(cov, cov.T, atol=1e-9):
                raise ValueError("covariance must be symmetric")
            self.covariance = cov.tolist()
        if self.provenance.source != self.sensor:
            raise ValueError(
                f"provenance.source ({self.provenance.source}) != sensor ({self.sensor})"
            )

    @property
    def label(self) -> str:
        return self.provenance.label

    @property
    def hud_tag(self) -> str:
        """Short string the HUD must print next to anything derived from this."""
        conf = "n/a" if self.confidence is None else f"{self.confidence:.2f}"
        return f"SRC: {self.label} conf {conf}"

    # ---- serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"]["parents"] = list(self.provenance.parents)
        return _to_jsonable(d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> "Measurement":
        d = dict(d)
        p = dict(d.pop("provenance"))
        p["parents"] = tuple(p.get("parents") or ())
        return cls(provenance=Provenance(**p), **d)

    @classmethod
    def from_json(cls, s: str) -> "Measurement":
        return cls.from_dict(json.loads(s))


def now() -> float:
    return time.time()
