"""ESP32-S3 supervisor: a device that reports on itself over USB.

Alpha 002-A is the **host side only**: the protocol, the acquisition, the
health model and the Measurement/JSONL/HUD plumbing. The firmware that will
produce these packets is a later milestone; until then the simulator in
:mod:`.simulator` stands in for it.

The supervisor's *device heartbeat* (its own ``HB`` sequence, carried over
USB) is deliberately distinct from the unit-level *network heartbeat* in
:mod:`specter.net.messages` (carried over the team link).
"""
from .protocol import (ESP32_USB_PID, ESP32_USB_VID, PROTOCOL_VERSION,
                        SupervisorHeartbeat, SupervisorIdentity,
                        SupervisorStatus, format_heartbeat, format_identity,
                        format_status, parse_line)
from .simulator import SimulatedSupervisor, SimulatorReader
from .supervisor import (SOURCE, SupervisorSnapshot, SupervisorSource,
                          SupervisorState)

__all__ = [
    "ESP32_USB_PID", "ESP32_USB_VID", "PROTOCOL_VERSION",
    "SupervisorHeartbeat", "SupervisorIdentity", "SupervisorStatus",
    "format_heartbeat", "format_identity", "format_status", "parse_line",
    "SimulatedSupervisor", "SimulatorReader", "SOURCE", "SupervisorSnapshot",
    "SupervisorSource", "SupervisorState",
]
