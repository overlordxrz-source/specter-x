"""Team message types: Heartbeat, PoseStamped, TrackReport, Alert.

Compact by design: tracks travel, video never does. Each TrackReport keeps
the source unit, sensor and Measurement ids so provenance survives the
network hop and the HUD can still print SRC: <UNIT>/<SENSOR>.
"""

from __future__ import annotations

import json
import math
import time
import numpy as np
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

HEARTBEAT, POSE, TRACK, ALERT = "heartbeat", "pose", "track", "alert"
SCHEMA_V1 = 1


@dataclass
class Message:
    type: str
    unit_id: str
    seq: int
    t_host: float  # sender host/report time; not an acquisition timestamp
    schema: int = SCHEMA_V1
    boot: str = ""  # sender boot id: ordered per boot, see security.generate_boot_id

    def body(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("schema", None)
        return d

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, s: str) -> "Message":
        return decode_message(s)


@dataclass
class Heartbeat(Message):
    mode: str = "REL"          # pose mode: REL | GNSS
    pos_rmse: float = 99.0
    health: str = "OK"

    def __init__(self, unit_id: str, seq: int, t_host: float,
                 mode: str = "REL", pos_rmse: float = 99.0, health: str = "OK",
                 boot: str = "") -> None:
        super().__init__(HEARTBEAT, unit_id, seq, t_host, boot=boot)
        self.mode, self.pos_rmse, self.health = mode, pos_rmse, health


@dataclass
class PoseStamped(Message):
    position_enu: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity_enu: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    cov_pos_3x3: List[List[float]] = field(
        default_factory=lambda: [[25.0, 0, 0], [0, 25.0, 0], [0, 0, 25.0]])
    mode: str = "REL"
    anchor: Optional[List[float]] = None  # shared ENU anchor [lat, lon, alt]
    quat_wxyz: Optional[List[float]] = None  # body orientation, if IMU fused

    def __init__(self, unit_id: str, seq: int, t_host: float,
                 position_enu, velocity_enu, cov_pos_3x3,
                 mode: str = "REL", anchor=None, quat_wxyz=None,
                 boot: str = "") -> None:
        super().__init__(POSE, unit_id, seq, t_host, boot=boot)
        self.position_enu = [float(v) for v in position_enu]
        self.velocity_enu = [float(v) for v in velocity_enu]
        self.cov_pos_3x3 = [[float(c) for c in row] for row in cov_pos_3x3]
        self.mode, self.anchor = mode, anchor
        self.quat_wxyz = [float(v) for v in quat_wxyz] if quat_wxyz else None


@dataclass
class TrackReport(Message):
    track_id: int = 0
    position_enu: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    cov_3x3: List[List[float]] = field(
        default_factory=lambda: [[4.0, 0, 0], [0, 4.0, 0], [0, 0, 4.0]])
    source_unit: str = ""
    source_sensor: str = "fusion"     # SENSOR_LABELS key on the origin unit
    measurement_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5
    label: str = "contact"
    frame_id: str = "enu"  # shared frame declaration; no anchor transform exists

    def __init__(self, unit_id: str, seq: int, t_host: float, track_id: int,
                 position_enu, cov_3x3, source_unit: str = "",
                 source_sensor: str = "fusion", measurement_ids=(),
                 confidence: float = 0.5, label: str = "contact",
                 boot: str = "", frame_id: str = "enu") -> None:
        super().__init__(TRACK, unit_id, seq, t_host, boot=boot)
        self.track_id = int(track_id)
        self.position_enu = [float(v) for v in position_enu]
        self.cov_3x3 = [[float(c) for c in row] for row in cov_3x3]
        self.source_unit = source_unit or unit_id
        self.source_sensor = source_sensor
        self.measurement_ids = list(measurement_ids)
        self.confidence = float(confidence)
        self.label = label
        if not isinstance(frame_id, str) or not frame_id:
            raise ValueError("track frame_id must be a nonempty string")
        self.frame_id = frame_id

    @property
    def hud_tag(self) -> str:
        return f"SRC: {self.source_unit}/{self.source_sensor.upper()} conf {self.confidence:.2f}"


@dataclass
class Alert(Message):
    kind: str = "man-down"            # man-down | flashover | gas | custom
    detail: Dict[str, Any] = field(default_factory=dict)
    severity: str = "high"

    def __init__(self, unit_id: str, seq: int, t_host: float,
                 kind: str = "man-down", detail=None, severity: str = "high",
                 boot: str = "") -> None:
        super().__init__(ALERT, unit_id, seq, t_host, boot=boot)
        self.kind, self.detail, self.severity = kind, dict(detail or {}), severity


