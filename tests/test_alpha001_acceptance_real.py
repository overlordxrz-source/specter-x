"""Alpha 001 acceptance test: the real DI-188, end to end.

Runs only when a DI-188 is actually attached. It exercises the whole path -
instrument -> Measurement -> JSONL -> HUD frame - and writes the evidence to
``docs/alpha001/`` (override with ``SPECTER_ALPHA001_OUT``).

It asserts the honesty rules, not just that bytes moved: the instrument must
be connected, and every channel must still be reported as unmeasured,
because nothing is plugged into the inputs.
"""
import os
import time

import numpy as np
import pytest

from specter.events.log import EventLog
from specter.hud.renderer import HudState, render
from specter.sensors.di188.driver import find_di188_ports
from specter.sensors.di188.measure import AnalogSource, DeviceState
from specter.sensors.di188.stats import ChannelState

try:
    import serial  # noqa: F401
    HAVE_PYSERIAL = True
except ImportError:
    HAVE_PYSERIAL = False

OUT = os.environ.get("SPECTER_ALPHA001_OUT", "docs/alpha001")
RUNTIME_S = float(os.environ.get("SPECTER_ALPHA001_SECONDS", "6"))

pytestmark = pytest.mark.skipif(
    not HAVE_PYSERIAL or not find_di188_ports(),
    reason="no DI-188 attached (needs the real instrument and pyserial)")


def _wait_for(predicate, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_real_di188_end_to_end():
    src = AnalogSource(rate=100.0).start()
    try:
        assert _wait_for(lambda: src.snapshot(0).device_state is DeviceState.CONNECTED), \
            f"instrument did not connect: {src.snapshot(0).device_detail}"
        snap = src.snapshot(0)
        assert snap.connected
        assert snap.model and "DI-188" in snap.model
        assert snap.serial
        assert snap.rate_hz > 0

        # let it stream
        assert _wait_for(lambda: src.snapshot(0).frames > 50, timeout=15.0)
        snap = src.snapshot()
        assert snap.frames > 50

        # a real Measurement, rate limited
        m = src.take_measurement()
        assert m is not None
        assert m.provenance.source == "analog"
        assert m.provenance.algorithm == "di188-ascii"
        assert m.provenance.sensor_id.startswith("di188-")
        assert m.confidence is None
        assert m.value["calibration_basis"] == "UNCALIBRATED (nominal)"

        # nothing is plugged in, so nothing is a measurement
        for ch in m.value["channels"]:
            assert ch["state"] in (ChannelState.UNDECLARED.value,
                                    ChannelState.FLOATING.value)
            assert ch["is_measurement"] is False
            assert ch["volts"] is None
        assert snap.any_measurement is False

        # device connectivity is reported separately and is healthy
        status = src.status()
        assert status.health.value == "OK"
        assert "floating" in status.detail

        # --- artefacts ------------------------------------------------------
        os.makedirs(OUT, exist_ok=True)
        log = EventLog(OUT)
        log.log("session_start", {
            "sensors": {"analog": status.health.value},
            "instrument": snap.model,
            "serial": snap.serial,
            "port": snap.port,
            "calibration_basis": snap.calibration_basis,
            "frames": snap.frames,
        })
        log.log("analog_sample", {"frames": snap.frames}, measurement=m)
        log.close()
        # stable filename: re-running the acceptance test overwrites its
        # evidence instead of littering the repo with timestamped copies
        session_path = os.path.join(OUT, "alpha001_acceptance_session.jsonl")
        os.replace(os.path.join(OUT, f"{log.session}.jsonl"), session_path)
        assert os.path.exists(session_path)
        body = open(session_path).read()
        assert '"source": "analog"' in body or '"source":"analog"' in body
        assert snap.serial in body

        st = HudState(mode="ANALOG", analog=snap, sensors=[status])
        frame = render(np.zeros((720, 1280, 3), np.uint8), st)
        png_path = os.path.join(OUT, "alpha001_hud.png")
        assert cv2_write(png_path, frame)

        print(f"\n  acceptance OK: {snap.frames} frames, "
              f"{snap.rate_hz:g} Hz, serial {snap.serial}")
        print(f"  session log -> {session_path}")
        print(f"  HUD frame   -> {png_path}")
    finally:
        src.stop()


def cv2_write(path, frame):
    import cv2
    return bool(cv2.imwrite(path, frame))
