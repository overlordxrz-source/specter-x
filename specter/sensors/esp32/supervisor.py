"""ESP32-S3 supervisor: device identity, uptime, heartbeat and health.

The supervisor is the ESP32-S3 acting as a **device that reports on itself**
over USB CDC. This module is the host half: it acquires the stream on a
background thread, keeps a bounded history, derives a health state and turns
the telemetry into provenance-tagged Measurements.

Two heartbeats, deliberately kept apart
---------------------------------------
The **device heartbeat** is the supervisor's own ``HB`` sequence, carried in
a Measurement over USB. The **network heartbeat** is the unit-level
``Heartbeat`` message in :mod:`specter.net.messages`, carried over the team
link. The first says "this board is alive"; the second says "this unit is on
the mesh". They are different sensors and are never merged.

Health is derived from two independent sources and both are reported:

* the **device's own** health word (``OK`` / ``WARN`` / ``DEGRADED`` / ``FAULT``);
* the **host's** view: is the heartbeat arriving, is the identity known, how
  many heartbeats have been missed.

A device that says it is fine but has stopped sending heartbeats is not
fine, and the host's view wins.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

from specter.fusion.measurement import Measurement, Provenance
from specter.hw.usb import find_usb_serial_ports
from specter.sensors.base import Health, SensorStatus

from .protocol import (ESP32_USB_PID, ESP32_USB_VID, SupervisorHeartbeat,
                        SupervisorIdentity, SupervisorStatus, parse_line)

#: Sensor key used in SENSOR_LABELS and Provenance.source.
SOURCE = "supervisor"
#: Sensor id used before the device has introduced itself.
UNKNOWN_ID = "unknown"


class SupervisorState(str, Enum):
    """Host-derived state of the supervisor link."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    NOT_INSTALLED = "N/A"

    @property
    def health(self) -> Health:
        return {
            SupervisorState.OK: Health.OK,
            SupervisorState.DEGRADED: Health.DEGRADED,
            SupervisorState.OFFLINE: Health.OFFLINE,
            SupervisorState.NOT_INSTALLED: Health.NOT_INSTALLED,
        }[self]


@dataclass
class SupervisorSnapshot:
    """Everything the HUD needs about the supervisor, at one instant."""

    state: SupervisorState = SupervisorState.NOT_INSTALLED
    detail: str = ""
    identity: Optional[SupervisorIdentity] = None
    status: Optional[SupervisorStatus] = None
    heartbeat_seq: int = 0
    heartbeats: int = 0
    missed_heartbeats: int = 0
    malformed_lines: int = 0
    uptime_s: float = 0.0
    heartbeat_age_s: float = 0.0
    port: str = ""
    usb: Dict = field(default_factory=dict)
    last_seen_at: float = 0.0

    @property
    def identity_known(self) -> bool:
        return self.identity is not None

    @property
    def device_health(self) -> str:
        """The device's own opinion of its health, or UNKNOWN."""
        return self.status.health if self.status else "UNKNOWN"

    def as_dict(self) -> Dict:
        return {
            "state": self.state.value,
            "detail": self.detail,
            "identity_known": self.identity_known,
            "identity": ({"board": self.identity.board, "chip": self.identity.chip,
                          "mac": self.identity.mac,
                          "fw_version": self.identity.fw_version,
                          "fw_build": self.identity.fw_build,
                          "label": self.identity.label}
                         if self.identity else None),
            "device_health": self.device_health,
            "heartbeat_seq": self.heartbeat_seq,
            "heartbeats": self.heartbeats,
            "missed_heartbeats": self.missed_heartbeats,
            "malformed_lines": self.malformed_lines,
            "uptime_s": self.uptime_s,
            "heartbeat_age_s": self.heartbeat_age_s,
            "port": self.port,
            "usb": self.usb,
        }


