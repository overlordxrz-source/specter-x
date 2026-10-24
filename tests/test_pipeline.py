"""Headless smoke test of the full Stage 1 pipeline + sensor helper parsers."""
import json
import struct

import numpy as np

from specter.app import main
from specter.sensors.radar.tlv import HEADER_FMT, MAGIC, parse_frame
from specter.sensors.thermal.tc001 import split_frame, thermal_to_celsius


def test_headless_synthetic_run(tmp_path):
    out_png = tmp_path / "hud.png"
    rc = main(["--source", "synthetic", "--pose", "synthetic", "--frames", "60", "--headless",
               "--log-dir", str(tmp_path), "--save-frame", str(out_png)])
    assert rc == 0
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    recs = [json.loads(l) for l in files[0].read_text().splitlines()]
    events = [r["event"] for r in recs]
    assert events[0] == "session_start" and events[-1] == "session_end"
    assert "pose_acquired" in events and "pose_lost" in events
    acq = next(r for r in recs if r["event"] == "pose_acquired")
    prov = acq["measurement"]["provenance"]
    assert acq["measurement"]["sensor"] == "synthetic"
    assert prov["sensor_id"] == "synthetic-0" and prov["frame_index"] > 0
    assert out_png.exists()
    import cv2
    assert cv2.imread(str(out_png)).shape == (800, 1280, 3)


def test_tc001_split_and_convert():
    raw = np.zeros((384, 256, 2), np.uint8)
    word = int(round((25.0 + 273.15) * 64))
    raw[192:, :, 0], raw[192:, :, 1] = word & 0xFF, word >> 8
    img, th = split_frame(raw)
    assert img.shape == th.shape == (192, 256, 2)
    np.testing.assert_allclose(thermal_to_celsius(th), 25.0, atol=0.02)


def test_radar_tlv_parse():
    pts = np.array([[1, 2, 0.5, -0.1], [0.2, 3, 0, 0.4]], "<f4")
    tlv = struct.pack("<2I", 1, pts.nbytes) + pts.tobytes()
    body = tlv + b"\x00" * ((32 - (struct.calcsize(HEADER_FMT) + len(tlv)) % 32) % 32)
    total = struct.calcsize(HEADER_FMT) + len(body)
    hdr = struct.pack(HEADER_FMT, MAGIC, 0x03060000, total, 0x6843, 7, 0, 2, 1, 0)
    h, p = parse_frame(hdr + body)
    assert h.frame_number == 7 and h.num_detected == 2
    np.testing.assert_allclose(p, pts)
