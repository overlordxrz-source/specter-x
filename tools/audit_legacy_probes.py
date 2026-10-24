"""Offline diagnostic probes for known legacy blockers; no hardware or transport.

Prints observations, not passing release gates. Reclassify findings after fixes.
"""
from __future__ import annotations
import json
import struct
import numpy as np
from specter.fusion.team import TeamFuser
from specter.net.messages import TrackReport
from specter.localization.ekf import PoseEKF
from specter.sensors.gnss.neom9n import Neom9nDriver, build_nav_pvt
from specter.sensors.imu.bno085 import quat_measurement
from specter.sensors.radar.tlv import MAGIC, parse_frame


def probe():
    stale = TeamFuser('local', max_age_s=5)
    stale.ingest_report(TrackReport('peer', 1, 1.0, 1, [0, 0, 0], np.eye(3)),
                        clock_offset_s=0.0)
    stale_tracks = stale.fuse(t_now=100.0)
    future = TeamFuser('local', max_age_s=5)
    future.ingest_report(TrackReport('peer', 1, 200.0, 1, [0, 0, 0], np.eye(3)),
                         clock_offset_s=0.0)
    future_tracks = future.fuse(t_now=100.0)
    unknown = TeamFuser('local', max_age_s=5)
    unknown.ingest_report(TrackReport('peer', 1, 100.0, 1, [0, 0, 0], np.eye(3)))
    unknown_tracks = unknown.fuse(t_now=100.0)
    repeated = TeamFuser('local')
    repeated.add_local(1, [0, 0, 0], np.eye(3), 'thermal', ['same-parent'], t_host=1.0)
    repeated.ingest_report(TrackReport('peer', 1, 1.0, 1, [0, 0, 0], np.eye(3),
                                       measurement_ids=['same-parent']),
                           clock_offset_s=0.0)
    merged = repeated.fuse(t_now=1.0)
    ekf = PoseEKF('local')
    no_fix = Neom9nDriver().feed(build_nav_pvt(fix_type=0))[0]
    pose = ekf.update_gnss(no_fix)
    malformed = struct.pack('<8s8I', MAGIC, 1, 1, 1, 1, 1, 0, 1, 0)
    q = quat_measurement([float('nan'), 0, 0, 0])
    return {
        'scope': 'Synthetic Python inputs only; diagnoses remaining legacy blockers and fixed team controls.',
        'stale_peer_restamped_fresh': bool(stale_tracks and stale_tracks[0].last_update == 100),
        'future_peer_admitted': bool(future_tracks),
        'unknown_age_peer_admitted': bool(unknown_tracks),
        'shared_parent_covariance_halved': bool(len(merged) == 1 and merged[0].covariance[0, 0] < .51),
        'no_fix_anchors_and_claims_gnss': pose.anchor is not None and pose.mode == 'GNSS',
        'radar_impossible_packet_length_accepted': parse_frame(malformed) is not None,
        'nonfinite_quaternion_accepted': not np.isfinite(q.value['quat_wxyz']).all(),
        'action': 'Team evidence-validity controls are fixed. Three P1s remain; do not enable these legacy modules as calibrated/live WORLD capabilities.',
    }


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
