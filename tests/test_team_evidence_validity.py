"""Evidence-validity controls for legacy team fusion.

These tests are deliberately offline and synthetic. Team fusion remains a
legacy capability: fresh, non-duplicated reports are required before any
precision merge, and WORLD must not import this module.
"""

import math

import numpy as np
import pytest

from specter.fusion.team import TeamFuser
from specter.net.messages import TrackReport


def report(t_host=100.0, *, unit="peer", mids=("m-peer",), cov=None, frame="enu"):
    return TrackReport(
        unit,
        1,
        t_host,
        7,
        [0.0, 0.0, 0.0],
        np.eye(3) if cov is None else cov,
        source_unit=unit,
        source_sensor="thermal",
        measurement_ids=list(mids),
        confidence=0.8,
        frame_id=frame,
    )


def test_stale_peer_is_not_restamped_fresh():
    fuser = TeamFuser("local", max_age_s=5.0)
    fuser.ingest_report(report(1.0), clock_offset_s=0.0)
    assert fuser.fuse(t_now=100.0) == []


def test_future_peer_is_rejected():
    fuser = TeamFuser("local", max_age_s=5.0, max_future_s=1.0)
    fuser.ingest_report(report(200.0), clock_offset_s=0.0)
    assert fuser.fuse(t_now=100.0) == []


def test_unknown_age_peer_is_rejected():
    fuser = TeamFuser("local", max_age_s=5.0)
    fuser.ingest_report(report(100.0), clock_offset_s=None)
    assert fuser.fuse(t_now=100.0) == []


def test_known_offset_maps_peer_time_to_local_time():
    fuser = TeamFuser("local", max_age_s=5.0)
    fuser.ingest_report(report(110.0), clock_offset_s=10.0)
    (track,) = fuser.fuse(t_now=100.0)
    assert track.last_update == pytest.approx(100.0)


def test_report_time_is_not_replaced_by_fusion_time():
    fuser = TeamFuser("local", max_age_s=5.0)
    fuser.ingest_report(report(99.0), clock_offset_s=0.0)
    (track,) = fuser.fuse(t_now=100.0)
    assert track.last_update == pytest.approx(99.0)


def test_repeated_fusion_does_not_advance_evidence_time():
    fuser = TeamFuser("local", max_age_s=5.0)
    for now in (100.0, 101.0):
        fuser.ingest_report(report(99.0), clock_offset_s=0.0)
        (track,) = fuser.fuse(t_now=now)
        assert track.last_update == pytest.approx(99.0)


def test_shared_parent_does_not_increase_precision():
    fuser = TeamFuser("local")
    fuser.add_local(1, [0.0, 0.0, 0.0], np.eye(3), "thermal", ["same-parent"], t_host=1.0)
    fuser.ingest_report(
        report(1.0, mids=("same-parent",)), clock_offset_s=0.0
    )
    (track,) = fuser.fuse(t_now=1.0)
    assert track.covariance[0, 0] == pytest.approx(1.0)
    assert track.fusion_status == "shared_evidence"
    assert set(track.measurement_ids) == {"same-parent"}


def test_looped_peer_duplicate_does_not_increase_precision():
    fuser = TeamFuser("local")
    fuser.add_local(1, [0.0, 0.0, 0.0], np.eye(3), "thermal", ["same-parent"], t_host=1.0)
    fuser.ingest_report(
        report(1.0, unit="peer-a", mids=("same-parent",)), clock_offset_s=0.0
    )
    fuser.ingest_report(
        report(1.0, unit="peer-b", mids=("same-parent",)), clock_offset_s=0.0
    )
    tracks = fuser.fuse(t_now=1.0)
    assert tracks
    assert all(track.covariance[0, 0] >= 0.99 for track in tracks)
    assert sum(track.fusion_status == "shared_evidence" for track in tracks) >= 1


def test_unknown_parentage_is_not_assumed_independent():
    fuser = TeamFuser("local")
    fuser.add_local(1, [0.0, 0.0, 0.0], np.eye(3), "thermal", [], t_host=1.0)
    fuser.ingest_report(report(1.0, mids=()), clock_offset_s=0.0)
    (track,) = fuser.fuse(t_now=1.0)
    assert track.covariance[0, 0] == pytest.approx(1.0)
    assert track.fusion_status == "shared_evidence"


def test_disjoint_validated_evidence_fuses_with_provenance():
    fuser = TeamFuser("local")
    fuser.add_local(1, [0.0, 0.0, 0.0], np.eye(3), "thermal", ["m-local"], t_host=1.0)
    fuser.ingest_report(
        report(1.0, mids=("m-peer",)), clock_offset_s=0.0
    )
    (track,) = fuser.fuse(t_now=1.0)
    assert track.covariance[0, 0] == pytest.approx(0.5)
    assert track.fusion_status == "independent"
    assert set(track.measurement_ids) == {"m-local", "m-peer"}
    assert ("local", "thermal") in track.contributors
    assert ("peer", "thermal") in track.contributors


@pytest.mark.parametrize(
    "bad_cov",
    [
        None,
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[math.nan, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    ],
)
def test_invalid_local_covariance_is_rejected(bad_cov):
    fuser = TeamFuser("local")
    with pytest.raises(ValueError):
        fuser.add_local(1, [0.0, 0.0, 0.0], bad_cov, "thermal", ["m"])


def test_invalid_peer_covariance_is_rejected():
    fuser = TeamFuser("local")
    bad = report(cov=np.eye(3))
    bad.cov_3x3 = [[math.nan, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    with pytest.raises(ValueError):
        fuser.ingest_report(bad, clock_offset_s=0.0)


def test_mismatched_frame_is_rejected():
    fuser = TeamFuser("local", frame_id="enu")
    with pytest.raises(ValueError):
        fuser.ingest_report(report(100.0, frame="body"), clock_offset_s=0.0)
    with pytest.raises(ValueError):
        fuser.add_local(
            1, [0.0, 0.0, 0.0], np.eye(3), "thermal", ["m"], frame_id="body"
        )


def test_confirmatory_requires_finite_known_age():
    fuser = TeamFuser("local")
    fuser.ingest_report(report(100.0), clock_offset_s=0.0)
    (track,) = fuser.fuse(t_now=100.0)
    assert track.last_update == pytest.approx(100.0)
    assert track.fusion_status == "single"


def test_anchor_transform_is_rejected_not_invented():
    fuser = TeamFuser("local")
    with pytest.raises(ValueError):
        fuser.ingest_report(
            report(100.0), own_anchor=[47.0, 8.0, 400.0], clock_offset_s=0.0
        )


def test_track_frame_roundtrips_through_message_contract():
    from specter.net.messages import decode_message

    original = report(100.0, frame="team_enu")
    decoded = decode_message(original.to_json())
    assert decoded.frame_id == "team_enu"
    assert decoded.measurement_ids == ["m-peer"]


def test_shared_parent_does_not_average_confidence():
    fuser = TeamFuser("local")
    fuser.add_local(
        1, [0.0, 0.0, 0.0], np.eye(3), "thermal", ["same-parent"],
        confidence=0.2, t_host=1.0
    )
    peer = report(1.5, mids=("same-parent",))
    fuser.ingest_report(peer, clock_offset_s=0.0)
    (track,) = fuser.fuse(t_now=1.5)
    assert track.fusion_status == "shared_evidence"
    assert track.confidence == pytest.approx(0.8)
