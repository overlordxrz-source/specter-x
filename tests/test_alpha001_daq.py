"""Alpha 001: DI-188 -> Measurement -> HUD -> JSONL.

Fake-driver tests: no hardware, no serial port, runs in CI.

The properties that matter here are the honesty ones:
  * a channel with no source attached is never a measurement;
  * a floating channel carries no volt value at all;
  * device connectivity is reported separately from measurement validity;
  * the event log is rate limited, not written per ADC sample;
  * the HUD never blocks on the instrument.
"""
import time

import numpy as np
import pytest

from specter.events.log import EventLog
from specter.hud.renderer import HUD_H, HUD_W, HudState, render
from specter.sensors.base import Health
from specter.sensors.di188 import measure as measure_mod
from specter.sensors.di188.driver import DeviceCalibration, DI188Identity, Sample
from specter.sensors.di188.measure import AnalogSource, DeviceState
from specter.sensors.di188.stats import ChannelState, default_specs

AMBER = (40, 200, 255)     # BGR, as the HUD draws it
GREEN = (90, 255, 120)


class FakeDriver:
    """Stands in for the DI-188: deterministic frames, no serial involved."""

    def __init__(self, port=None, frames=200, values=None, device_cal=True):
        self.port = port or "/dev/fake"
        self.identity = DI188Identity(port=self.port, usb_product="Fake DI-188",
                                      usb_vid=0x2846, usb_pid=0x8037, model="188",
                                      vendor_tag="DATAQ", serial_number="FAKE0001",
                                      firmware_rev="0", hardware_rev="0",
                                      channel_count=4)
        self.device_calibration = DeviceCalibration(
            read_ok=True, scale=[[18850] * 4] * 8, offset=[[0, 0, 0, 0]] * 8,
            last_cal_date="6214F19E")
        self._frames = frames
        self._values = values or [[3.0, -2.0, 1.0, 0.0]]
        self._device_cal = device_cal
        self.started = False
        self.stopped = False

    def open(self):
        return self

    def read_identity(self):
        return self.identity

    def read_device_calibration(self):
        if not self._device_cal:
            raise RuntimeError("no flash")
        return self.device_calibration

    def configure(self, channels, rate=100.0):
        self.configured = (list(channels), rate)
        return float(rate)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.stopped = True

    def force_close(self):
        self.stopped = True

    def stream(self, max_frames=None, stall_timeout=None, cancel=None):
        i = 0
        while max_frames is None or i < max_frames:
            if self.stopped:
                return
            if cancel is not None and cancel.is_set():
                return
            yield Sample(t=i * 0.01, index=i, values=list(self._values[i % len(self._values)]),
                         host_time=time.time())
            i += 1
            time.sleep(0.001)


@pytest.fixture
def fake_device(monkeypatch):
    """Install a fake instrument and a fake port list."""
    created = {}

    def factory(port=None, **kw):
        d = FakeDriver(port=port, **kw)
        created["driver"] = d
        return d

    monkeypatch.setattr(measure_mod, "DI188Driver", factory)
    monkeypatch.setattr(measure_mod, "find_serial_ports", lambda: ["/dev/fake"])
    # discovery matches on the USB VID:PID of the DAQ
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: ["/dev/fake"])
    return created


def _wait_for(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- device connectivity vs measurement validity ---------------------------

def test_absent_device_is_reported_not_crashed(monkeypatch):
    monkeypatch.setattr(measure_mod, "find_serial_ports", lambda: [])
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: [])
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).device_state is DeviceState.ABSENT)
        snap = src.snapshot(0)
        assert snap.device_state is DeviceState.ABSENT
        assert not snap.connected
        # an absent device never produces a Measurement
        assert src.take_measurement() is None
    finally:
        src.stop()


def test_contended_port_is_reported_as_busy(monkeypatch):
    def boom(port=None, **kw):
        raise measure_mod.DI188Error(f"cannot open {port}: Resource busy")
    monkeypatch.setattr(measure_mod, "DI188Driver", boom)
    monkeypatch.setattr(measure_mod, "find_serial_ports", lambda: ["/dev/fake"])
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: ["/dev/fake"])
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).device_state is DeviceState.BUSY)
        assert src.take_measurement() is None
    finally:
        src.stop()


def test_device_health_is_separate_from_measurement_validity(fake_device):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).device_state is DeviceState.CONNECTED)
        snap = src.snapshot(0)
        status = src.status()
        # the instrument is fine ...
        assert status.health is Health.OK
        # ... but nothing is plugged into it
        assert snap.any_measurement is False
        assert all(c.state is ChannelState.UNDECLARED for c in snap.channels)
        assert "floating" in status.detail
    finally:
        src.stop()


# --- the Measurement itself ------------------------------------------------

def test_measurement_carries_provenance_state_and_calibration_basis(fake_device):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        m = src.take_measurement()
        assert m is not None
        assert m.sensor == "analog"
        assert m.kind == "analog4"
        assert m.frame_id == "daq"
        assert m.provenance.source == "analog"
        assert m.provenance.algorithm == "di188-ascii"
        assert m.provenance.sensor_id == "di188-FAKE0001"
        assert m.provenance.frame_index and m.provenance.frame_index > 0
        assert "noise" in m.provenance.notes
        # nothing is calibrated here, so no confidence is claimed
        assert m.confidence is None
        # the calibration basis travels with the value
        assert m.value["calibration_basis"] == "UNCALIBRATED (nominal)"
        assert m.value["device"]["serial"] == "FAKE0001"
        # and so does the per-channel state
        for ch in m.value["channels"]:
            assert ch["state"] == "UNDECLARED"
            assert ch["is_measurement"] is False
            assert ch["calibration_basis"] == "nominal"
    finally:
        src.stop()


