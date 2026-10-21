"""ESP32-S3 supervisor: protocol, identity, health, missed heartbeats, recovery.

Everything here runs without hardware: the simulator and a scripted reader
stand in for the device, so the whole host path is exercised in CI.
"""
import time

import pytest

from specter.fusion.measurement import SENSOR_LABELS
from specter.sensors.base import Health
from specter.sensors.esp32 import (SupervisorIdentity, SupervisorSource,
                                    SupervisorState, format_heartbeat,
                                    format_identity, format_status, parse_line)
from specter.sensors.esp32.simulator import SimulatedSupervisor, SimulatorReader


class ScriptedReader:
    """A byte source that serves a fixed script and then goes quiet."""

    def __init__(self, chunks=None, silent_after=True):
        self._buf = bytearray()
        self._chunks = list(chunks or [])
        self._silent_after = silent_after
        self.closed = False

    def feed(self, text: str) -> None:
        self._buf += text.encode()

    @property
    def in_waiting(self) -> int:
        return len(self._buf)

    def read(self, size: int = 1) -> bytes:
        out = bytes(self._buf[:size])
        del self._buf[:size]
        return out

    def close(self) -> None:
        self.closed = True


def _wait(predicate, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- protocol --------------------------------------------------------------

def test_parses_the_three_packet_types():
    ident = parse_line("HELLO,1,esp32s3-devkitc-1,ESP32-S3,14:C1:9F:26:52:EC,0.1.0,abc123")
    assert isinstance(ident, SupervisorIdentity)
    assert ident.protocol == 1
    assert ident.board == "esp32s3-devkitc-1"
    assert ident.chip == "ESP32-S3"
    assert ident.mac == "14:C1:9F:26:52:EC"
    assert ident.fw_version == "0.1.0"
    assert ident.fw_build == "abc123"

    stat = parse_line("STAT,123.456,180000,170000,OK")
    assert stat is not None and stat.uptime_s == pytest.approx(123.456)
    assert stat.heap_free == 180000 and stat.health == "OK"

    hb = parse_line("HB,42,123.456")
    assert hb is not None and hb.seq == 42


@pytest.mark.parametrize("line", [
    "",
    "   ",
    "HELLO,1,board",                                  # too few fields
    "HELLO,1,board,chip,mac,1.0,build,extra",         # too many fields
    "HELLO,x,board,chip,mac,1.0,build",               # non-numeric protocol
    "HELLO,1,,chip,mac,1.0,build",                    # empty board
    "HELLO,1,board,chip,,1.0,build",                  # empty mac
    "STAT,abc,1,2,OK",                                # non-numeric uptime
    "STAT,1,2",                                      # too few fields
    "STAT,1,2,3,OK,extra",                            # too many fields
    "HB,notanumber,1.0",                              # non-numeric seq
    "HB,1",                                           # too few fields
    "HB,1,2,3",                                       # too many fields
    "NONSENSE,1,2,3",                                 # unknown type
    "I (2701) wifi:new:<11,0>",                       # an interleaved log line
    "CSI_DATA,7182,b8:62:1f:b4:a5:62,-73,11,1,4,0,0",  # CSI traffic
    None,
])
def test_malformed_packets_are_rejected(line):
    assert parse_line(line) is None


def test_a_malformed_line_does_not_break_the_stream():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("garbage")
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("more garbage")
    src._handle_line("HB,1,0.5")
    snap = src.snapshot()
    assert snap.malformed_lines == 2
    assert snap.identity_known
    assert snap.heartbeat_seq == 1


# --- identity --------------------------------------------------------------

def test_identity_is_unknown_until_the_device_says_who_it_is():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HB,1,0.5")
    snap = src.snapshot()
    assert not snap.identity_known
    m = src.take_measurement()
    assert m is not None
    # the identity is never invented
    assert m.provenance.sensor_id == "unknown"
    assert m.provenance.model_version is None
    assert "identity not yet reported" in m.provenance.notes
    assert m.value["identity"] is None


def test_identity_is_reported_once_the_device_introduces_itself():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HELLO,1,esp32s3-devkitc-1,ESP32-S3,14:C1:9F:26:52:EC,0.1.0,abc123")
    src._handle_line("HB,1,0.5")
    m = src.take_measurement()
    assert m.provenance.sensor_id == "14:C1:9F:26:52:EC"
    assert m.provenance.model_version == "abc123"
    assert m.provenance.source == "supervisor"
    assert m.value["identity"]["board"] == "esp32s3-devkitc-1"


# --- heartbeats ------------------------------------------------------------

def test_missed_heartbeats_are_counted():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HB,1,0.5")
    src._handle_line("HB,2,1.0")
    src._handle_line("HB,5,4.0")        # 3 and 4 never arrived
    snap = src.snapshot()
    assert snap.missed_heartbeats == 2
    assert snap.heartbeat_seq == 5


def test_a_device_restart_is_not_counted_as_missed_heartbeats():
    """The sequence going backwards means a reboot, not a lost packet."""
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HB,100,10.0")
    src._handle_line("HB,1,0.1")        # rebooted
    snap = src.snapshot()
    assert snap.missed_heartbeats == 0
    assert snap.heartbeat_seq == 1


def test_a_late_heartbeat_degrades_the_link():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=10.0,
                           heartbeat_grace=0.05)
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("HB,1,0.5")
    time.sleep(0.12)
    assert src.snapshot().state is SupervisorState.DEGRADED
    assert src.snapshot().heartbeat_age_s > 0.05


