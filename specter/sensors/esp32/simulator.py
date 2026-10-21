"""A simulated ESP32-S3 supervisor, so the host half can be built and tested
before the firmware exists.

It produces exactly the lines the real firmware will produce, with knobs for
the situations the host has to survive: a device that never introduces
itself, one that sends garbage, one whose heartbeats stop, and one that
restarts (so the sequence number goes backwards).

Used by the CI tests and by ``python -m specter.sensors.esp32.simulator`` to
drive the dashboard without hardware.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from .protocol import (format_heartbeat, format_identity, format_status)


class SimulatedSupervisor:
    """Produces supervisor protocol lines on demand."""

    def __init__(self, board: str = "esp32s3-devkitc-1", chip: str = "ESP32-S3",
                 mac: str = "14:C1:9F:26:52:EC", fw_version: str = "0.1.0",
                 fw_build: str = "sim", rate_hz: float = 1.0,
                 announce_identity: bool = True,
                 garbage_every: int = 0,
                 start_seq: int = 0):
        self.board = board
        self.chip = chip
        self.mac = mac
        self.fw_version = fw_version
        self.fw_build = fw_build
        self.rate_hz = rate_hz
        self.announce_identity = announce_identity
        #: Emit a malformed line every N packets (0 = never).
        self.garbage_every = garbage_every
        self.start_seq = start_seq
        self.seq = start_seq
        self.uptime = 0.0
        self.sent = 0
        self.health = "OK"

    def lines(self, count: int = 1) -> List[str]:
        """Produce the next ``count`` protocol lines."""
        out: List[str] = []
        if self.announce_identity and self.sent == 0:
            out.append(format_identity(self.board, self.chip, self.mac,
                                       self.fw_version, self.fw_build))
        for _ in range(count):
            self.uptime += 1.0 / max(self.rate_hz, 0.01)
            self.seq += 1
            if self.garbage_every and self.sent % self.garbage_every == 0 \
                    and self.garbage_every > 0:
                out.append("this line is not a protocol packet")
            out.append(format_status(self.uptime, 180000, 170000, self.health))
            out.append(format_heartbeat(self.seq, self.uptime))
            self.sent += 1
        return out


class SimulatorReader:
    """A file-like byte source that serves a simulated supervisor.

    It mimics the pyserial surface the acquisition code uses
    (``in_waiting`` / ``read``), so the whole host path can be driven
    without a serial port.
    """

    def __init__(self, sim: Optional[SimulatedSupervisor] = None,
                 rate_hz: float = 20.0):
        self.sim = sim or SimulatedSupervisor(rate_hz=rate_hz)
        self._buf = bytearray()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self.sent_packets = 0
        self._thread.start()

    def _pump(self):
        period = 1.0 / max(self.sim.rate_hz, 1.0)
        while not self._stop.is_set():
            for line in self.sim.lines(1):
                self._buf += (line + "\r\n").encode()
            self.sent_packets += 1
            self._stop.wait(period)

    @property
    def in_waiting(self) -> int:
        return len(self._buf)

    def read(self, size: int = 1) -> bytes:
        out = bytes(self._buf[:size])
        del self._buf[:size]
        return out

    def close(self) -> None:
        self._stop.set()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def main():  # pragma: no cover - manual driver
    """Print simulated supervisor traffic to stdout."""
    sim = SimulatedSupervisor()
    while True:
        for line in sim.lines(1):
            print(line)
        time.sleep(1.0 / max(sim.rate_hz, 0.01))


if __name__ == "__main__":  # pragma: no cover
    main()