def test_floating_channels_carry_no_volts(fake_device):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        m = src.take_measurement()
        for ch in m.value["channels"]:
            assert ch["volts"] is None, "a floating channel must not carry a volt value"
            assert ch["is_measurement"] is False
        assert src.snapshot(0).any_measurement is False
    finally:
        src.stop()


def test_a_connected_channel_does_carry_nominal_volts(fake_device):
    specs = default_specs(4)
    for s in specs:
        s.connected = True
        s.source = "1.5 V cell"
    src = AnalogSource(rate=100.0, specs=specs).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        m = src.take_measurement()
        for ch in m.value["channels"]:
            assert ch["is_measurement"] is True
            assert ch["volts"] is not None
            assert ch["calibration_basis"] == "nominal"
        assert src.snapshot(0).any_measurement is True
    finally:
        src.stop()


def test_logging_is_rate_limited_not_per_sample(fake_device):
    src = AnalogSource(rate=100.0, log_interval=1.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 20)
        first = src.take_measurement()
        assert first is not None
        # the next call is inside the window and must be refused
        assert src.take_measurement() is None
        assert src.take_measurement() is None
    finally:
        src.stop()


def test_series_is_bounded(fake_device):
    src = AnalogSource(rate=100.0, history=32).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 40)
        snap = src.snapshot(series_points=120)
        for ch in snap.series.values():
            assert len(ch) <= 32
    finally:
        src.stop()


def test_snapshot_does_not_block_the_caller(fake_device):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        t0 = time.perf_counter()
        for _ in range(200):
            src.snapshot()
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, "the HUD must not be held up by the DAQ"
    finally:
        src.stop()


# --- HUD -------------------------------------------------------------------

def test_hud_renders_floating_inputs_as_noise(fake_device):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        st = HudState(mode="ANALOG", analog=src.snapshot(), sensors=[src.status()])
        frame = render(np.zeros((720, 1280, 3), np.uint8), st)
        assert frame.shape == (HUD_H, HUD_W, 3)
        # the amber FLOATING / NOISE styling is on the frame
        assert (frame == np.array(AMBER, np.uint8)).all(axis=2).any()
    finally:
        src.stop()


def test_hud_draws_nothing_invented_when_the_daq_is_absent(monkeypatch):
    monkeypatch.setattr(measure_mod, "find_serial_ports", lambda: [])
    monkeypatch.setattr(measure_mod, "find_di188_ports", lambda: [])
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).device_state is DeviceState.ABSENT)
        st = HudState(mode="ANALOG", analog=src.snapshot())
        frame = render(np.zeros((720, 1280, 3), np.uint8), st)
        assert frame.shape == (HUD_H, HUD_W, 3)
    finally:
        src.stop()


def _card_region(frame):
    """The first channel card, in frame coordinates."""
    return frame[168:464, 20:495]


def _has_colour(frame, bgr):
    return (frame == np.array(bgr, np.uint8)).all(axis=2).any()


def test_hud_draws_a_connected_channel_as_a_measurement(fake_device):
    """The connected case must look different from the floating case."""
    specs = default_specs(4)
    for s in specs:
        s.connected = True
        s.source = "1.5 V cell"
    src = AnalogSource(rate=100.0, specs=specs).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        snap = src.snapshot()
        assert snap.any_measurement is True
        for ch in snap.channels:
            assert ch.volts is not None
        st = HudState(mode="ANALOG", analog=snap, sensors=[src.status()])
        frame = render(np.zeros((720, 1280, 3), np.uint8), st)
        assert frame.shape == (HUD_H, HUD_W, 3)
        card = _card_region(frame)
        assert _has_colour(card, GREEN), "a CONNECTED channel must be drawn in the healthy colour"
        # the calibration badge elsewhere on the frame is legitimately amber
        # (the volts are nominal), but the channel card itself must not be
        assert not _has_colour(card, AMBER), "a CONNECTED channel must not carry the floating styling"
    finally:
        src.stop()


def test_hud_draws_a_floating_channel_with_the_floating_styling(fake_device):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        st = HudState(mode="ANALOG", analog=src.snapshot(), sensors=[src.status()])
        frame = render(np.zeros((720, 1280, 3), np.uint8), st)
        card = _card_region(frame)
        assert _has_colour(card, AMBER), "a floating channel must be badged FLOATING / NOISE"
        assert not _has_colour(card, GREEN)
    finally:
        src.stop()


def test_volts_are_withheld_from_an_unconnected_channel(fake_device):
    """The rule lives in the stats layer, so every consumer inherits it."""
    specs = default_specs(4)
    specs[0].connected = True
    specs[1].connected = False
    src = AnalogSource(rate=100.0, specs=specs).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        snap = src.snapshot()
        by_index = {c.index: c for c in snap.channels}
        assert by_index[0].volts is not None
        assert by_index[1].volts is None
        assert by_index[1].state is ChannelState.FLOATING
    finally:
        src.stop()


# --- event log -------------------------------------------------------------

def test_event_log_round_trips_an_analog_measurement(fake_device, tmp_path):
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).frames > 5)
        log = EventLog(tmp_path)
        log.log("session_start", {"sensors": {"analog": "OK"}})
        m = src.take_measurement()
        log.log("analog_sample", {"channels": m.value["frames"]}, measurement=m)
        log.close()
        lines = (tmp_path / f"{log.session}.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2
        assert '"source": "analog"' in lines[1] or '"source":"analog"' in lines[1]
        assert "di188-FAKE0001" in lines[1]
        assert '"confidence": null' in lines[1] or '"confidence":null' in lines[1]
    finally:
        src.stop()