def test_a_missing_heartbeat_offlines_the_link():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=0.2,
                           heartbeat_grace=0.1)
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("HB,1,0.5")
    time.sleep(0.35)
    snap = src.snapshot()
    assert snap.state is SupervisorState.OFFLINE
    assert snap.state.health is Health.OFFLINE


def test_the_link_recovers_when_heartbeats_resume():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=0.2,
                           heartbeat_grace=0.1)
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("HB,1,0.5")
    time.sleep(0.35)
    assert src.snapshot().state is SupervisorState.OFFLINE
    src._handle_line("HB,2,1.0")
    assert src.snapshot().state is SupervisorState.OK
    assert src.snapshot().heartbeat_seq == 2


def test_a_device_warning_degrades_an_otherwise_healthy_link():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=10.0)
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("HB,1,0.5")
    src._handle_line(format_status(1.0, 1000, 900, "WARN"))
    assert src.snapshot().state is SupervisorState.DEGRADED
    assert src.snapshot().device_health == "WARN"


def test_the_device_health_word_is_reported_separately_from_the_host_state():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=10.0)
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("HB,1,0.5")
    src._handle_line(format_status(1.0, 1000, 900, "WARN"))
    snap = src.snapshot()
    assert snap.device_health == "WARN"        # what the device says
    assert snap.state is SupervisorState.DEGRADED   # what the host concludes


# --- measurement, provenance, logging --------------------------------------

def test_the_measurement_carries_provenance_and_state():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HELLO,1,esp32s3-devkitc-1,ESP32-S3,14:C1:9F:26:52:EC,0.1.0,abc123")
    src._handle_line("STAT,12.5,180000,170000,OK")
    src._handle_line("HB,7,12.5")
    m = src.take_measurement()
    assert m.sensor == "supervisor"
    assert m.kind == "supervisor_status"
    assert m.frame_id == "supervisor"
    assert m.provenance.algorithm == "esp32-supervisor/v1"
    assert m.provenance.frame_index == 7
    assert m.t_sensor == pytest.approx(12.5)
    assert m.confidence is None
    assert m.value["state"] == "OK"
    assert m.value["uptime_s"] == pytest.approx(12.5)
    assert m.value["device_health"] == "OK"


def test_measurements_are_rate_limited_to_the_log_interval():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0,
                           log_interval=10.0)
    src._handle_line("HB,1,0.5")
    assert src.take_measurement() is not None
    assert src.take_measurement() is None
    assert src.take_measurement() is None


def test_the_device_heartbeat_is_distinct_from_the_network_heartbeat():
    """The two heartbeats answer different questions and must not merge."""
    from specter.net.messages import Heartbeat
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HELLO,1,b,c,mac,1.0,build")
    src._handle_line("HB,1,0.5")
    m = src.take_measurement()
    assert m.sensor == "supervisor"
    assert m.sensor != "fusion"
    assert SENSOR_LABELS["supervisor"] == "SUPERVISOR"
    # the network heartbeat is a different type in a different module
    assert Heartbeat is not None
    assert "supervisor" not in Heartbeat.__module__


# --- acquisition -----------------------------------------------------------

def test_the_simulator_drives_the_whole_path():
    with SimulatorReader(SimulatedSupervisor(rate_hz=50.0)) as reader:
        src = SupervisorSource(reader=reader, heartbeat_timeout=2.0)
        src.start()
        try:
            assert _wait(lambda: src.snapshot().identity_known)
            assert _wait(lambda: src.snapshot().heartbeat_seq >= 2)
            snap = src.snapshot()
            assert snap.state is SupervisorState.OK
            assert snap.uptime_s > 0
            m = src.take_measurement()
            assert m is not None
            assert m.provenance.sensor_id == "14:C1:9F:26:52:EC"
        finally:
            src.stop()


def test_stop_always_releases_the_port():
    reader = ScriptedReader()
    src = SupervisorSource(reader=reader)
    src.start()
    time.sleep(0.1)
    src.stop(timeout=1.0)
    assert reader.closed


def test_a_silent_device_is_reported_offline_not_hung():
    reader = ScriptedReader()          # never says anything
    src = SupervisorSource(reader=reader, stall_timeout=0.3, heartbeat_timeout=0.2)
    src.start()
    try:
        assert _wait(lambda: src.snapshot().state is SupervisorState.OFFLINE,
                     timeout=3.0)
        assert src.snapshot().identity_known is False
    finally:
        src.stop()


def test_the_status_row_reports_the_link_not_the_telemetry():
    src = SupervisorSource(reader=ScriptedReader(), heartbeat_timeout=1.0)
    src._handle_line("HELLO,1,esp32s3-devkitc-1,ESP32-S3,14:C1:9F:26:52:EC,0.1.0,abc")
    src._handle_line("HB,3,0.5")
    status = src.status()
    assert status.key == "supervisor"
    assert status.health is Health.OK
    assert "hb 3" in status.detail
    assert len(status.detail) <= 30
