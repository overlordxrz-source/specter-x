"""Team message types: Heartbeat, PoseStamped, TrackReport, Alert.

Compact by design: tracks travel, video never does. Each TrackReport keeps
the source unit, sensor and Measurement ids so provenance survives the
network hop and the HUD can still print SRC: <UNIT>/<SENSOR>.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

HEARTBEAT, POSE, TRACK, ALERT = "heartbeat", "pose", "track", "alert"
SCHEMA_V1 = 1


@dataclass
class Message:
    type: str
    unit_id: str
    seq: int
    t_host: float
    schema: int = SCHEMA_V1
    boot: str = ""  # sender boot id: ordered per boot, see security.generate_boot_id

    def body(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("schema", None)
        return d

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, separators=(",", ":"))

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

    def __init__(self, unit_id: str, seq: int, t_host: float, track_id: int,
                 position_enu, cov_3x3, source_unit: str = "",
                 source_sensor: str = "fusion", measurement_ids=(),
                 confidence: float = 0.5, label: str = "contact",
                 boot: str = "") -> None:
        super().__init__(TRACK, unit_id, seq, t_host, boot=boot)
        self.track_id = int(track_id)
        self.position_enu = [float(v) for v in position_enu]
        self.cov_3x3 = [[float(c) for c in row] for row in cov_3x3]
        self.source_unit = source_unit or unit_id
        self.source_sensor = source_sensor
        self.measurement_ids = list(measurement_ids)
        self.confidence = float(confidence)
        self.label = label

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
    if not isinstance(d, dict) or d.get("schema") != SCHEMA_V1:
        raise ValueError(f"unsupported schema: {d.get('schema') if isinstance(d, dict) else type(d)}")
    t = d.get("type")
    u, seq, th = d.get("unit_id", "?"), int(d.get("seq", 0)), float(d.get("t_host", time.time()))
    boot = str(d.get("boot", ""))
    if t == HEARTBEAT:
        return Heartbeat(u, seq, th, d.get("mode", "REL"),
                         float(d.get("pos_rmse", 99.0)), d.get("health", "OK"),
                         boot=boot)
    if t == POSE:
        return PoseStamped(u, seq, th, d.get("position_enu", [0, 0, 0]),
                           d.get("velocity_enu", [0, 0, 0]),
                           d.get("cov_pos_3x3", [[25, 0, 0], [0, 25, 0], [0, 0, 25]]),
                           d.get("mode", "REL"), d.get("anchor"),
                           d.get("quat_wxyz"), boot=boot)
    if t == TRACK:
        return TrackReport(u, seq, th, int(d.get("track_id", 0)),
                           d.get("position_enu", [0, 0, 0]),
                           d.get("cov_3x3", [[4, 0, 0], [0, 4, 0], [0, 0, 4]]),
                           d.get("source_unit", u), d.get("source_sensor", "fusion"),
                           d.get("measurement_ids", []),
                           float(d.get("confidence", 0.5)), d.get("label", "contact"),
                           boot=boot)
    if t == ALERT:
        return Alert(u, seq, th, d.get("kind", "man-down"),
                     d.get("detail", {}), d.get("severity", "high"), boot=boot)
    raise ValueError(f"unknown message type: {t!r}")
