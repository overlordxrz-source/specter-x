"""The one reader that owns the ESP32-S3's USB serial port.

There must be exactly one reader per CDC node: two readers on the same port
fight over the bytes and neither sees a clean stream. This class is that
reader. It owns the port, feeds the :class:`SerialDispatcher`, and publishes
an acquisition health record.

It also *feeds* a :class:`SupervisorSource` rather than opening a second
port, so the supervisor's state machine is driven by the same bytes without
duplicating any logic.

States
------
``CONNECTED``    the port is open and packets are arriving
``CONNECTING``   opening or identifying
``STALLED``      the port is open but no bytes have arrived for a while
``DISCONNECTED`` the device went away (cable, reset, crash)
``ABSENT``       no such device on the bus
``ERROR``        anything else

A stalled or disconnected link is reported, never waited on: the reader keeps
running and the port is always released on stop.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from specter.hw.usb import find_usb_serial_ports

from .dispatcher import CsiRecord, SerialDispatcher
from .supervisor import SupervisorSource, SupervisorState

ESP32_USB_VID = 0x303A
ESP32_USB_PID = 0x1001


class LinkState(str, Enum):
    CONNECTED = "CONNECTED"
    CONNECTING = "CONNECTING"
    STALLED = "STALLED"
    DISCONNECTED = "DISCONNECTED"
    ABSENT = "ABSENT"
    ERROR = "ERROR"

    @property
    def healthy(self) -> bool:
        return self is LinkState.CONNECTED


@dataclass
class AcquisitionHealth:
    """Everything about the acquisition, for the HUD and the event log."""

    state: LinkState = LinkState.ABSENT
    detail: str = ""
    port: str = ""
    board_mac: str = ""
    uptime_s: float = 0.0
    bytes: int = 0
    packets: int = 0
    packets_per_s: float = 0.0
    gaps: int = 0
    missing_packets: int = 0
    malformed: int = 0
    unknown_lines: int = 0
    dropped: int = 0
    first_id: Optional[int] = None
    last_id: Optional[int] = None
    last_packet_at: float = 0.0
    silence_s: float = 0.0
    reconnects: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        data = dict(self.__dict__)
        data["state"] = self.state.value
        return data


class Esp32SerialReader:
    """Owns the ESP32-S3 CDC port and routes everything it says."""

    def __init__(self, port: Optional[str] = None, vid: int = ESP32_USB_VID,
                 pid: int = ESP32_USB_PID, stall_timeout: float = 5.0,
                 startup_grace: float = 20.0,
                 csi_capacity: int = 2048, supervisor_capacity: int = 64,
                 reconnect: bool = True, reconnect_delay: float = 2.0):
        self.port = port
        self.vid = vid
        self.pid = pid
        self.stall_timeout = stall_timeout
        #: The instrument needs ~10 s after a reset to bring up Wi-Fi and
        #: start streaming, so silence in this window is "warming up", not a
        #: stall.
        self.startup_grace = startup_grace
        self.reconnect = reconnect
        self.reconnect_delay = reconnect_delay

        self.dispatcher = SerialDispatcher(csi_capacity=csi_capacity,
                                           supervisor_capacity=supervisor_capacity)
        # the supervisor's state machine, fed by this reader rather than by a
        # second port
        self.supervisor = SupervisorSource(reader=None, port=None)
        self._supervisor_fed = False

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ser = None
        self._state = LinkState.ABSENT
        self._detail = "not started"
        self._start_time = 0.0
        self._last_byte = 0.0
        self._last_packet = 0.0
        self._reconnects = 0
        self._errors: List[str] = []
        self._board_mac = ""

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "Esp32SerialReader":
        if self._thread is not None:
            return self
        self._stop.clear()
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run, name="specter-esp32",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        """Stop and **always** release the port."""
        self._stop.set()
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
        with self._lock:
            self._ser = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    # -- acquisition -------------------------------------------------------

    def _set_state(self, state: LinkState, detail: str) -> None:
        with self._lock:
            self._state = state
            self._detail = detail

    def _open(self):
        from specter.hw.usb import serial_port_usb_ids
        ids = serial_port_usb_ids()
        candidates = []
        for path, info in ids.items():
            if info["vid"] == self.vid and info["pid"] == self.pid:
                candidates.append((path, info))
        if self.port:
            candidates = [(p, i) for p, i in candidates if p == self.port] or \
                         [(self.port, {})]
        if not candidates:
            self._set_state(LinkState.ABSENT, "no ESP32-S3 USB node found")
            return None, {}
        path, info = candidates[0]
        try:
            import serial
        except ImportError:
            self._set_state(LinkState.ERROR, "pyserial is not installed")
            return None, info
        try:
            ser = serial.Serial(path, baudrate=115200, timeout=0.5)
        except Exception as exc:
            self._set_state(LinkState.ERROR, f"{path}: {exc}")
            return None, info
        with self._lock:
            self._ser = ser
            self._board_mac = info.get("serial", "")
        self._set_state(LinkState.CONNECTING, f"{path}: opening")
        return ser, info

    def _run(self) -> None:
        while not self._stop.is_set():
            ser, info = self._open()
            if ser is None:
                if not self.reconnect or self._stop.is_set():
                    return
                self._stop.wait(self.reconnect_delay)
                continue
            self._read_loop(ser, info)
            try:
                ser.close()
            except Exception:
                pass
            with self._lock:
                self._ser = None
            if not self.reconnect or self._stop.is_set():
                return
            with self._lock:
                self._reconnects += 1
            self._set_state(LinkState.DISCONNECTED, "device went away; retrying")
            self._stop.wait(self.reconnect_delay)

    def _read_loop(self, ser, info) -> None:
        with self._lock:
            self._last_byte = time.time()
            opened_at = time.time()
        while not self._stop.is_set():
            try:
                waiting = ser.in_waiting
            except Exception as exc:
                self._set_state(LinkState.DISCONNECTED, f"device went away: {exc}")
                return
            if waiting:
                try:
                    data = ser.read(waiting)
                except Exception as exc:
                    self._set_state(LinkState.DISCONNECTED, f"read failed: {exc}")
                    return
                if data:
                    now = time.time()
                    with self._lock:
                        self._last_byte = now
                    self.dispatcher.feed(data)
                    self._feed_supervisor()
                    if self._state is not LinkState.CONNECTED:
                        self._set_state(LinkState.CONNECTED,
                                        f"{self.port or 'ESP32'}: streaming")
            else:
                now = time.time()
                with self._lock:
                    silence = now - self._last_byte
                if silence > self.stall_timeout:
                    if time.time() - opened_at < self.startup_grace:
                        self._set_state(LinkState.CONNECTING,
                                        f"{self.port or 'ESP32'}: waiting for the "
                                        f"app to start streaming")
                    else:
                        self._set_state(LinkState.STALLED,
                                        f"no data for {silence:.1f}s")
                time.sleep(0.005)

    def _feed_supervisor(self) -> None:
        """Hand any supervisor packets to the supervisor state machine."""
        for packet in self.dispatcher.drain_supervisor():
            self._supervisor_fed = True
            self.supervisor.ingest_packet(packet)

    # -- publishing --------------------------------------------------------

    def health(self) -> AcquisitionHealth:
        with self._lock:
            counters = self.dispatcher.snapshot()
            elapsed = max(time.time() - self._start_time, 1e-6)
            silence = time.time() - self._last_byte if self._last_byte else 0.0
            return AcquisitionHealth(
                state=self._state,
                detail=self._detail,
                port=self.port or "",
                board_mac=self._board_mac,
                uptime_s=elapsed,
                bytes=counters.get("bytes", 0),
                packets=counters.get("csi_parsed", 0),
                packets_per_s=counters.get("csi_parsed", 0) / elapsed,
                gaps=counters.get("csi_sequence_gaps", 0),
                missing_packets=counters.get("csi_missing_packets", 0),
                malformed=counters.get("csi_malformed", 0),
                unknown_lines=counters.get("unknown_lines", 0),
                dropped=counters.get("csi_dropped", 0),
                first_id=counters.get("csi_first_seq"),
                last_id=counters.get("csi_last_seq"),
                last_packet_at=self._last_packet,
                silence_s=silence,
                reconnects=self._reconnects,
                errors=list(self._errors),
            )

    def drain_csi(self) -> List[CsiRecord]:
        records = self.dispatcher.drain_csi()
        if records:
            with self._lock:
                self._last_packet = time.time()
        return records

    def supervisor_view(self) -> Dict:
        """The supervisor's state, and whether it is available at all.

        The board's current firmware does not emit supervisor packets, so the
        supervisor is reported as *explicitly unavailable* - never as a
        simulated heartbeat.
        """
        snap = self.supervisor.snapshot()
        available = self._supervisor_fed
        return {
            "available": available,
            "state": (snap.state.value if available else "UNAVAILABLE"),
            "detail": (snap.detail if available else
                       "instrument does not emit supervisor packets"),
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
        }
