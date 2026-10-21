"""Alpha 002-B: the single ESP32 reader, end to end.

Covers the failure modes the hardware actually shows:

* the USB device disappearing (a reset re-enumerates it);
* a stream that goes quiet;
* malformed lines and truncated records;
* several record types interleaved on one link;
* a bounded queue that must not let the reader block or grow without limit.

No hardware is needed: the reader is driven through an injected fake port.
"""
import time

import pytest

from specter.sensors.esp32 import reader as reader_mod
from specter.sensors.esp32.csi import (csi_summary_measurement,
                                        subcarrier_amplitudes)
from specter.sensors.esp32.reader import Esp32SerialReader, LinkState


class FakePort:
    """A pyserial-shaped port that can be fed, wedged or unplugged."""

    def __init__(self, port="/dev/fake", fail_on_read=False):
        self.port = port
        self.buf = bytearray()
        self.closed = False
        self.fail_on_read = fail_on_read
        self.reads = 0

    @property
    def in_waiting(self):
        if self.fail_on_read:
            raise OSError("Device not configured")
        return len(self.buf)

    def read(self, size=1):
        self.reads += 1
        if self.fail_on_read:
            raise OSError("Device not configured")
        out = bytes(self.buf[:size])
        del self.buf[:size]
        return out

    def write(self, data):
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True

    def feed(self, text):
        self.buf += text.encode()


def csi(seq, iq="0,0,-3,-5"):
    return (f"CSI_DATA,{seq},b8:62:1f:e5:ac:62,-60,9,0,0,0,0,0,0,0,0,0,-90,0,11,0,"
            f"67768165,0,109,0,128,0,\"[{iq}]\"\r\n")


HELLO = "HELLO,1,esp32s3-devkitc-1,ESP32-S3,14:C1:9F:26:52:EC,0.1.0,abc\r\n"
STAT = "STAT,123.456,180000,170000,OK\r\n"
HB = "HB,42,123.456\r\n"


@pytest.fixture
def wired(monkeypatch):
    """A reader wired to a fake port, with the USB lookup faked out."""
    port = FakePort()
    ids = {"/dev/fake": {"product": "USB JTAG_serial debug unit", "vendor": "Espressif",
                          "vid": 0x303A, "pid": 0x1001, "serial": "14:C1:9F:26:52:EC"}}
    monkeypatch.setattr(reader_mod, "find_usb_serial_ports",
                        lambda vid=None, pid=None: ["/dev/fake"])
    monkeypatch.setattr("specter.hw.usb.serial_port_usb_ids", lambda: ids)
    monkeypatch.setattr("serial.Serial", lambda *a, **k: port)
    return port


