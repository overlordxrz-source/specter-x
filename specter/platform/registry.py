"""Common sensor registry, replay health and bounded diagnostic retention."""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import math
from .observation import Observation, ContractError


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: str
    node_id: str
    label: str
    kind: str
    units: str
    frame_id: str
    note: str = "No driver opened in this session"

    def __post_init__(self):
        for v in (
            self.sensor_id,
            self.node_id,
            self.label,
            self.kind,
            self.units,
            self.frame_id,
        ):
            if not isinstance(v, str) or not v:
                raise ValueError("sensor spec requires explicit identifiers")


@dataclass
class StreamState:
    spec: SensorSpec
    state: str = "OFFLINE"
    received: int = 0
    source_missing: int = 0
    buffer_evictions: int = 0
    last_seq: int | None = None
    last_epoch: str | None = None
    clock_contract: tuple | None = None
    last_playback_ns: int | None = None
    rate_hz: float | None = None
    last: Observation | None = None
    times: deque = field(default_factory=lambda: deque(maxlen=128))


class Registry:
    def __init__(self, capacity=256):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("positive capacity required")
        self.streams = {}
        self.history = deque(maxlen=capacity)
        self.evictions = 0

    def register(self, spec):
        if spec.sensor_id in self.streams:
            raise ValueError("duplicate sensor ID")
        self.streams[spec.sensor_id] = StreamState(spec)

    def ingest(self, obs, playback_ns):
        if type(playback_ns) is not int or playback_ns < 0:
            raise ValueError("monotonic playback ns required")
        d = obs.to_dict()
        if d["sensor_id"] not in self.streams:
            raise ContractError("unregistered source")
        st = self.streams[d["sensor_id"]]
        for key in ("node_id", "kind", "units", "frame_id"):
            if d[key] != getattr(st.spec, key):
                st.state = "ERROR"
                raise ContractError("registry " + key + " mismatch")
        if st.last_playback_ns is not None and playback_ns < st.last_playback_ns:
            raise ContractError(
                "playback clock went backwards; seek must rebuild state"
            )
        ep = d["acquisition"]["epoch"]
        if st.last_epoch == ep and st.last_seq is not None and d["seq"] <= st.last_seq:
            st.state = "ERROR"
            raise ContractError("duplicate/out-of-order observation")
        ac = d["acquisition"]
        contract = (ac["domain"], ac["tick_hz"], ac["wrap_bits"])
        if st.last_epoch == ep and st.clock_contract != contract:
            st.state = "ERROR"
            raise ContractError("clock contract changed within epoch")
        t = (
            None
            if ac["unwrapped_ticks"] is None
            else ac["unwrapped_ticks"] / ac["tick_hz"]
        )
        if ep == st.last_epoch and t is not None and st.times and t < st.times[-1]:
            st.state = "ERROR"
            raise ContractError("acquisition clock moved backwards in epoch")
        if (
            ep == st.last_epoch
            and st.last_seq is not None
            and d["dropped_before"] != d["seq"] - st.last_seq - 1
        ):
            st.state = "ERROR"
            raise ContractError("sequence/drop accounting mismatch")
        if ep != st.last_epoch:
            st.times.clear()
            st.rate_hz = None
        st.last_epoch = ep
        st.clock_contract = contract
        st.last_seq = d["seq"]
        st.last_playback_ns = playback_ns
        st.received += 1
        st.source_missing += d["dropped_before"]
        st.last = obs
        if t is not None:
            st.times.append(t)
            if len(st.times) > 1 and t > st.times[0]:
                st.rate_hz = (len(st.times) - 1) / (t - st.times[0])
        st.state = "SIMULATED" if d["origin"] == "simulated" else "REPLAY"
        if d["validity"]["state"] == "invalid":
            st.state = "ERROR"
        if len(self.history) == self.history.maxlen:
            old = self.history[0].to_dict()["sensor_id"]
            self.streams[old].buffer_evictions += 1
            self.evictions += 1
        self.history.append(obs)

    def mark_stale(self, now_ns, max_age_ns=2_000_000_000):
        for st in self.streams.values():
            if (
                st.last_playback_ns is not None
                and now_ns - st.last_playback_ns > max_age_ns
            ):
                st.state = "STALE"

    def disconnect(self, sensor_id):
        self.streams[sensor_id].state = "OFFLINE"


def default_registry(capacity=256):
    r = Registry(capacity)
    r.register(
        SensorSpec(
            "bench/esp32-s3/csi",
            "bench",
            "ESP32-S3 / Wi-Fi CSI",
            "csi_lltf_amplitude",
            "gain_compensated_csi_counts",
            "esp32/lltf-frequency",
            "Recorded hardware replay; no motion inference",
        )
    )
    r.register(
        SensorSpec(
            "bench/di188/analog",
            "bench",
            "DI-188 / Analog",
            "analog_voltage",
            "V",
            "di188/channel",
            "Prior streaming recorded; no live connection opened",
        )
    )
    r.register(
        SensorSpec(
            "future/thermal",
            "future",
            "Thermal / future",
            "thermal_image",
            "degC",
            "thermal/optical",
            "UNAVAILABLE: module / driver / calibration not established",
        )
    )
    r.streams["future/thermal"].state = "UNAVAILABLE"
    return r


class ReplaySession:
    def __init__(self, observations, capacity=256):
        self.observations = tuple(observations)
        self.capacity = capacity
        self.position = -1
        self.registry = default_registry(capacity)

    def seek(self, index):
        if not self.observations:
            raise ValueError("empty session")
        if type(index) is not int:
            raise ValueError("integer index required")
        index = max(0, min(index, len(self.observations) - 1))
        self.registry = default_registry(self.capacity)
        for i in range(index + 1):
            self.registry.ingest(self.observations[i], i * 1_000_000)
        self.position = index

    def step(self):
        if self.position + 1 >= len(self.observations):
            return False
        self.position += 1
        self.registry.ingest(
            self.observations[self.position], self.position * 1_000_000
        )
        return True