class SupervisorSource:
    """Acquires the supervisor stream and publishes bounded snapshots."""

    def __init__(self, port: Optional[str] = None,
                 heartbeat_timeout: float = 3.0,
                 heartbeat_grace: float = 1.5,
                 log_interval: float = 1.0,
                 stall_timeout: float = 5.0,
                 history: int = 120,
                 reader=None):
        self.port = port
        #: How long without a heartbeat before the link is called dead.
        self.heartbeat_timeout = heartbeat_timeout
        #: How long after a missed deadline the state is DEGRADED, not OFFLINE.
        self.heartbeat_grace = heartbeat_grace
        self.log_interval = log_interval
        self.stall_timeout = stall_timeout
        self.history = history
        #: Injected byte source (tests, simulator). None means "open a port".
        self._reader = reader

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._ser = None

        self._state = SupervisorState.NOT_INSTALLED
        #: Set when the *link* itself is broken (no device, port error, the
        #: device went silent). None means "the link is up" and the state is
        #: derived from the heartbeat instead.
        self._link_state: Optional[SupervisorState] = None
        self._detail = "not started"
        self._identity: Optional[SupervisorIdentity] = None
        self._status: Optional[SupervisorStatus] = None
        self._hb_seq = 0
        self._hb_count = 0
        self._missed = 0
        self._malformed = 0
        self._last_hb_at = 0.0
        self._last_seen_at = 0.0
        self._uptime = 0.0
        self._events: Deque[dict] = deque(maxlen=history)
        self._last_log = 0.0
        self._port = port or ""
        self._usb: Dict = {}

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "SupervisorSource":
        if self._thread is not None:
            return self
        self._stop.clear()
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, name="specter-esp32",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        """Stop acquisition and always release the port."""
        self._stop.set()
        self._cancel.clear()
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        if thread is not None and thread.is_alive():
            ser = self._ser
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            thread.join(timeout=timeout)
        if thread is not None and not thread.is_alive():
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    # -- acquisition -------------------------------------------------------

    def _open(self):
        """Open the supervisor's USB CDC node, or use the injected reader."""
        if self._reader is not None:
            return self._reader, self.port or "injected"
        port = self.port
        if not port:
            nodes = find_usb_serial_ports(vid=ESP32_USB_VID, pid=ESP32_USB_PID)
            if not nodes:
                self._set_link_state(SupervisorState.NOT_INSTALLED,
                                     "no ESP32 USB serial node found")
                return None, ""
            port = nodes[0]
        try:
            import serial
        except ImportError:
            self._set_link_state(SupervisorState.NOT_INSTALLED,
                                 "pyserial is not installed")
            return None, ""
        try:
            ser = serial.Serial(port, baudrate=115200, timeout=0.5)
        except Exception as exc:
            self._set_link_state(SupervisorState.OFFLINE, f"{port}: {exc}")
            return None, ""
        return ser, port

    def _run(self) -> None:
        try:
            self._acquire()
        except Exception as exc:  # pragma: no cover - defensive
            self._set_state(SupervisorState.OFFLINE, f"{type(exc).__name__}: {exc}")

    def _acquire(self) -> None:
        ser, port = self._open()
        if ser is None:
            return
        self._ser = ser
        with self._lock:
            self._port = port
        self._set_link_state(None, "connecting, identity unknown")
        buf = b""
        last_byte = time.time()
        try:
            while not self._cancel.is_set():
                chunk = self._read_available(ser)
                now = time.time()
                if chunk:
                    last_byte = now
                    buf += chunk
                    parts = buf.replace(b"\r\n", b"\n").split(b"\n")
                    buf = parts.pop()
                    for raw in parts:
                        self._handle_line(raw.decode("utf-8", "replace"))
                else:
                    if (now - last_byte) > self.stall_timeout:
                        self._set_link_state(
                            SupervisorState.OFFLINE,
                            f"no data for {now - last_byte:.1f}s")
                        return
                    time.sleep(0.005)
        finally:
            try:
                ser.close()
            except Exception:
                pass
            if self._ser is ser:
                self._ser = None

    @staticmethod
    def _read_available(ser) -> bytes:
        try:
            waiting = ser.in_waiting
        except Exception:
            return b""
        if not waiting:
            return b""
        try:
            return ser.read(waiting)
        except Exception:
            return b""

    def ingest(self, line: str) -> None:
        """Feed one protocol line (used by the standalone reader)."""
        self._handle_line(line)

    def ingest_packet(self, packet) -> None:
        """Feed an already-parsed packet (used by the shared reader)."""
        self._apply_packet(packet)

    def _handle_line(self, line: str) -> None:
        packet = parse_line(line)
        if packet is None:
            if line.strip():
                with self._lock:
                    self._malformed += 1
            return
        self._apply_packet(packet)

    def _apply_packet(self, packet) -> None:
        now = time.time()
        with self._lock:
            if isinstance(packet, SupervisorIdentity):
                self._identity = packet
                self._set_state_locked(SupervisorState.DEGRADED,
                                       "identity known, awaiting heartbeat")
            elif isinstance(packet, SupervisorStatus):
                self._status = packet
                self._uptime = packet.uptime_s
            elif isinstance(packet, SupervisorHeartbeat):
                if self._hb_seq and packet.seq != self._hb_seq + 1:
                    self._missed += max(0, packet.seq - self._hb_seq - 1)
                self._hb_seq = packet.seq
                self._hb_count += 1
                self._last_hb_at = now
                self._uptime = packet.uptime_s
                self._set_state_locked(SupervisorState.OK, "heartbeat ok")
            self._last_seen_at = now
            self._events.append({"t": now, "seq": getattr(packet, "seq", None),
                                 "uptime_s": getattr(packet, "uptime_s", None)})

    def _set_state(self, state: SupervisorState, detail: str) -> None:
        with self._lock:
            self._set_state_locked(state, detail)

    def _set_state_locked(self, state: SupervisorState, detail: str) -> None:
        self._state = state
        self._detail = detail

    def _set_link_state(self, state: Optional[SupervisorState], detail: str) -> None:
        """Record a link-level failure (or clear it)."""
        with self._lock:
            self._link_state = state
            self._detail = detail

    # -- publishing --------------------------------------------------------

    def _derive_state(self) -> SupervisorState:
        """The host's view, which overrides the device's own opinion."""
        if self._link_state is not None:
            return self._link_state
        if self._identity is None and self._hb_count == 0:
            return SupervisorState.NOT_INSTALLED
        age = time.time() - self._last_hb_at if self._last_hb_at else 0.0
        if self._hb_count == 0:
            return SupervisorState.DEGRADED
        if age > self.heartbeat_timeout:
            return SupervisorState.OFFLINE
        if age > self.heartbeat_grace:
            return SupervisorState.DEGRADED
        if self._status and self._status.health not in ("OK", ""):
            return SupervisorState.DEGRADED
        return SupervisorState.OK

    def snapshot(self) -> SupervisorSnapshot:
        with self._lock:
            state = self._derive_state()
            age = (time.time() - self._last_hb_at) if self._last_hb_at else 0.0
            return SupervisorSnapshot(
                state=state,
                detail=self._detail,
                identity=self._identity,
                status=self._status,
                heartbeat_seq=self._hb_seq,
                heartbeats=self._hb_count,
                missed_heartbeats=self._missed,
                malformed_lines=self._malformed,
                uptime_s=self._uptime,
                heartbeat_age_s=age,
                port=self._port,
                usb=dict(self._usb),
                last_seen_at=self._last_seen_at,
            )

    def status(self) -> SensorStatus:
        """Sensor-health row: the link to the supervisor, not its telemetry."""
        snap = self.snapshot()
        if snap.state is SupervisorState.NOT_INSTALLED:
            return SensorStatus(SOURCE, "SUPERVISOR ESP32", Health.NOT_INSTALLED,
                                snap.detail[:30])
        # the panel truncates the detail at 30 characters, so keep it short
        if not snap.identity_known:
            detail = "identity unknown"
        else:
            detail = snap.identity.chip[:14] if snap.identity else ""
        if snap.heartbeats:
            detail += f" | hb {snap.heartbeat_seq}"
        return SensorStatus(SOURCE, "SUPERVISOR ESP32", snap.state.health,
                            detail[:30])

    def take_measurement(self) -> Optional[Measurement]:
        """One Measurement, rate limited to ``log_interval`` seconds."""
        now = time.time()
        if now - self._last_log < self.log_interval:
            return None
        self._last_log = now
        snap = self.snapshot()
        if snap.state is SupervisorState.NOT_INSTALLED:
            return None

        value = {
            "state": snap.state.value,
            "detail": snap.detail,
            "identity_known": snap.identity_known,
            "identity": ({"board": snap.identity.board, "chip": snap.identity.chip,
                          "mac": snap.identity.mac,
                          "fw_version": snap.identity.fw_version,
                          "fw_build": snap.identity.fw_build}
                         if snap.identity else None),
            "device_health": snap.device_health,
            "heartbeat_seq": snap.heartbeat_seq,
            "heartbeats": snap.heartbeats,
            "missed_heartbeats": snap.missed_heartbeats,
            "malformed_lines": snap.malformed_lines,
            "uptime_s": snap.uptime_s,
            "heartbeat_age_s": snap.heartbeat_age_s,
            "port": snap.port,
        }
        if snap.identity is not None:
            sensor_id = snap.identity.mac
            model_version = snap.identity.fw_build
        else:
            # no identity yet: say so rather than inventing one
            sensor_id = UNKNOWN_ID
            model_version = None
        notes = ("identity not yet reported" if not snap.identity_known
                 else f"device health {snap.device_health}")
        prov = Provenance(
            sensor_id=sensor_id,
            source=SOURCE,
            algorithm="esp32-supervisor/v1",
            model_version=model_version,
            frame_index=snap.heartbeat_seq,
            parents=(),
            notes=notes,
        )
        return Measurement(
            sensor=SOURCE,
            kind="supervisor_status",
            t_host=now,
            frame_id="supervisor",
            value=value,
            provenance=prov,
            t_sensor=snap.uptime_s or None,
            confidence=None,
            covariance=None,
        )