def _wait(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- a single reader, many record types -----------------------------------

def test_one_reader_carries_every_record_type(wired):
    r = Esp32SerialReader(reconnect=False, stall_timeout=1.0).start()
    try:
        wired.feed(HELLO + csi(1) + STAT + csi(2) + HB)
        assert _wait(lambda: r.health().packets >= 2)
        records = r.drain_csi()
        assert [x.seq for x in records] == [1, 2]
        view = r.supervisor_view()
        assert view["available"] is True
        assert view["identity"]["mac"] == "14:C1:9F:26:52:EC"
        assert view["heartbeat_seq"] == 42
    finally:
        r.stop()


def test_the_supervisor_is_unavailable_until_the_firmware_emits_it(wired):
    """A real link with no supervisor packets must not look healthy."""
    r = Esp32SerialReader(reconnect=False).start()
    try:
        wired.feed(csi(1) + csi(2))
        assert _wait(lambda: r.health().packets >= 2)
        view = r.supervisor_view()
        assert view["available"] is False
        assert view["state"] == "UNAVAILABLE"
        assert "does not emit" in view["detail"]
        assert view["heartbeat_seq"] == 0
    finally:
        r.stop()


# --- disconnects -----------------------------------------------------------

def test_a_usb_disconnect_is_reported_not_hidden(wired):
    r = Esp32SerialReader(reconnect=False, stall_timeout=1.0).start()
    try:
        wired.feed(csi(1))
        assert _wait(lambda: r.health().packets >= 1)
        wired.fail_on_read = True
        assert _wait(lambda: r.health().state is LinkState.DISCONNECTED, 5.0)
        assert "went away" in r.health().detail
    finally:
        r.stop()


def test_the_reader_reconnects_and_counts_it(wired, monkeypatch):
    ports = []

    def factory(*a, **k):
        p = FakePort()
        ports.append(p)
        return p

    monkeypatch.setattr("serial.Serial", factory)
    r = Esp32SerialReader(reconnect=True, reconnect_delay=0.05,
                           stall_timeout=1.0).start()
    try:
        assert _wait(lambda: len(ports) >= 1, 5.0)
        ports[0].fail_on_read = True
        assert _wait(lambda: r.health().reconnects >= 1, 5.0)
        assert _wait(lambda: len(ports) >= 2, 5.0), "a new port should have been opened"
    finally:
        r.stop()


# --- stalled streams -------------------------------------------------------

def test_a_stalled_stream_is_reported_after_the_grace(wired):
    r = Esp32SerialReader(reconnect=False, stall_timeout=0.4,
                           startup_grace=0.0).start()
    try:
        wired.feed(csi(1))
        assert _wait(lambda: r.health().packets >= 1)
        assert _wait(lambda: r.health().state is LinkState.STALLED, 5.0)
        assert "no data" in r.health().detail
    finally:
        r.stop()


def test_silence_during_startup_is_not_called_a_stall(wired):
    r = Esp32SerialReader(reconnect=False, stall_timeout=0.2,
                           startup_grace=30.0).start()
    try:
        time.sleep(0.8)
        assert r.health().state is LinkState.CONNECTING
        assert "waiting" in r.health().detail
    finally:
        r.stop()


# --- malformed data --------------------------------------------------------

def test_malformed_records_are_counted_and_do_not_stop_the_stream(wired):
    r = Esp32SerialReader(reconnect=False).start()
    try:
        wired.feed("CSI_DATA,notanumber,mac,-60,9\r\n"
                   "garbage line\r\n"
                   "CSI_DATA,1,mac,-60,9,0,0,0,0,0,0,0,0,0,-90,0,11,0,1,0,109,0,128,0\r\n")
        assert _wait(lambda: r.health().packets >= 1)
        h = r.health()
        assert h.malformed >= 1
        assert h.unknown_lines >= 1
        assert h.packets == 1
    finally:
        r.stop()


def test_a_record_split_across_reads_is_reassembled(wired):
    r = Esp32SerialReader(reconnect=False).start()
    try:
        whole = csi(1)
        wired.feed(whole[:40])
        time.sleep(0.2)
        wired.feed(whole[40:])
        assert _wait(lambda: r.health().packets >= 1)
        assert r.health().malformed == 0
    finally:
        r.stop()


def test_a_truncated_record_does_not_crash_the_reader(wired):
    r = Esp32SerialReader(reconnect=False).start()
    try:
        wired.feed("CSI_DATA,1,mac,-60,9,0,0,0\r\n")
        time.sleep(0.2)
        wired.feed(csi(2))
        assert _wait(lambda: r.health().packets >= 1)
        h = r.health()
        assert h.malformed == 1, "the short record is counted as malformed"
        assert h.packets == 1, "the good record still arrives"
    finally:
        r.stop()


# --- bounded queues --------------------------------------------------------

def test_a_slow_consumer_does_not_grow_the_queue(wired):
    r = Esp32SerialReader(reconnect=False, csi_capacity=64).start()
    try:
        for i in range(500):
            wired.feed(csi(i + 1))
        assert _wait(lambda: r.health().packets >= 500, 5.0)
        h = r.health()
        assert h.packets == 500
        assert h.dropped > 0, "the bounded queue should have dropped records"
        assert len(r.drain_csi()) <= 64
    finally:
        r.stop()


# --- shutdown --------------------------------------------------------------

def test_stop_releases_the_port(wired):
    r = Esp32SerialReader(reconnect=False).start()
    wired.feed(csi(1))
    assert _wait(lambda: r.health().packets >= 1)
    r.stop()
    assert wired.closed
    assert r._thread is None


def test_stop_is_safe_when_the_device_is_already_gone(wired):
    r = Esp32SerialReader(reconnect=False, stall_timeout=1.0).start()
    wired.fail_on_read = True
    time.sleep(0.2)
    r.stop()
    assert wired.closed


# --- the measurement --------------------------------------------------------

def test_the_measurement_carries_the_counters_and_the_device_clock(wired):
    r = Esp32SerialReader(reconnect=False).start()
    try:
        wired.feed(csi(7))
        assert _wait(lambda: r.health().packets >= 1)
        rec = r.drain_csi()[0]
        h = r.health()
        m = csi_summary_measurement(rec, h, h.board_mac, packets=1,
                                    first_id=7, gaps=0, missing=0, malformed=0,
                                    dropped=0, unknown_lines=0)
        assert m.sensor == "wifi_csi"
        assert m.kind == "csi_summary"
        assert m.frame_id == "csi"
        assert m.provenance.source == "wifi_csi"
        assert m.provenance.algorithm == "csi_recv_router"
        assert m.provenance.sensor_id == "14:C1:9F:26:52:EC"
        assert m.provenance.frame_index == 7
        # the device's own clock, in seconds
        assert m.t_sensor == pytest.approx(67768165 / 1e6)
        assert m.confidence is None
        v = m.value
        assert v["id"] == 7
        assert v["ap_mac"] == "b8:62:1f:e5:ac:62"
        assert v["rssi"] == -60
        assert v["channel"] == 11
        assert v["local_timestamp"] == 67768165
        assert v["subcarriers"] == 2
        assert v["packets"] == 1
        assert v["link_state"] == "CONNECTED"
    finally:
        r.stop()


def test_subcarrier_amplitudes_are_magnitudes():
    amps = subcarrier_amplitudes([3, 4, 0, 5, 6])
    assert amps[0] == pytest.approx(5.0)
    assert amps[1] == pytest.approx(5.0)
    assert len(amps) == 2, "an odd trailing sample is not paired"
