"""Team fusion + man-down: Mahalanobis gating, Hungarian merge, stillness alerts."""
import time

import numpy as np
import pytest

from specter.fusion.team import (
    GATE_CHI2_3DOF_95, ManDownDetector, TeamFuser, mahalanobis2,
    tilt_from_vertical_deg,
)
from specter.net import PoseStamped, TrackReport


def _rep(uid, pos, cov=1.0, sensor="thermal", mids=("m1",), conf=0.8):
    return TrackReport(uid, 1, time.time(), 7, pos, np.eye(3) * cov,
                       uid, sensor, mids, conf)


def test_mahalanobis_gating():
    assert mahalanobis2([0, 0, 0], np.eye(3), [0, 0, 0], np.eye(3)) == 0.0
    far = mahalanobis2([0, 0, 0], np.eye(3) * 0.01, [5, 0, 0], np.eye(3) * 0.01)
    assert far > GATE_CHI2_3DOF_95


def test_same_contact_merges_with_both_contributors():
    f = TeamFuser("unit-1")
    f.add_local(1, [10.0, 4.0, 0.0], np.eye(3) * 0.25, "thermal", ["m-local"], 0.8)
    f.ingest_report(_rep("unit-2", [10.2, 4.1, 0.0], 0.25, "thermal", ["m-peer"], 0.7))
    (merged,) = f.fuse(t_now=time.time())
    assert ("unit-1", "thermal") in merged.contributors
    assert ("unit-2", "thermal") in merged.contributors
    assert set(merged.measurement_ids) == {"m-local", "m-peer"}  # provenance kept
    np.testing.assert_allclose(merged.position[:2], [10.1, 4.05], atol=0.05)
    assert merged.confidence == (0.8 + 0.7) / 2


def test_distant_reports_stay_separate():
    f = TeamFuser("unit-1")
    f.add_local(1, [0.0, 0.0, 0.0], np.eye(3) * 0.04, "thermal", ["a"], 0.9)
    f.ingest_report(_rep("unit-2", [50.0, 0.0, 0.0], 0.04, "thermal", ["b"], 0.9))
    assert len(f.fuse(t_now=time.time())) == 2


def test_uncertain_peer_deweighted_in_merge():
    f = TeamFuser("unit-1")
    f.add_local(1, [0.0, 0.0, 0.0], np.eye(3) * 0.01, "thermal", ["a"], 0.9)
    f.ingest_report(_rep("unit-2", [2.0, 0.0, 0.0], 25.0, "thermal", ["b"], 0.5))
    (merged,) = f.fuse(t_now=time.time())
    assert abs(merged.position[0]) < 0.2  # precise local dominates vague peer


def test_stale_merged_tracks_pruned():
    f = TeamFuser("unit-1", max_age_s=1.0)
    f.add_local(1, [0, 0, 0], np.eye(3), "thermal")
    assert len(f.fuse(t_now=100.0)) == 1
    assert f.fuse(t_now=102.0) == []


def test_tilt_math():
    assert tilt_from_vertical_deg([1, 0, 0, 0]) == 0.0
    # 90° about body x: torso horizontal
    assert tilt_from_vertical_deg([0.7071, 0.7071, 0, 0]) == 90.0
    assert tilt_from_vertical_deg(None) is None


def test_man_down_on_stillness_not_motion():
    d = ManDownDetector("unit-2", still_s=10.0)
    assert d.update(0.0, 0.0) is None
    alert = d.update(11.0, 0.0, seq=3)
    assert alert is not None and alert.kind == "man-down"
    assert alert.detail["reason"] == "no-motion" and alert.unit_id == "unit-2"
    d2 = ManDownDetector("unit-2", still_s=10.0)
    for t in range(12):
        assert d2.update(float(t), 1.5) is None  # walking: never fires


def test_man_down_on_horizontal_pose():
    d = ManDownDetector("unit-2", horiz_s=5.0)
    flat = [0.7071, 0.7071, 0, 0]
    assert d.update(0.0, 0.0, flat) is None
    alert = d.update(6.0, 0.0, flat)
    assert alert is not None and alert.detail["reason"] in ("no-motion", "horizontal")


def test_man_down_from_peer_pose_stamped():
    d = ManDownDetector("unit-2", still_s=10.0)
    p = PoseStamped("unit-2", 1, 100.0, [0, 0, 0], [0, 0, 0],
                    np.eye(3).tolist(), "REL", None, [1, 0, 0, 0])
    assert d.update_from_pose(p) is None
    p2 = PoseStamped("unit-2", 2, 111.0, [0, 0, 0], [0, 0, 0],
                     np.eye(3).tolist(), "REL", None, [1, 0, 0, 0])
    alert = d.update_from_pose(p2)
    assert alert is not None and alert.kind == "man-down"
