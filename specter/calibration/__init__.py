"""Intrinsics/extrinsics storage. Stage 2 adds a checkerboard intrinsics tool for
the IMX462 and a heated-checkerboard optical<->thermal extrinsic calibration."""
import json
from pathlib import Path

from specter.fusion.coordinate_frames import PinholeCamera, Transform

DEFAULT_PATH = Path(__file__).with_name("rig.json")


def load_rig(path=DEFAULT_PATH):
    d = json.loads(Path(path).read_text())
    cams = {k: PinholeCamera(**v) for k, v in d.get("cameras", {}).items()}
    ext = {k: Transform.from_dict(v) for k, v in d.get("extrinsics", {}).items()}
    return cams, ext
