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
    "gnss": "GNSS",
    "uwb": "UWB",
    "event_camera": "EVENT",
    "acoustic": "ACOUSTIC",
    "vitals_radar": "VITALS",
    "gas": "GAS",
    "lora": "LORA",
    "vlm": "AI-SUMMARY",
    "synthetic": "SYNTHETIC",
    "fusion": "FUSED",
    "analog": "ANALOG",       # DI-188 USB DAQ analog channels
    # The ESP32-S3 supervisor's DEVICE heartbeat (over USB). Distinct from the
    # unit-level NETWORK heartbeat in specter/net/messages.py.
    "supervisor": "SUPERVISOR",
}


#: Versioned observation contract. Bumped only by an explicit schema change.
OBSERVATION_SCHEMA_V1 = "specter.observation.v1"

#: Evidence ladder. A claim may never be reported above the level it was
#: actually obtained at.
EVIDENCE_LEVELS = (
    "simulated",              # synthetic fixture or explicit test source
    "software_verified",      # produced/checked by code, no hardware involved
    "hardware_measured",      # a real sensor produced the bytes
    "experimentally_validated"  # a physical experiment established the claim
)

#: Allowed validity flags. "valid" means contract-complete, not scientifically
#: established; these flags carry the caveats downstream.
VALIDITY_FLAGS = frozenset({
    "uncalibrated",       # no calibration_version applies yet
    "signal_domain",      # value is a signal feature, not a spatial coordinate
    "not_spatial",        # explicit: must never be read as position/pose
    "raw_unavailable",    # raw bytes were not retained for this observation
    "clock_unsynced",     # sensor clock offset not yet estimated
    "stale",              # delivered after its useful window
    "frame_mismatch",     # frame_id disagrees with the registered sensor
    "calibration_mismatch",
    "null_control",       # synthetic negative control
    "positive_control",   # synthetic positive control
})


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
    # ---- FRONTIER-001 observation contract (additive, defaults keep old
    # call sites valid) ---------------------------------------------------
    schema_version: str = OBSERVATION_SCHEMA_V1
    measurement_type: Optional[str] = None   # e.g. "csi_lltf_amplitude"
    units: Optional[str] = None              # e.g. "adc_counts", "pixel"
    calibration_version: Optional[str] = None
    evidence_level: str = "software_verified"
    valid: bool = True
    validity_flags: tuple = ()
    raw_ref: Optional[dict] = None           # RawEvidence.to_dict()
    uncertainty: Optional[dict] = None       # Uncertainty.to_dict()
    seq: Optional[int] = None                # per-sensor monotonic sequence
    dropped_before: int = 0                  # frames known lost before this one

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
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise ValueError("schema_version must be a non-empty string")
        if self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(
                f"evidence_level must be one of {EVIDENCE_LEVELS}, "
                f"got {self.evidence_level!r}"
            )
        flags = tuple(self.validity_flags or ())
        unknown = set(flags) - VALIDITY_FLAGS
        if unknown:
            raise ValueError(f"unknown validity_flags: {sorted(unknown)}")
        self.validity_flags = flags
        if self.seq is not None and (not isinstance(self.seq, int) or self.seq < 0):
            raise ValueError(f"seq must be a non-negative int, got {self.seq!r}")
        if not isinstance(self.dropped_before, int) or self.dropped_before < 0:
            raise ValueError(
                f"dropped_before must be a non-negative int, got {self.dropped_before!r}"
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
