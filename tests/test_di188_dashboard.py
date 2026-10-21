"""DI-188 dashboard: HTTP API, recording control and the honesty labels.

Runs the dashboard against a stub instrument so no hardware is needed.
"""
import json
import os
import urllib.request

import pytest

from specter.sensors.di188.calibration import CalibrationSet
from specter.sensors.di188.dashboard import Di188Dashboard
from specter.sensors.di188.driver import DI188Identity, DeviceCalibration, Sample
from specter.sensors.di188.stats import default_specs


class StubDriver:
    """Stands in for the DI-188: deterministic frames, no serial involved."""

    def __init__(self, n_channels=4, frames=500):
        self.identity = DI188Identity(port="/dev/stub", usb_product="Stub DI-188",
                                      usb_vid=0x2846, usb_pid=0x8037, model="188",
                                      vendor_tag="DATAQ", serial_number="STUB0001",
                                      firmware_rev="0", hardware_rev="0",
                                      channel_count=n_channels)
        self.device_calibration = DeviceCalibration(read_ok=True, scale=[[18850] * 4] * 8,
                                                     offset=[[0, 0, 0, 0]] * 8,
                                                     last_cal_date="6214F19E")
        self.malformed_lines = 0
        self.n_channels = n_channels
        self.frames = frames
        self._stopped = False

    def configure(self, channels, rate=100.0):
        return float(rate)

    def start(self):
        self._stopped = False

    def stop(self):
        self._stopped = True

    def stream(self, max_frames=None, stall_timeout=None):
        import time
        for i in range(self.frames):
            if self._stopped:
                return
            values = [(i * 7 + c * 13) % 41 - 20 for c in range(self.n_channels)]
            yield Sample(t=i * 0.002, index=i, values=values, host_time=time.time())
            time.sleep(0.002)


@pytest.fixture
def dashboard(tmp_path):
    driver = StubDriver()
    cal = CalibrationSet.nominal("di188_pm10v", [0, 1, 2, 3],
                                 device_serial="STUB0001", device_model="DI-188")
    dash = Di188Dashboard(driver, default_specs(4), cal, [0, 1, 2, 3], rate=500)
    dash.start()
    url = dash.serve(port=0)
    yield dash, url
    dash.shutdown()


def get_json(url, path):
    with urllib.request.urlopen(url + path, timeout=5) as resp:
        return json.loads(resp.read().decode())


def post_json(url, path, payload):
    req = urllib.request.Request(url + path, method="POST",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def test_state_endpoint_reports_identity_and_floating_inputs(dashboard):
    dash, url = dashboard
    state = get_json(url, "/api/state")
    assert state["device"]["model_name"] == "DI-188"
    assert state["device"]["serial_number"] == "STUB0001"
    assert len(state["channels"]) == 4
    # nothing was declared connected -> every channel is not a measurement
    assert all(not ch["is_measurement"] for ch in state["channels"])
    assert all(ch["state"] == "UNDECLARED" for ch in state["channels"])
    assert state["all_floating"] is True
    assert state["calibration"]["basis_label"] == "UNCALIBRATED (nominal)"


def test_link_health_and_rate_are_reported(dashboard):
    dash, url = dashboard
    state = get_json(url, "/api/state")
    assert state["rate"]["realised"] == 500
    assert state["rate"]["achieved"] > 0
    assert state["link"]["frames_received"] > 0
    assert state["link"]["ok"] is True


def test_series_are_exposed_for_plotting(dashboard):
    dash, url = dashboard
    state = get_json(url, "/api/state")
    series = state["series"]["0"]
    assert len(series) > 0
    assert series[0][1] is not None          # counts
    assert series[0][2] is not None          # volts


def test_recording_can_be_started_and_exported(dashboard, tmp_path):
    dash, url = dashboard
    out = os.path.join(tmp_path, "rec.csv")
    post_json(url, "/api/record", {"action": "start_record", "path": out})
    state = get_json(url, "/api/state")
    assert state["recording"]["active"] is True
    assert state["recording"]["path"] == out

    import time
    time.sleep(0.2)

    post_json(url, "/api/record", {"action": "stop_record"})
    state = get_json(url, "/api/state")
    assert state["recording"]["active"] is False

    with urllib.request.urlopen(url + "/api/export.csv", timeout=5) as resp:
        text = resp.read().decode()
    assert "# SPECTER-X DI-188 acquisition" in text
    assert "# channel_state ch0" in text
    assert "ch0_volts" in text
    assert len(text.splitlines()) > 3


def test_index_page_serves_the_dashboard(dashboard):
    dash, url = dashboard
    with urllib.request.urlopen(url + "/", timeout=5) as resp:
        html = resp.read().decode()
    assert "SPECTER-X" in html
    assert "FLOATING" in html
