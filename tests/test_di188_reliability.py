"""Regression tests for the DI-188 acquisition shutdown path.

These cover the failure modes behind the reported lockup:

* the instrument stops sending bytes  -> the stream must not hang forever
* a shutdown is requested while the instrument is silent -> the port must
  still be released
* another serial device (an ESP32, a GPS) is on the bus -> discovery must
  not select it

No hardware is needed: the fake serial port reproduces the silence.
"""
import threading
import time

import pytest

from specter.sensors.di188 import measure as measure_mod
from specter.sensors.di188.driver import (DI188Driver, DI188Error, find_di188_ports,
                                          find_serial_ports, probe_di188_port,
                                          serial_port_usb_ids)
from specter.sensors.di188.measure import AnalogSource, DeviceState


class _SerialShim:
    """Stands in for the pyserial module (the driver uses serial.Serial)."""

    def __init__(self, cls):
        self.Serial = cls


class SilentSerial:
    """A port that opens, answers nothing, and never sends a byte."""

    def __init__(self, port=None, **kw):
        self.port = port or "/dev/fake"
        self.timeout = 1.0
        self.baudrate = 0
        self.closed = False

    @property
    def in_waiting(self):
        return 0

    def read(self, size=1):
        return b""

    def write(self, data):
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True


class Answering(SilentSerial):
    """Echoes the command and answers it like a DI-188 would."""

    def __init__(self, port=None, **kw):
        super().__init__(port)
        self.buf = bytearray()

    @property
    def in_waiting(self):
        return len(self.buf)

    def read(self, size=1):
        out = bytes(self.buf[:size])
        del self.buf[:size]
        return out

    def write(self, data):
        self.buf += b"info 1 188\r\n"
        return len(data)


def _make_driver(monkeypatch, serial_cls=SilentSerial):
    made = {}

    def factory(port=None, **kw):
        d = DI188Driver(port or "/dev/fake", timeout=kw.get("timeout", 1.0))
        d.ser = serial_cls(port, **kw)
        made["driver"] = d
        return d

    monkeypatch.setattr("specter.sensors.di188.driver.serial", _SerialShim(serial_cls))
    return factory, made


# --- the stream must be bounded -------------------------------------------

def test_stream_raises_when_the_instrument_goes_silent(monkeypatch):
    factory, made = _make_driver(monkeypatch)
    dev = factory()
    with pytest.raises(DI188Error) as exc:
        next(dev.stream(stall_timeout=0.2))
    assert "silent" in str(exc.value).lower()


def test_stream_returns_promptly_when_cancelled(monkeypatch):
    """A shutdown request must be honoured even with no data at all."""
    factory, made = _make_driver(monkeypatch)
    dev = factory()
    cancel = threading.Event()
    cancel.set()
    t0 = time.time()
    frames = list(dev.stream(stall_timeout=60.0, cancel=cancel))
    assert frames == []
    assert time.time() - t0 < 1.0


def test_stream_checks_cancellation_even_while_data_flows(monkeypatch):
    factory, made = _make_driver(monkeypatch)
    dev = factory()
    cancel = threading.Event()
    cancel.set()
    assert list(dev.stream(stall_timeout=60.0, cancel=cancel)) == []


# --- shutdown must always release the port ---------------------------------

