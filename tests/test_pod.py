"""POD mode: rendering, honesty labels, tracking, zoom and polarity."""
import numpy as np

from specter.app import main
from specter.hud.pod import PodState, PodTelemetry, agc, digital_zoom, hottest_blob, render_pod


def _scene(hot_xy=(400, 300)):
    img = np.full((720, 1280), 60, np.uint8)
    img += np.random.default_rng(0).integers(0, 10, img.shape, dtype=np.uint8)
    x, y = hot_xy
    img[y:y + 120, x:x + 50] = 230
    return img


def test_hottest_blob_finds_target():
    box, score = hottest_blob(agc(_scene().astype(np.float32)))
    assert box is not None and score > 0.3
    x, y, w, h = box
    assert 380 <= x <= 420 and 280 <= y <= 320


def test_render_shapes_and_track():
    st = PodState()
    for _ in range(5):
        out = render_pod(_scene(), st)
    assert out.shape == (800, 1280, 3)
    assert st._track is not None and st._track_conf > 0


def test_missing_telemetry_never_invented_and_sim_label():
    st = PodState()
    assert not st.thermal_is_real and "SIM" in st.sensor_label
    tel = PodTelemetry()
    assert all(v is None for v in vars(tel).values())
    render_pod(_scene(), st, tel)  # must not raise with every value missing


def test_zoom_and_polarity():
    img = _scene()
    z = digital_zoom(img, 4)
    assert z.shape == img.shape
    st = PodState()
    a = render_pod(img, st)[400, 425].mean()      # centre of the hot target (letterbox oy=40)
    st.toggle_polarity()
    st._acc = None
    b = render_pod(img, st)[400, 425].mean()
    assert st.polarity == "BLK" and a > 200 and b < 55  # white-hot -> black-hot
    st.cycle_zoom(); assert st.zoom == 2


def test_headless_pod_run(tmp_path):
    png = tmp_path / "pod.png"
    rc = main(["--source", "synthetic", "--pose", "synthetic", "--frames", "30", "--headless",
               "--mode", "POD", "--zoom", "2", "--log-dir", str(tmp_path), "--save-frame", str(png)])
    assert rc == 0 and png.exists()
