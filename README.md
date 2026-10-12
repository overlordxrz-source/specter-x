# SPECTER-X

![CI](https://github.com/overlordxrz-source/specter-x/actions/workflows/pytest.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

Open-source handheld multisensor fusion: a low-light camera, a thermal imager, a 60&nbsp;GHz radar and Wi-Fi sensing on a Raspberry Pi 5, fused into one touchscreen HUD where **every overlay traces back to its sensor**. Nothing is drawn from vibes; synthetic data is always labelled `SIM`/`SYNTHETIC`.

![POD targeting view (synthetic)](docs/pod.png)
*POD mode: white-hot, 1x, hot-blob tracker locked (`TRK SIM 0.40`); radar/thermal/IMU show dashes until their sensors exist.*

![Optical view (synthetic)](docs/optical.png)
*OPTICAL mode on the synthetic test pattern.*

Handheld multisensor fusion device on a Raspberry Pi 5 (8 GB): low-light optical,
thermal, mmWave radar, Wi-Fi CSI and IMU, fused into a 1280x800 touchscreen HUD.

**Core principle: provenance first.** Every detection is a `Measurement` that carries
its sensor, host and sensor timestamps, confidence/covariance, coordinate frame and
the algorithm/model that produced it. The HUD draws only Measurements and sensor
health records, so nothing unsourced reaches the screen (every overlay prints
`SRC: <SENSOR> conf 0.xx`). Synthetic data is always labelled `SYNTHETIC`, never `OPTICAL`.

## Hardware

| Role | Part | Link | Stage |
|---|---|---|---|
| Compute | Raspberry Pi 5, 8 GB | — | 1 |
| Low-light camera | Arducam IMX462 (CSI, libcamera / Picamera2) | CSI-2 | 1 |
| Display | 7" 1280x800 touchscreen | DSI/HDMI | 1 |
| Thermal | TOPDON TC001 (256x192; UVC frames are 256x384, thermal words in lower half) | USB UVC | 2 |
| IMU | BNO085 | I2C | 2 |
| Radar | TI IWR6843AOPEVM (TLV point clouds) | UART-over-USB | 3 |
| RF sensing | ESP32-S3 Wi-Fi CSI | USB serial | 3 |
| Accelerator | Hailo-8L (optional) | PCIe (M.2 HAT) | 5 |

## Repo layout

```
firmware/esp32-csi/          ESP-IDF CSI streamer (stage 3, placeholder)
specter/
  app.py                     Stage 1 entry point: python -m specter.app
  sensors/
    base.py                  Health enum + SensorStatus (feeds the HUD panel)
    stubs.py                 presence probes for not-yet-integrated sensors
    nightvision/camera.py    Picamera2 -> OpenCV -> synthetic camera sources
    thermal/tc001.py         TC001 frame split + raw->°C helper (stage 2)
    radar/tlv.py             IWR6843 TLV header/point parser (stage 3)
    wifi_csi/  imu/          stage 2/3 placeholders
  calibration/               rig.json (PLACEHOLDER intrinsics/extrinsics) + loader
  fusion/
    measurement.py           Measurement + Provenance dataclasses, JSON round-trip
    coordinate_frames.py     Transform (R,t), FrameGraph, PinholeCamera projection
    tracking.py              Track/Tracker interface (stage 4 stub)
  ml/pose/estimator.py       YOLO11n-pose / synthetic-GT / none backends
  events/log.py              JSONL session log + acquired/lost hysteresis
  hud/renderer.py            OpenCV 1280x800 HUD
events/sessions/             one <session>.jsonl per run
tests/                       pytest suite (projection, serialisation, smoke run)
```

The Python subsystems live inside the `specter` package (rather than at the repo
root) so `python -m specter.app` and imports work without path hacks.

## Quick start (Mac / Linux desktop)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # numpy, opencv-python, pytest
pip install ultralytics                  # optional: real pose (downloads yolo11n-pose.pt on first run)

python -m specter.app --source synthetic --windowed     # test pattern, no camera needed
python -m specter.app --windowed                        # webcam via OpenCV (auto fallback)
python -m specter.app --source synthetic --frames 30 --headless   # CI smoke run
pytest -q
```

Keys: `q`/`Esc` quit, `m` cycle mode (`OPTICAL` / `NIGHT-GREEN` / `POD`),
`p` POD polarity (white-hot / black-hot), `z` POD zoom (1x / 2x / 4x / 8x),
`t` toggle the hot-blob tracker.

Useful flags: `--source auto|picamera|opencv|synthetic`, `--pose auto|yolo|synthetic|none`,
`--model yolo11n-pose.pt`, `--conf 0.4`, `--frames N`, `--headless`, `--windowed`,
`--save-frame hud.png`, `--log-dir DIR`.

`--pose auto` uses YOLO11n-pose if Ultralytics is installed; otherwise it uses
ground-truth keypoints when the source is synthetic, and no pose for a real camera.

## Raspberry Pi 5 setup

1. **OS:** flash Raspberry Pi OS Bookworm 64-bit (desktop, for the HUD window), then
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y python3-picamera2 python3-opencv python3-venv git
   ```
2. **Camera overlay:** edit `/boot/firmware/config.txt`:
   ```ini
   camera_auto_detect=0
   dtoverlay=imx462
   ```
   (If the Arducam module is on the CAM0 port, Arducam's docs use `dtoverlay=imx462,cam0`.)
   Reboot, then check: `rpicam-hello --list-cameras` and `rpicam-hello -t 5000`.
   Some Arducam IMX462 boards need Arducam's own libcamera tuning file; follow
   Arducam's IMX462 page if the camera is not listed.
3. **venv that can see apt's picamera2/libcamera:**
   ```bash
   git clone <repo> specter-x && cd specter-x
   python3 -m venv --system-site-packages .venv && source .venv/bin/activate
   pip install -r requirements-pi.txt   # numpy, pytest, ultralytics (optional, pulls CPU torch)
   ```
   Do **not** `pip install opencv-python` inside this venv; use apt's `python3-opencv`
   so it matches the system Qt/GTK for the fullscreen window.
4. **Run:** `python -m specter.app` (fullscreen 1280x800; picks Picamera2 automatically).
   Over SSH without a display: `python -m specter.app --headless --frames 300`.
5. **Pose performance on the Pi 5 CPU:** YOLO11n-pose at `imgsz=640` is the slowest
   part of the loop. If it is too slow, export to NCNN (`yolo export model=yolo11n-pose.pt format=ncnn`)
   and pass `--model yolo11n-pose_ncnn_model`; the Hailo-8L path is Stage 5.

## Event log format

`events/sessions/<YYYYmmdd-HHMMSS-xxxxxx>.jsonl`, one JSON object per line:

```json
{"t_host": 1760253038.1, "session": "20261012-073038-2bdf03", "seq": 2,
 "event": "pose_acquired", "detail": {"frame_index": 3},
 "measurement": {"sensor": "nightvision", "kind": "pose2d", "t_host": ..., "t_sensor": ...,
   "frame_id": "imx462-0/image", "value": {"keypoints_xy": [...], "keypoint_conf": [...],
   "bbox_xyxy": [...], "image_size": [1920, 1080]}, "confidence": 0.87, "covariance": null,
   "provenance": {"sensor_id": "imx462-0", "source": "nightvision", "algorithm": "yolo11n-pose",
     "model_version": "yolo11n-pose.pt@ultralytics-8.x", "frame_index": 1234, "parents": []}}}
```

Events in Stage 1: `session_start`, `pose_acquired` (3 consecutive frames with a person),
`pose_lost` (5 consecutive frames without, or `reason: session_end`), `mode_change`,
`sensor_offline`, `sensor_recovered`, `session_end`.

## Coordinate conventions

* `T_a_b` maps points in frame `b` to frame `a`: `p_a = R p_b + t`; compose `T_a_c = T_a_b @ T_b_c`.
* Camera frames: OpenCV optical (+x right, +y down, +z forward).
* Body frame: +x forward, +y left, +z up. `R_CAM_BODY` converts body -> camera optical.
* `specter/calibration/rig.json` holds **placeholder** intrinsics (from a nominal FOV) until calibrated.

## Roadmap

1. **Stage 1: optical HUD (this commit).** IMX462 via Picamera2 with OpenCV/synthetic fallbacks,
   YOLO11n-pose, fullscreen HUD with sensor health, provenance-tagged overlays, JSONL event log, tests.
2. **Stage 2: thermal + IMU + calibration.** TC001 UVC driver (raw mode, °C per pixel),
   BNO085 orientation, IMX462 intrinsics, optical/thermal extrinsics with a heated checkerboard,
   thermal overlay with its own `SRC: THERMAL` tags, horizon line from the IMU.
3. **Stage 3: radar + Wi-Fi CSI.** IWR6843AOP config + TLV point clouds projected into the
   camera view; ESP32-S3 CSI firmware and host parser for through-wall presence/motion;
   hardware timestamp alignment across sensors.
4. **Stage 4: fusion and tracking.** Kalman tracks in the body frame fed by optical/thermal
   bearings, radar range/Doppler and CSI presence; each track lists the sensors and Measurement
   ids behind it; IMU-stabilised track display; session replay from the JSONL log.
5. **Stage 5: acceleration and field unit.** Hailo-8L pose/detection (HEF models), power and
   thermal budget, battery and enclosure, touchscreen controls, packaged systemd service.

## Honest limits

- LWIR thermal sees surface temperature, not through things: it does **not** see through walls, glass, or much beyond thin fabric. Anyone claiming otherwise is selling something.
- Radar (60 GHz) and Wi-Fi CSI cover presence and motion where optics can't, including through interior walls — that is why this device has them instead of a bigger thermal sensor.
- Synthetic mode is a test pattern for development and CI. It proves the pipeline runs, not that any sensor works.

## Sponsors & support

No sponsors yet. If a company wants its logo here, it can fund hardware or build time first.
