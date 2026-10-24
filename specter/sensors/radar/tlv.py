"""TI mmWave (IWR6843AOP, out-of-box demo) UART TLV frame parsing.

The packet format is the documented TI mmWave OOB demo layout:

* 40-byte frame header (magic, version, totalPacketLen, platform,
  frameNumber, timeCpuCycles, numDetectedObj, numTLVs, subFrameNumber);
* ``numTLVs`` TLV items, each with an 8-byte type/length header and payload;
* ``totalPacketLen`` includes the header and is padded to a multiple of 32 B.

Detected points (TLV type 1) are ``numDetectedObj`` records of four
little-endian float32 values (x, y, z, radial velocity). Unknown TLVs are
skipped only after their declared boundary is validated.

This is a boundary validator, not a radar measurement model. It does not infer
missing antenna, calibration or detection metadata.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

MAGIC = bytes([0x02, 0x01, 0x04, 0x03, 0x06, 0x05, 0x08, 0x07])
HEADER_FMT = "<8s8I"
HEADER_LEN = struct.calcsize(HEADER_FMT)  # 40
TLV_HEADER_LEN = 8
PACKET_ALIGNMENT = 32
TLV_DETECTED_POINTS = 1
POINT_LEN = 16
# Engineering resource guard, not a vendor field. Valid OOB packets are far
# smaller; this prevents a corrupt header from causing unbounded buffering.
MAX_FRAME_BYTES = 4 * 1024 * 1024


@dataclass
class FrameHeader:
    version: int
    total_len: int
    platform: int
    frame_number: int
    time_cpu_cycles: int
    num_detected: int
    num_tlvs: int
    subframe: int


def find_frame(buf: bytes) -> int:
    """Index of the next magic word in buf, or -1."""
    return buf.find(MAGIC)


def _unpack_header(buf: bytes) -> FrameHeader:
    _, *fields = struct.unpack_from(HEADER_FMT, buf, 0)
    return FrameHeader(*fields)


def _header_shape_valid(hdr: FrameHeader) -> bool:
    if hdr.total_len < HEADER_LEN or hdr.total_len > MAX_FRAME_BYTES:
        return False
    if hdr.total_len % PACKET_ALIGNMENT:
        return False
    return hdr.num_tlvs <= (hdr.total_len - HEADER_LEN) // TLV_HEADER_LEN


def parse_frame(buf: bytes) -> Optional[Tuple[FrameHeader, np.ndarray]]:
    """Parse one complete TI OOB frame starting at ``buf[0]``.

    Returns ``None`` for a non-magic, truncated, malformed or internally
    inconsistent packet. It never allocates from an unvalidated length field.
    """
    if len(buf) < HEADER_LEN or not buf.startswith(MAGIC):
        return None
    try:
        hdr = _unpack_header(buf)
    except struct.error:
        return None
    if not _header_shape_valid(hdr) or len(buf) < hdr.total_len:
        return None
    offset = HEADER_LEN
    points = np.zeros((0, 4), np.float32)
    seen_points = False
    for _ in range(hdr.num_tlvs):
        if offset + TLV_HEADER_LEN > hdr.total_len:
            return None
        tlv_type, tlv_len = struct.unpack_from("<2I", buf, offset)
        offset += TLV_HEADER_LEN
        end = offset + tlv_len
        if tlv_len == 0 or end > hdr.total_len:
            return None
        if tlv_type == TLV_DETECTED_POINTS:
            if seen_points or hdr.num_detected == 0:
                return None
            if tlv_len != hdr.num_detected * POINT_LEN:
                return None
            try:
                frame_points = np.frombuffer(
                    buf[offset:end], dtype="<f4"
                ).reshape(hdr.num_detected, 4)
            except ValueError:
                return None
            if not np.isfinite(frame_points).all():
                return None
            points = frame_points.astype(np.float32, copy=True)
            seen_points = True
        offset = end
    if hdr.total_len - offset >= PACKET_ALIGNMENT:
        return None
    return hdr, points


class RadarFrameStream:
    """Fragmented UART stream framer with resynchronisation.

    Invalid or impossible frames are skipped by advancing one byte and
    searching for the next magic word. A valid frame after corruption is
    therefore not poisoned by the bad prefix.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> List[Tuple[FrameHeader, np.ndarray]]:
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("radar stream requires bytes-like input")
        self._buf.extend(chunk)
        frames: List[Tuple[FrameHeader, np.ndarray]] = []
        keep = len(MAGIC) - 1
        while True:
            index = find_frame(self._buf)
            if index < 0:
                if len(self._buf) > keep:
                    del self._buf[:-keep]
                break
            if index:
                del self._buf[:index]
            if len(self._buf) < HEADER_LEN:
                break
            try:
                hdr = _unpack_header(self._buf)
            except struct.error:
                del self._buf[0]
                continue
            if not _header_shape_valid(hdr):
                del self._buf[0]
                continue
            if len(self._buf) < hdr.total_len:
                break
            parsed = parse_frame(self._buf)
            if parsed is None:
                del self._buf[0]
                continue
            frames.append(parsed)
            del self._buf[:hdr.total_len]
        return frames
