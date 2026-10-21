"""SPECTER-X Stage 1 entry point:  python -m specter.app

Camera (Picamera2 -> OpenCV -> synthetic) -> pose (YOLO11n-pose if installed)
-> provenance-tagged Measurements -> HUD (1280x800) + JSONL event log.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import cv2

from specter import __version__
from specter.events.log import EventLog, PresenceMonitor
from specter.hud.pod import POLARITIES, ZOOMS, PodState, PodTelemetry, render_pod
from specter.hud.renderer import MODES, HUD_H, HUD_W, HudState, render
from specter.ml.pose.estimator import PoseEstimator, make_pose_estimator
from specter.sensors import stubs
from specter.sensors.base import Health, SensorStatus
from specter.sensors.nightvision.camera import open_camera

log = logging.getLogger("specter")
REPO_ROOT = Path(__file__).resolve().parent.parent
WINDOW = "SPECTER-X"


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="specter.app", description="SPECTER-X Stage 1 HUD")
    p.add_argument("--source", default="auto", choices=["auto", "picamera", "opencv", "synthetic"])
    p.add_argument("--device", type=int, default=0, help="OpenCV camera index")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--pose", default="auto", choices=["auto", "yolo", "synthetic", "none"])
    p.add_argument("--model", default="yolo11n-pose.pt")
    p.add_argument("--conf", type=float, default=0.4, help="pose detection threshold")
    p.add_argument("--frames", type=int, default=0, help="stop after N frames (0 = run forever)")
    p.add_argument("--min-seconds", type=float, default=0.0,
                   help="run at least this long, even if --frames is reached first "
                        "(useful for headless runs that wait on a sensor)")
    p.add_argument("--headless", action="store_true", help="no window (CI / ssh)")
    p.add_argument("--windowed", action="store_true", help="window instead of fullscreen")
    p.add_argument("--mode", default="OPTICAL", choices=MODES)
    p.add_argument("--daq", default="off", choices=["off", "di188"],
                   help="enable the DI-188 USB DAQ as a SPECTER-X sensor")
    p.add_argument("--daq-port", default=None, help="DI-188 serial node (default: auto)")
    p.add_argument("--daq-rate", type=float, default=100.0, help="DI-188 sample rate, Hz")
    p.add_argument("--daq-channels", default="0,1,2,3", help="DI-188 channel numbers")
    p.add_argument("--daq-log-hz", type=float, default=1.0,
                   help="how often an analog Measurement is written to the event log")
    p.add_argument("--polarity", default="WHT", choices=POLARITIES, help="POD mode: white-hot or black-hot")
    p.add_argument("--zoom", type=int, default=1, choices=ZOOMS, help="POD mode digital zoom")
    p.add_argument("--log-dir", default=str(REPO_ROOT / "events" / "sessions"))
    p.add_argument("--save-frame", default=None, help="write the last HUD frame to this PNG")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cam = open_camera(a.source, a.device, a.width, a.height, a.fps,
                      realtime_synthetic=not a.headless)
    log.info("camera source: %s (%s)", cam.name, cam.sensor_id)

    try:
        pose = make_pose_estimator(a.pose, cam.name, a.model, a.conf)
    except Exception as e:
        log.error("pose backend %s failed: %s", a.pose, e)
        cam.close()
        return 2
    log.info("pose backend: %s", pose.name)

    events = EventLog(a.log_dir)
    try:
        from specter.hw.pinmap import PINMAP_PATH, load_pinmap

        pinmap = load_pinmap()
        log.info("pinmap ok: %s (%s)", pinmap.board, PINMAP_PATH)
    except Exception as e:
        log.warning("pinmap validation failed (wiring unverified): %s", e)
    cam_health = Health.SIMULATED if cam.source == "synthetic" else Health.OK
    cam_status = SensorStatus("nightvision", "NV CAM IMX462", cam_health, f"{cam.name} {cam.sensor_id}")
    pose_status = SensorStatus("pose", "POSE ENGINE",
                               Health.OK if pose.name != "none" else Health.NOT_INSTALLED,
                               pose.name if pose.name != "none" else "ultralytics missing")
    sensors = [cam_status, pose_status, stubs.probe_thermal(), stubs.probe_senxor(),
               stubs.probe_radar(), stubs.probe_wifi_csi(), stubs.probe_imu(),
               stubs.probe_gnss(), stubs.probe_uwb(), stubs.probe_hailo()]

    # --- DI-188 USB DAQ ------------------------------------------------------
    # Acquisition runs on its own thread; the HUD only ever reads a bounded
    # snapshot, so a slow or absent instrument can never stall the frame loop.
    daq = None
    if a.daq == "di188":
        try:
            from specter.sensors.di188.measure import AnalogSource
            from specter.sensors.di188.stats import default_specs
            channels = [int(c) for c in a.daq_channels.split(",") if c.strip() != ""]
            daq = AnalogSource(port=a.daq_port, channels=channels, rate=a.daq_rate,
                               specs=default_specs(max(channels) + 1),
                               log_interval=1.0 / max(a.daq_log_hz, 0.01))
            daq.start()
        except Exception as e:
            log.warning("DI-188 could not be started: %s", e)
            daq = None
    if daq is not None:
        # The instrument has not connected yet at this point. Say "connecting"
        # rather than "N/A": the DAQ was requested and is on its way.
        sensors.append(SensorStatus("analog", "ANALOG DI-188", Health.DEGRADED,
                                    "connecting"))

    events.log("session_start", {
        "version": __version__, "camera": cam.name, "sensor_id": cam.sensor_id,
        "pose_backend": pose.name, "argv": sys.argv[1:],
        "sensors": {s.key: s.health.value for s in sensors},
    })
    presence = PresenceMonitor("pose", events)
    st = HudState(mode=a.mode, sensors=sensors, source_name=cam.name, session=events.session)
    # No thermal driver yet (stage 2): POD mode runs on an optical-luminance stand-in, labelled SIM.
    pod = PodState(polarity=a.polarity, zoom_idx=ZOOMS.index(a.zoom))
    pod_tel = PodTelemetry()  # IMU / radar / radiometric values plug in here as drivers land

    if not a.headless:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        if a.windowed:
            cv2.resizeWindow(WINDOW, HUD_W, HUD_H)
        else:
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    n = 0
    t_prev = time.perf_counter()
    hud = None
    misses = 0
    daq_snapshot_at = 0.0
    daq_state = None
    t_start = time.monotonic()
    try:
        while a.frames <= 0 or n < a.frames or (time.monotonic() - t_start) < a.min_seconds:
            frame = cam.read()
            if frame is None:
                misses += 1
                cam_status.health = Health.DEGRADED if misses < 30 else Health.OFFLINE
                cam_status.detail = f"read failed x{misses}"
                if misses == 30:
                    events.log("sensor_offline", {"sensor": "nightvision", "sensor_id": cam.sensor_id})
                if misses > 300:
                    break
                time.sleep(0.01)
                continue
            if misses:
                events.log("sensor_recovered", {"sensor": "nightvision", "after_misses": misses})
                misses = 0
                cam_status.health, cam_status.detail = cam_health, f"{cam.name} {cam.sensor_id}"
            n += 1

            t0 = time.perf_counter()
            dets = pose(frame)
            st.infer_ms = 0.9 * st.infer_ms + 0.1 * (time.perf_counter() - t0) * 1000
            best = max(dets, key=lambda m: m.confidence or 0.0) if dets else None
            presence.update(best, frame.index)

            t_now = time.perf_counter()
            inst = 1.0 / max(t_now - t_prev, 1e-6)
            t_prev = t_now
            st.fps = inst if st.fps == 0 else 0.9 * st.fps + 0.1 * inst
            cam_status.touch(st.fps)

            st.poses, st.pose_active, st.ticker = dets, presence.active, list(events.recent)
            if daq is not None:
                # The DAQ snapshot is refreshed at ~10 Hz, not per frame: the
                # HUD must never spend its budget copying a series buffer, and
                # the acquisition thread keeps running regardless.
                now = time.monotonic()
                if now - daq_snapshot_at >= 0.1:
                    daq_snapshot_at = now
                    st.analog = daq.snapshot()
                    status = daq.status(st.analog)
                    for ss in sensors:
                        if ss.key == "analog":
                            ss.health, ss.detail = status.health, status.detail
                    # device connectivity transitions are logged; measurement
                    # validity lives on the channels, not on the device
                    new_state = st.analog.device_state
                    if new_state is not daq_state:
                        events.log("analog_online" if new_state.value == "CONNECTED"
                                   else "analog_state",
                                   {"state": new_state.value,
                                    "detail": st.analog.device_detail[:80]})
                        daq_state = new_state
                m = daq.take_measurement()
                if m is not None:
                    events.log("analog_sample", {"channels": m.value.get("frames", 0)},
                               measurement=m)
            if st.mode == "POD":
                hud = render_pod(frame.image, pod, pod_tel, st.fps)
            else:
                hud = render(frame.image, st)

            if not a.headless:
                cv2.imshow(WINDOW, hud)
                k = cv2.waitKey(1) & 0xFF
                if k in (ord("q"), 27):
                    break
                if k == ord("m"):
                    st.mode = MODES[(MODES.index(st.mode) + 1) % len(MODES)]
                    events.log("mode_change", {"mode": st.mode})
                elif k == ord("p"):
                    pod.toggle_polarity()
                elif k == ord("z"):
                    pod.cycle_zoom()
                elif k == ord("t"):
                    pod.track_enabled = not pod.track_enabled
    except KeyboardInterrupt:
        pass
    finally:
        if presence.active:  # close the open track so every acquired has a matching lost
            events.log("pose_lost", {"reason": "session_end"}, presence.last)
        events.log("session_end", {"frames": n, "event_counts": dict(events.counts)})
        events.close()
        cam.close()
        if daq is not None:
            daq.stop()
        if hud is not None and a.save_frame:
            out = os.path.dirname(os.path.abspath(a.save_frame))
            if out:
                os.makedirs(out, exist_ok=True)
            cv2.imwrite(a.save_frame, hud)
        if not a.headless:
            cv2.destroyAllWindows()
    log.info("done: %d frames, events -> %s", n, events.path)
    print(f"SPECTER-X: {n} frames | camera={cam.name} pose={pose.name} | "
          f"events={dict(events.counts)} | log={events.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