def decode_message(s: str) -> Message:
    """JSON -> typed message. Raises ValueError on bad schema/type."""
    try:
        d = json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}")
    if not isinstance(d, dict) or type(d.get("schema")) is not int or d.get("schema") != SCHEMA_V1:
        raise ValueError(
            f"unsupported schema: {d.get('schema') if isinstance(d, dict) else type(d)}"
        )

    def validate_json(value):
        if isinstance(value, dict):
            for item in value.values():
                validate_json(item)
        elif isinstance(value, list):
            for item in value:
                validate_json(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite network payload")

    validate_json(d)
    def scalar(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("finite numeric field required")
        return value

    def vector(value, size):
        if not isinstance(value, list) or len(value) != size:
            raise ValueError("invalid vector dimension")
        for item in value:
            scalar(item)

    def covariance(value):
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError("3x3 covariance required")
        for row in value:
            vector(row, 3)
        c = np.asarray(value, float)
        if not np.allclose(c, c.T, atol=1e-9) or (np.diag(c) < 0).any() or np.linalg.eigvalsh(c).min() < -1e-10:
            raise ValueError("invalid covariance")

    if (
        not isinstance(d.get("unit_id"), str)
        or not d["unit_id"]
        or type(d.get("seq")) is not int
        or d["seq"] < 0
        or type(d.get("t_host")) not in (int, float)
    ):
        raise ValueError("explicit valid unit/sequence/timestamp required")
    if not isinstance(d.get("boot", ""), str):
        raise ValueError("boot must be a string")
    t = d.get("type")
    if t in (POSE, TRACK):
        vector(d.get("position_enu"), 3)
        covariance(d.get("cov_pos_3x3" if t == POSE else "cov_3x3"))
    if t == POSE:
        vector(d.get("velocity_enu"), 3)
        if d.get("quat_wxyz") is not None:
            vector(d["quat_wxyz"], 4)
        if d.get("anchor") is not None:
            vector(d["anchor"], 3)
    if t == TRACK:
        if not 0 <= scalar(d.get("confidence", 0.5)) <= 1:
            raise ValueError("invalid track confidence")
        if not isinstance(d.get("measurement_ids", []), list) or not all(isinstance(v, str) for v in d.get("measurement_ids", [])):
            raise ValueError("invalid parent IDs")
        if not isinstance(d.get("frame_id", "enu"), str) or not d.get("frame_id", "enu"):
            raise ValueError("track frame_id must be a nonempty string")
    if t == HEARTBEAT and scalar(d.get("pos_rmse", 99.0)) < 0:
        raise ValueError("negative position uncertainty")
    u, seq, th = (
        d.get("unit_id", "?"),
        int(d.get("seq", 0)),
        float(d.get("t_host", time.time())),
    )
    boot = str(d.get("boot", ""))
    if t == HEARTBEAT:
        return Heartbeat(
            u,
            seq,
            th,
            d.get("mode", "REL"),
            float(d.get("pos_rmse", 99.0)),
            d.get("health", "OK"),
            boot=boot,
        )
    if t == POSE:
        return PoseStamped(
            u,
            seq,
            th,
            d.get("position_enu", [0, 0, 0]),
            d.get("velocity_enu", [0, 0, 0]),
            d.get("cov_pos_3x3", [[25, 0, 0], [0, 25, 0], [0, 0, 25]]),
            d.get("mode", "REL"),
            d.get("anchor"),
            d.get("quat_wxyz"),
            boot=boot,
        )
    if t == TRACK:
        return TrackReport(
            u,
            seq,
            th,
            int(d.get("track_id", 0)),
            d.get("position_enu", [0, 0, 0]),
            d.get("cov_3x3", [[4, 0, 0], [0, 4, 0], [0, 0, 4]]),
            d.get("source_unit", u),
            d.get("source_sensor", "fusion"),
            d.get("measurement_ids", []),
            float(d.get("confidence", 0.5)),
            d.get("label", "contact"),
            boot=boot,
            frame_id=d.get("frame_id", "enu"),
        )
    if t == ALERT:
        return Alert(
            u,
            seq,
            th,
            d.get("kind", "man-down"),
            d.get("detail", {}),
            d.get("severity", "high"),
            boot=boot,
        )
    raise ValueError(f"unknown message type: {t!r}")
