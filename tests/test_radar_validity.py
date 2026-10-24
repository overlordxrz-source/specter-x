"""Strict TI mmWave OOB UART frame/TLV validation controls.

The reference fixture is spec-derived, not a hardware capture. See
``tests/fixtures/radar/README.md`` for provenance and the frozen hash.
"""

import hashlib
import struct
from pathlib import Path

import numpy as np
import pytest

from specter.sensors.radar.tlv import (
    MAGIC,
    HEADER_FMT,
    RadarFrameStream,
    parse_frame,
)

FIXTURE = Path(__file__).parent / "fixtures/radar/iwr6843aop_oob_points_2.bin"
FIXTURE_SHA256 = "ea26d5ef056ced916ee39f3b6120cffa8c6acb335fdff94326cad80b4dd1d8db"
POINTS = np.array([[1.0, 2.0, 0.5, -0.1], [0.2, 3.0, 0.0, 0.4]], "<f4")


def build_frame(
    points=POINTS,
    *,
    total_len_override=None,
    num_tlvs=1,
    num_detected=None,
    tlv_type=1,
    tlv_len_override=None,
    extra=b"",
):
    pts = np.asarray(points, dtype="<f4")
    if pts.ndim != 2 or pts.shape[1] != 4:
        raise ValueError("points must be Nx4")
    payload = pts.tobytes()
    tlv_len = len(payload) if tlv_len_override is None else tlv_len_override
    body = struct.pack("<2I", tlv_type, tlv_len) + payload + extra
    raw_len = struct.calcsize(HEADER_FMT) + len(body)
    pad = (32 - (raw_len % 32)) % 32
    total_len = raw_len + pad
    declared_total = total_len if total_len_override is None else total_len_override
    declared_points = len(pts) if num_detected is None else num_detected
    header = struct.pack(
        HEADER_FMT,
        MAGIC,
        0x03060000,
        declared_total,
        0x6843,
        7,
        0,
        declared_points,
        num_tlvs,
        0,
    )
    return header + body + b"\x00" * pad


def test_reference_fixture_is_frozen_and_parses():
    blob = FIXTURE.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == FIXTURE_SHA256
    header, points = parse_frame(blob)
    assert header.total_len == 96
    assert header.num_detected == 2 and header.num_tlvs == 1
    np.testing.assert_allclose(points, POINTS)


@pytest.mark.parametrize(
    "blob",
    [
        b"",
        b"\x00" * 40,
        build_frame(total_len_override=1),
        build_frame(total_len_override=39),
        build_frame(total_len_override=80),
        build_frame(total_len_override=128),
    ],
)
def test_impossible_or_truncated_lengths_are_rejected(blob):
    assert parse_frame(blob) is None


def test_missing_tlv_headers_are_rejected():
    blob = build_frame(points=POINTS[:1], num_tlvs=2)
    assert len(blob) == 64  # header + one point TLV, already a multiple of 32
    assert parse_frame(blob) is None


def test_tlv_payload_past_packet_end_is_rejected():
    blob = build_frame(tlv_len_override=64)
    assert parse_frame(blob) is None


def test_detected_points_length_must_match_header_count():
    for bad_len in (16, 31, 48):
        blob = build_frame(tlv_len_override=bad_len)
        assert parse_frame(blob) is None


def test_zero_length_tlv_is_rejected():
    blob = build_frame(tlv_len_override=0)
    assert parse_frame(blob) is None


def test_duplicate_detected_points_tlv_is_rejected():
    extra = struct.pack("<2I", 1, POINTS.nbytes) + POINTS.tobytes()
    blob = build_frame(num_tlvs=2, extra=extra)
    assert parse_frame(blob) is None


def test_nonfinite_point_values_are_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        points = POINTS.copy()
        points[0, 0] = bad
        blob = build_frame(points=points)
        assert parse_frame(blob) is None


def test_unknown_tlv_is_skipped_without_losing_points():
    side = struct.pack("<2I", 7, 4) + b"\x01\x02\x03\x04"
    blob = build_frame(num_tlvs=2, extra=side)
    header, points = parse_frame(blob)
    assert header.num_tlvs == 2
    np.testing.assert_allclose(points, POINTS)


def test_padding_is_not_interpreted_as_extra_tlv():
    blob = build_frame(num_tlvs=3)  # one real TLV + zero padding
    assert len(blob) == 96
    assert parse_frame(blob) is None


def test_stream_handles_fragmented_reference_frame():
    blob = FIXTURE.read_bytes()
    stream = RadarFrameStream()
    frames = []
    for start in range(0, len(blob), 7):
        frames.extend(stream.feed(blob[start:start + 7]))
    assert len(frames) == 1
    _, points = frames[0]
    np.testing.assert_allclose(points, POINTS)


def test_stream_does_not_poison_valid_frame_after_bad_frame():
    bad = build_frame(total_len_override=1)
    good = FIXTURE.read_bytes()
    stream = RadarFrameStream()
    frames = stream.feed(bad + b"garbage" + good)
    assert len(frames) == 1
    _, points = frames[0]
    np.testing.assert_allclose(points, POINTS)


def test_stream_recovers_after_truncated_frame_and_chunked_magic():
    good = FIXTURE.read_bytes()
    stream = RadarFrameStream()
    assert stream.feed(good[:3]) == []
    frames = stream.feed(good[3:])
    assert len(frames) == 1
    np.testing.assert_allclose(frames[0][1], POINTS)


def test_stream_recovers_after_invalid_tlv():
    bad = build_frame(tlv_len_override=64)
    good = FIXTURE.read_bytes()
    stream = RadarFrameStream()
    frames = stream.feed(bad)
    assert frames == []
    frames = stream.feed(good)
    assert len(frames) == 1
    np.testing.assert_allclose(frames[0][1], POINTS)


def test_stream_ignores_garbage_without_magic():
    stream = RadarFrameStream()
    assert stream.feed(b"\x00\x01\x02" * 100) == []
    frames = stream.feed(FIXTURE.read_bytes())
    assert len(frames) == 1
    np.testing.assert_allclose(frames[0][1], POINTS)
