"""Night-vision camera sources: Arducam IMX462 via Picamera2, OpenCV, or synthetic.

All sources return `Frame` objects (BGR uint8 image + timestamps + index) so
downstream code never cares where pixels came from, but provenance does.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Frame:
    image: np.ndarray              # BGR uint8, HxWx3
    t_host: float                  # time.time() at capture
    t_sensor: Optional[float]      # sensor timestamp in seconds, if provided
    index: int
    source: str                    # provenance key: "nightvision" or "synthetic"
    sensor_id: str
    meta: dict = field(default_factory=dict)


class CameraSource:
    source = "nightvision"
    sensor_id = "camera"
    name = "camera"

    def read(self) -> Optional[Frame]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class PicameraSource(CameraSource):
    """Arducam IMX462 (or any libcamera sensor) through Picamera2."""

    name = "picamera2"
    sensor_id = "imx462-0"

    def __init__(self, width: int = 1920, height: int = 1080, fps: float = 30.0) -> None:
        from picamera2 import Picamera2  # raises ImportError off-Pi

        self.cam = Picamera2()
        if not self.cam.camera_properties:
            raise RuntimeError("Picamera2 found no camera")
        model = self.cam.camera_properties.get("Model", "unknown")
        self.sensor_id = f"{model}-0"
        cfg = self.cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameRate": fps},
            buffer_count=4,
        )
        self.cam.configure(cfg)
        self.cam.start()
        self._i = 0
        log.info("Picamera2 started: %s %dx%d@%.0f", model, width, height, fps)

    def read(self) -> Optional[Frame]:
        req = self.cam.capture_request()
        try:
            # Picamera2 "RGB888" is BGR byte order in memory -> directly usable by OpenCV.
            img = req.make_array("main")
            md = req.get_metadata()
        finally:
            req.release()
        t_host = time.time()
        ts_ns = md.get("SensorTimestamp")
        self._i += 1
        return Frame(
            image=np.ascontiguousarray(img[:, :, :3]),
            t_host=t_host,
            t_sensor=ts_ns / 1e9 if ts_ns else None,
            index=self._i,
            source=self.source,
            sensor_id=self.sensor_id,
            meta={k: md.get(k) for k in ("ExposureTime", "AnalogueGain", "Lux") if k in md},
        )

    def close(self) -> None:
        try:
            self.cam.stop()
            self.cam.close()
        except Exception:  # pragma: no cover
            pass


class OpenCVSource(CameraSource):
    name = "opencv"

    def __init__(self, device: int = 0, width: int = 1280, height: int = 720) -> None:
        self.cap = cv2.VideoCapture(device)
        if not self.cap.isOpened():
            raise RuntimeError(f"OpenCV could not open camera {device}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        ok, _ = self.cap.read()
        if not ok:
            self.cap.release()
            raise RuntimeError(f"OpenCV camera {device} opened but returned no frame")
        self.sensor_id = f"uvc-{device}"
        self._i = 0

    def read(self) -> Optional[Frame]:
        ok, img = self.cap.read()
        if not ok:
            return None
        self._i += 1
        pos = self.cap.get(cv2.CAP_PROP_POS_MSEC)
        return Frame(img, time.time(), pos / 1000.0 if pos > 0 else None, self._i,
                     self.source, self.sensor_id)

    def close(self) -> None:
        self.cap.release()


# COCO-17 keypoint order used by YOLO pose models.
COCO_KEYPOINTS = [
    "nose", "l_eye", "r_eye", "l_ear", "r_ear", "l_shoulder", "r_shoulder",
    "l_elbow", "r_elbow", "l_wrist", "r_wrist", "l_hip", "r_hip",
    "l_knee", "r_knee", "l_ankle", "r_ankle",
]
COCO_SKELETON = [
    (15, 13), (13, 11), (16, 14), (14, 12), (11, 12), (5, 11), (6, 12), (5, 6),
    (5, 7), (6, 8), (7, 9), (8, 10), (1, 2), (0, 1), (0, 2), (1, 3), (2, 4),
    (3, 5), (4, 6),
]


class SyntheticSource(CameraSource):
    """Test pattern with a walking stick figure; ground-truth keypoints in meta.

    The figure is present for `on_s` seconds then absent for `off_s` seconds
    (in simulated time = index / fps), so pose acquired/lost events fire.
    """

    source = "synthetic"
    sensor_id = "synthetic-0"
    name = "synthetic"

    def __init__(self, width: int = 1280, height: int = 720, fps: float = 30.0,
                 on_s: float = 0.5, off_s: float = 0.33, realtime: bool = False,
                 seed: int = 0) -> None:
        self.w, self.h, self.fps = width, height, fps
        self.on_s, self.off_s = on_s, off_s
        self.realtime = realtime
        self.rng = np.random.default_rng(seed)
        self._i = 0
        self._t0 = time.time()
        yy, xx = np.mgrid[0:height, 0:width]
        base = (40 + 30 * (xx / width) + 20 * (yy / height)).astype(np.uint8)
        self._bg = cv2.merge([base, base, base])
        for x in range(0, width, 80):
            cv2.line(self._bg, (x, 0), (x, height), (70, 70, 70), 1)
        for y in range(0, height, 80):
            cv2.line(self._bg, (0, y), (width, y), (70, 70, 70), 1)

    def _skeleton(self, t: float) -> np.ndarray:
        cx = self.w * (0.5 + 0.3 * math.sin(0.6 * t))
        top = self.h * 0.2
        s = self.h / 720.0
        sw = math.sin(4 * t) * 25 * s  # limb swing
        pts = {
            0: (0, 0), 1: (-8, -8), 2: (8, -8), 3: (-18, -2), 4: (18, -2),
            5: (-45, 60), 6: (45, 60), 7: (-60 - sw * 0.4, 140), 8: (60 + sw * 0.4, 140),
            9: (-65 + sw, 215), 10: (65 - sw, 215), 11: (-30, 220), 12: (30, 220),
            13: (-35 + sw, 330), 14: (35 - sw, 330), 15: (-38 + 1.5 * sw, 440),
            16: (38 - 1.5 * sw, 440),
        }
        return np.array([[cx + x * s, top + y * s] for _, (x, y) in sorted(pts.items())])

    def read(self) -> Optional[Frame]:
        self._i += 1
        t = self._i / self.fps
        if self.realtime:
            target = self._t0 + t
            dt = target - time.time()
            if dt > 0:
                time.sleep(dt)
        img = self._bg.copy()
        period = self.on_s + self.off_s
        present = (t % period) < self.on_s
        kps = None
        if present:
            kps = self._skeleton(t)
            for a, b in COCO_SKELETON:
                cv2.line(img, tuple(map(int, kps[a])), tuple(map(int, kps[b])), (200, 200, 200), 6)
            cv2.circle(img, tuple(map(int, kps[0])), int(22 * self.h / 720), (200, 200, 200), -1)
        noise = self.rng.integers(0, 12, img.shape, dtype=np.uint8)
        img = cv2.add(img, noise)
        cv2.putText(img, "SYNTHETIC TEST PATTERN", (20, self.h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2)
        return Frame(img, time.time(), t, self._i, self.source, self.sensor_id,
                     meta={"gt_keypoints": kps})


def open_camera(kind: str = "auto", device: int = 0, width: int = 1920, height: int = 1080,
                fps: float = 30.0, realtime_synthetic: bool = True) -> CameraSource:
    """Open the best available source. kind: auto|picamera|opencv|synthetic."""
    errors = []
    order = {"auto": ["picamera", "opencv", "synthetic"]}.get(kind, [kind])
    for k in order:
        try:
            if k == "picamera":
                return PicameraSource(width, height, fps)
            if k == "opencv":
                return OpenCVSource(device, min(width, 1280), min(height, 720))
            if k == "synthetic":
                return SyntheticSource(1280, 720, fps, realtime=realtime_synthetic)
            raise ValueError(f"unknown camera source {k!r}")
        except Exception as e:  # ImportError, RuntimeError...
            errors.append(f"{k}: {e}")
            log.info("camera source %s unavailable: %s", k, e)
    raise RuntimeError("no camera source available: " + "; ".join(errors))
