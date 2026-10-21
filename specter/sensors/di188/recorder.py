"""CSV recorder for DI-188 acquisitions, with a provenance header.

Every file states which instrument produced it, on which port, with which
calibration basis and what was connected to each channel - so a recording
taken three weeks later cannot be mistaken for a calibrated measurement.
"""
from __future__ import annotations

import csv
import os
import time
from typing import Iterable, List, Optional, Sequence

from .calibration import CalibrationSet
from .stats import ChannelReport


def build_provenance(identity, device_cal, calibration: Optional[CalibrationSet],
                     channels: Sequence[int], rate: float,
                     reports: Sequence[ChannelReport] = ()) -> List[str]:
    """Header comment lines describing the acquisition."""
    lines = [
        "# SPECTER-X DI-188 acquisition",
        f"# recorded_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
    ]
    if identity is not None:
        lines += [
            f"# device: {identity.model_name} ({identity.vendor_tag}) "
            f"serial={identity.serial_number or '?'} "
            f"fw={identity.firmware_rev or '?'} hw={identity.hardware_rev or '?'}",
            f"# usb: {identity.usb_product or '?'} "
            f"{_hex(identity.usb_vid)}:{_hex(identity.usb_pid)} "
            f"usb_serial={identity.usb_serial or '?'}",
            f"# port: {identity.port}",
        ]
    if device_cal is not None and device_cal.read_ok:
        scale0 = device_cal.channel_scale(0)
        lines += [
            f"# device_digital_cal: scale={scale0 if scale0 is not None else '?'} "
            f"offset(ch0..3)="
            f"{[device_cal.channel_offset(i) for i in range(4)]} "
            f"last_cal_date={device_cal.last_cal_date or '?'}",
        ]
    if calibration is not None:
        lines += [
            f"# calibration_basis: {calibration.basis_label()} "
            f"(profile={calibration.profile}, created={calibration.created_utc or '?'}, "
            f"operator={calibration.operator or '?'})",
        ]
        for ch in sorted(calibration.channels):
            cal = calibration.channels[ch]
            lines.append(
                f"# cal_ch{ch}: basis={cal.basis} gain={cal.gain:.9g} V/count "
                f"offset={cal.offset:.9g} V unc={cal.uncertainty_v:.9g} V "
                f"reference={cal.reference or 'n/a'}")
    lines.append(f"# sample_rate_hz: {rate:g}")
    lines.append(f"# scan_list_channels: {list(channels)}")
    for rep in reports:
        lines.append(
            f"# channel_state ch{rep.index} ({rep.label}, {rep.terminal}): "
            f"{rep.state.value} source={rep.source or 'none'} | {rep.note}")
    lines.append("# counts are the instrument's device-calibrated integers; "
                 "volts use the calibration basis stated above")
    return lines


def _hex(v) -> str:
    try:
        return f"0x{int(v):04X}"
    except Exception:
        return "?"


class CsvRecorder:
    """Streaming CSV writer: provenance header + one row per frame."""

    def __init__(self, path: str, channels: Sequence[int],
                 provenance: Optional[Iterable[str]] = None):
        self.path = path
        self.channels = list(channels)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._fh = open(path, "w", newline="", encoding="utf-8")
        for line in (provenance or []):
            self._fh.write(line + "\n")
        header = ["t_s", "frame"]
        for ch in self.channels:
            header += [f"ch{ch}_counts", f"ch{ch}_volts"]
        self._writer = csv.writer(self._fh)
        self._writer.writerow(header)
        self.rows = 0

    def write(self, t: float, index: int, counts: Sequence[float],
              volts: Sequence[Optional[float]]) -> None:
        row: List = [f"{t:.6f}", index]
        for i in range(len(self.channels)):
            c = counts[i] if i < len(counts) else ""
            v = volts[i] if i < len(volts) else None
            row.append(f"{c}" if c != "" else "")
            row.append("" if v is None else f"{v:.6f}")
        self._writer.writerow(row)
        self.rows += 1

    def close(self) -> None:
        try:
            self._fh.flush()
            self._fh.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
