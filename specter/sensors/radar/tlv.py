"""TI mmWave (IWR6843AOP, out-of-box demo) UART TLV frame parsing (Stage 3).

Frame = 40-byte header + numTLVs x (type:uint32, length:uint32, payload).
Header: magic word (8 bytes: 02 01 04 03 06 05 08 07) then 8 x uint32:
version, totalPacketLen, platform, frameNumber, timeCpuCycles,
numDetectedObj, numTLVs, subFrameNumber.
TLV type 1 = detected points: numDetectedObj x 4 float32 (x, y, z, doppler).
Check these against the SDK version flashed on the board.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

MAGIC = bytes([0x02, 0x01, 0x04, 0x03, 0x06, 0x05, 0x08, 0x07])
HEADER_FMT = "<8s8I"
HEADER_LEN = struct.calcsize(HEADER_FMT)  # 40
TLV_DETECTED_POINTS = 1


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


def parse_frame(buf: bytes) -> Optional[Tuple[FrameHeader, np.ndarray]]:
    """Parse one complete frame starting at buf[0]. Returns (header, points Nx4) or None."""
    if len(buf) < HEADER_LEN or not buf.startswith(MAGIC):
        return None
    _, *fields = struct.unpack_from(HEADER_FMT, buf, 0)
    hdr = FrameHeader(*fields)
    if len(buf) < hdr.total_len:
        return None
    off = HEADER_LEN
    points = np.zeros((0, 4), np.float32)
    for _ in range(hdr.num_tlvs):
        if off + 8 > hdr.total_len:
            break
        ttype, tlen = struct.unpack_from("<2I", buf, off)
        off += 8
        payload = buf[off:off + tlen]
        if ttype == TLV_DETECTED_POINTS and hdr.num_detected:
            points = np.frombuffer(payload[: hdr.num_detected * 16], dtype="<f4").reshape(-1, 4)
        off += tlen
    return hdr, points
