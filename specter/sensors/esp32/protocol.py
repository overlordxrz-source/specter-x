"""Wire protocol for the ESP32-S3 supervisor.

The supervisor is a small ESP32-S3 that reports on **itself**: who it is,
how long it has been up, that it is still alive, and what its own health is.
It streams ASCII lines over USB CDC, one packet per line, CR or LF terminated.

    HELLO,<proto>,<board>,<chip>,<mac>,<fw_version>,<fw_build>
    STAT,<uptime_s>,<heap_free>,<heap_min>,<health>
    HB,<seq>,<uptime_s>

The CSV-with-a-type-tag shape matches the CSI streamer already described in
``firmware/esp32-csi/README.md``, so both can share a host-side line reader.

Two heartbeats, deliberately kept apart
---------------------------------------
* the **device heartbeat** is this: the supervisor's own ``HB`` sequence,
  carried in a Measurement over USB;
* the **network heartbeat** is the unit-level ``Heartbeat`` message in
  ``specter/net/messages.py``, carried over the team link.

They answer different questions and must not be conflated: the device
heartbeat says "this board is alive", the network heartbeat says "this unit
is on the mesh and where it thinks it is".

The firmware side is not written yet (Alpha 002-A is host side only). The
protocol is specified here so the host can be built and tested against a
simulator first.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

#: Version of the wire format. Bumped when a field changes meaning.
PROTOCOL_VERSION = 1

#: Espressif native USB (USB-Serial/JTAG) VID:PID. The supervisor appears
#: here when it enumerates over its own USB port.
ESP32_USB_VID = 0x303A
ESP32_USB_PID = 0x1001

#: Health words the device may report for itself.
DEVICE_HEALTH_WORDS = ("OK", "WARN", "DEGRADED", "FAULT")

Packet = Union["SupervisorIdentity", "SupervisorStatus", "SupervisorHeartbeat"]


@dataclass(frozen=True)
class SupervisorIdentity:
    """Who the supervisor says it is."""

    protocol: int
    board: str
    chip: str
    mac: str
    fw_version: str
    fw_build: str

    @property
    def label(self) -> str:
        return f"{self.board} {self.chip}"


@dataclass(frozen=True)
class SupervisorStatus:
    """Periodic health telemetry from the supervisor."""

    uptime_s: float
    heap_free: int
    heap_min: int
    health: str


@dataclass(frozen=True)
class SupervisorHeartbeat:
    """The supervisor's own liveness counter."""

    seq: int
    uptime_s: float


def _float(text: str) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int(text: str) -> Optional[int]:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_line(line: str) -> Optional[Packet]:
    """Parse one protocol line.

    Returns ``None`` for anything that is not a well-formed packet: an
    unknown type, the wrong number of fields, or a non-numeric field. The
    caller counts those; a malformed line is never fatal, because a device
    that also logs other things will interleave them.
    """
    if line is None:
        return None
    text = line.strip()
    if not text:
        return None
    parts = text.split(",")
    kind = parts[0].strip().upper()

    if kind == "HELLO":
        if len(parts) != 7:
            return None
        proto = _int(parts[1].strip())
        if proto is None:
            return None
        board = parts[2].strip()
        chip = parts[3].strip()
        mac = parts[4].strip()
        if not board or not chip or not mac:
            return None
        return SupervisorIdentity(proto, board, chip, mac,
                                  parts[5].strip(), parts[6].strip())

    if kind == "STAT":
        if len(parts) != 5:
            return None
        uptime = _float(parts[1].strip())
        heap_free = _int(parts[2].strip())
        heap_min = _int(parts[3].strip())
        if uptime is None or heap_free is None or heap_min is None:
            return None
        health = parts[4].strip().upper() or "UNKNOWN"
        return SupervisorStatus(uptime, heap_free, heap_min, health)

    if kind == "HB":
        if len(parts) != 3:
            return None
        seq = _int(parts[1].strip())
        uptime = _float(parts[2].strip())
        if seq is None or uptime is None:
            return None
        return SupervisorHeartbeat(seq, uptime)

    return None


def format_identity(board: str, chip: str, mac: str, fw_version: str,
                     fw_build: str) -> str:
    """Build a HELLO line (used by the simulator and by future firmware)."""
    return (f"HELLO,{PROTOCOL_VERSION},{board},{chip},{mac},"
            f"{fw_version},{fw_build}")


def format_status(uptime_s: float, heap_free: int, heap_min: int,
                  health: str = "OK") -> str:
    """Build a STAT line."""
    return f"STAT,{uptime_s:.3f},{heap_free},{heap_min},{health}"


def format_heartbeat(seq: int, uptime_s: float) -> str:
    """Build an HB line."""
    return f"HB,{seq},{uptime_s:.3f}"