def test_stop_releases_the_port_even_when_the_device_is_silent(monkeypatch):
    """The regression: a silent instrument must not hold the port open."""
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr(measure_mod, "find_serial_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr("specter.sensors.di188.driver.serial", _SerialShim(SilentSerial))
    opened = {}

    class FakeDriver(SilentSerial):
        def open(self):
            opened["driver"] = self
            return self

        def read_identity(self):
            raise DI188Error("no reply")

        def close(self):
            self.closed = True

        def force_close(self):
            self.closed = True

        def stream(self, max_frames=None, stall_timeout=None, cancel=None):
            # a device that has gone quiet: nothing arrives, ever
            while cancel is None or not cancel.is_set():
                time.sleep(0.01)
            return

    monkeypatch.setattr(measure_mod, "DI188Driver",
                        lambda port=None, **kw: FakeDriver(port))
    src = AnalogSource(rate=100.0, stall_timeout=30.0)
    src.start()
    time.sleep(0.3)
    src.stop(timeout=1.0)
    assert src._thread is None, "the acquisition thread must be gone"
    assert opened["driver"].closed, "the serial port must have been released"


def test_adapter_reports_a_silent_instrument_as_silent(monkeypatch):
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr(measure_mod, "find_serial_ports", lambda: ["/dev/fake"])

    class SilentStreamDriver(SilentSerial):
        def open(self):
            return self

        def read_identity(self):
            from specter.sensors.di188.driver import DI188Identity
            return DI188Identity(port="/dev/fake", model="188", serial_number="X")

        def read_device_calibration(self):
            raise DI188Error("nope")

        def configure(self, channels, rate=100.0):
            return float(rate)

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            self.closed = True

        def force_close(self):
            self.closed = True

        def stream(self, max_frames=None, stall_timeout=None, cancel=None):
            raise DI188Error("no data for 5.0s (instrument is silent)")

    monkeypatch.setattr(measure_mod, "DI188Driver",
                        lambda port=None, **kw: SilentStreamDriver(port))
    src = AnalogSource(rate=100.0).start()
    try:
        end = time.time() + 5.0
        while time.time() < end:
            if src.snapshot(0).device_state is DeviceState.SILENT:
                break
            time.sleep(0.02)
        assert src.snapshot(0).device_state is DeviceState.SILENT
    finally:
        src.stop()


# --- discovery must not grab the wrong device ------------------------------

def test_discovery_matches_on_the_usb_vid_pid(monkeypatch):
    """Only a node whose USB identity is the DAQ may be selected."""
    ids = {
        "/dev/cu.usbmodem1101": {"product": "USB JTAG_serial debug unit",
                                 "vendor": "Espressif", "vid": 0x303A, "pid": 0x1001,
                                 "serial": "14:C1:9F:26:52:EC"},
        "/dev/cu.usbmodem5B901602281": {"product": "USB Single Serial",
                                        "vendor": "WCH", "vid": 0x1A86, "pid": 0x55D3,
                                        "serial": "5B90160228"},
        "/dev/cu.usbmodem101": {"product": "Seeed XIAO M0", "vendor": "Seeed",
                                "vid": 0x2846, "pid": 0x8037,
                                "serial": "022581D650555233362E3120FF081935"},
    }
    monkeypatch.setattr("specter.sensors.di188.driver.serial_port_usb_ids",
                        lambda: ids)
    matched = find_di188_ports()
    assert matched == ["/dev/cu.usbmodem101"]
    # the ESP32 and the UART bridge are not candidates
    assert "/dev/cu.usbmodem1101" not in matched
    assert "/dev/cu.usbmodem5B901602281" not in matched


def test_adapter_does_not_open_a_foreign_device(monkeypatch):
    """With no VID:PID match, nothing may be opened at all."""
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: [])
    monkeypatch.setattr(measure_mod, "find_serial_ports",
                        lambda: ["/dev/cu.usbmodem1101"])   # the ESP32
    opened = []

    class NeverOpen:
        def __init__(self, port=None, **kw):
            opened.append(port)

    monkeypatch.setattr(measure_mod, "DI188Driver", NeverOpen)
    src = AnalogSource(rate=100.0).start()
    try:
        end = time.time() + 2.0
        while time.time() < end:
            if src.snapshot(0).device_state is DeviceState.ABSENT:
                break
            time.sleep(0.02)
        assert opened == [], "a foreign device must never be opened"
        assert src.snapshot(0).device_state is DeviceState.ABSENT
    finally:
        src.stop()


def test_probe_rejects_a_device_that_does_not_answer(monkeypatch):
    """The read-only probe only accepts a node that reports a model number."""
    monkeypatch.setattr("specter.sensors.di188.driver.serial", _SerialShim(SilentSerial))
    assert probe_di188_port("/dev/fake") is None


def test_probe_accepts_a_device_that_reports_a_model(monkeypatch):
    monkeypatch.setattr("specter.sensors.di188.driver.serial", _SerialShim(Answering))
    info = probe_di188_port("/dev/fake")
    assert info is not None
    assert info["model"] == "188"
    assert info["model_name"] == "DI-188"


def test_find_serial_ports_excludes_system_ports(monkeypatch):
    monkeypatch.setattr("specter.sensors.di188.driver.glob.glob",
                        lambda pattern: {
                            "/dev/cu.usbmodem*": ["/dev/cu.usbmodem101"],
                            "/dev/cu.usbserial*": [],
                            "/dev/cu.SLAB_USBtoUART*": [],
                            "/dev/cu.usb-FTDI*": [],
                            "/dev/cu.wchusbserial*": [],
                            "/dev/tty.usbmodem*": ["/dev/tty.usbmodem101"],
                            "/dev/ttyACM*": [],
                            "/dev/ttyUSB*": [],
                            "/dev/serial/by-id/*": [],
                        }.get(pattern, []))
    ports = find_serial_ports()
    assert "/dev/cu.usbmodem101" in ports
    assert not any("Bluetooth" in p for p in ports)
    assert not any("debug-console" in p for p in ports)
