"""Pose estimation backends. Every detection is emitted as a Measurement.

Backends
--------
* "yolo"      : Ultralytics YOLO11n-pose (CPU on Pi 5; Hailo-8L path is Stage 5)
* "synthetic" : reads ground-truth keypoints from SyntheticSource frames, so the
                pipeline and HUD can be exercised without a model. Labelled
                SRC: SYNTHETIC, never OPTICAL.
* "none"      : no pose.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from specter.fusion.measurement import Measurement, Provenance
from specter.sensors.nightvision.camera import Frame

log = logging.getLogger(__name__)


class PoseEstimator:
    name = "none"
    available = True

    def __call__(self, frame: Frame) -> List[Measurement]:
        return []

    @property
    def status_detail(self) -> str:
        return self.name


def _pose_measurement(frame: Frame, kps: np.ndarray, kconf: np.ndarray, box, score: float,
                      algorithm: str, model_version: Optional[str]) -> Measurement:
    return Measurement(
        sensor=frame.source,
        kind="pose2d",
        t_host=frame.t_host,
        t_sensor=frame.t_sensor,
        frame_id=f"{frame.sensor_id}/image",   # pixel frame of the source image
        value={
            "keypoints_xy": np.round(np.asarray(kps, float), 1).tolist(),
            "keypoint_conf": np.round(np.asarray(kconf, float), 3).tolist(),
            "bbox_xyxy": [round(float(v), 1) for v in box],
            "image_size": [int(frame.image.shape[1]), int(frame.image.shape[0])],
        },
        confidence=float(np.clip(score, 0.0, 1.0)),
        provenance=Provenance(
            sensor_id=frame.sensor_id,
            source=frame.source,
            algorithm=algorithm,
            model_version=model_version,
            frame_index=frame.index,
        ),
    )


class YoloPose(PoseEstimator):
    name = "yolo11n-pose"

    def __init__(self, model: str = "yolo11n-pose.pt", conf: float = 0.4, imgsz: int = 640,
                 device: Optional[str] = None) -> None:
        from ultralytics import YOLO  # ImportError if not installed

        self.model = YOLO(model)
        self.conf, self.imgsz, self.device = conf, imgsz, device
        self.model_version = model
        try:
            import ultralytics
            self.model_version = f"{model}@ultralytics-{ultralytics.__version__}"
        except Exception:
            pass

    def __call__(self, frame: Frame) -> List[Measurement]:
        kwargs = dict(conf=self.conf, imgsz=self.imgsz, verbose=False)
        if self.device:
            kwargs["device"] = self.device
        res = self.model(frame.image, **kwargs)[0]
        out: List[Measurement] = []
        if res.keypoints is None or res.boxes is None or len(res.boxes) == 0:
            return out
        xy = res.keypoints.xy.cpu().numpy()
        kc = res.keypoints.conf
        kc = kc.cpu().numpy() if kc is not None else np.ones(xy.shape[:2])
        boxes = res.boxes.xyxy.cpu().numpy()
        scores = res.boxes.conf.cpu().numpy()
        for i in range(len(boxes)):
            out.append(_pose_measurement(frame, xy[i], kc[i], boxes[i], scores[i],
                                         "yolo11n-pose", self.model_version))
        return out


class SyntheticPose(PoseEstimator):
    name = "synthetic-gt"

    def __call__(self, frame: Frame) -> List[Measurement]:
        kps = frame.meta.get("gt_keypoints")
        if kps is None:
            return []
        kps = np.asarray(kps)
        x0, y0 = kps.min(0) - 25
        x1, y1 = kps.max(0) + 25
        return [_pose_measurement(frame, kps, np.full(len(kps), 0.99), (x0, y0, x1, y1),
                                  0.99, "synthetic-ground-truth", None)]


def make_pose_estimator(kind: str, source_kind: str, model: str, conf: float) -> PoseEstimator:
    """kind: auto|yolo|synthetic|none. auto = yolo if importable, else synthetic GT
    when the camera is synthetic, else none."""
    if kind in ("auto", "yolo"):
        try:
            return YoloPose(model=model, conf=conf)
        except Exception as e:
            if kind == "yolo":
                raise
            log.warning("YOLO pose unavailable (%s); falling back", e)
    if kind == "synthetic" or (kind == "auto" and source_kind == "synthetic"):
        return SyntheticPose()
    return PoseEstimator()
