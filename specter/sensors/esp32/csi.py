"""CSI observations as SPECTER-X Measurements.

The board streams ~178 packets/s, so logging one Measurement per packet would
bury the event log. Instead a **summary** Measurement is emitted on a fixed
cadence, and it *accounts for every packet*: the id range, the count, the
gaps and the drops are all in the payload, so no packet is silently lost.

Each summary carries the latest packet in full - its id, the device's own
timestamp, the AP, the RSSI, and the per-subcarrier amplitudes - plus the
acquisition health.

Subcarrier amplitudes
---------------------
The upstream payload is a flat list of interleaved I/Q samples (the upstream
web viewer parses it the same way), so the amplitude of subcarrier *n* is
``hypot(i_n, q_n)``. A trailing odd sample is reported, not silently dropped.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from specter.fusion.measurement import Measurement, Provenance

from .dispatcher import CsiRecord

#: The sensor key used in SENSOR_LABELS and Provenance.source.
SOURCE = "wifi_csi"
#: The algorithm that produced the data, as it identifies itself.
ALGORITHM = "csi_recv_router"


def subcarrier_amplitudes(iq: Sequence[int]) -> List[float]:
    """Per-subcarrier amplitude from interleaved I/Q samples."""
    out: List[float] = []
    for i in range(0, len(iq) - 1, 2):
        out.append(math.hypot(float(iq[i]), float(iq[i + 1])))
    return out


def csi_packet_value(record: CsiRecord) -> Dict:
    """The full detail of one CSI packet."""
    amps = subcarrier_amplitudes(record.iq)
    return {
        "id": record.seq,
        "ap_mac": record.mac,
        "rssi": record.rssi,
        "rate": record.rate,
        "channel": record.channel,
        "local_timestamp": record.local_timestamp,
        "sig_len": record.sig_len,
        "len": record.fields.get("len"),
        "noise_floor": record.noise_floor,
        "iq_samples": len(record.iq),
        "subcarriers": len(amps),
        "amplitudes": [round(a, 1) for a in amps],
        "odd_trailing_sample": bool(record.iq) and len(record.iq) % 2 == 1,
    }


def csi_summary_measurement(record: CsiRecord, health, board_mac: str = "",
                             packets: int = 0, first_id: Optional[int] = None,
                             gaps: int = 0, missing: int = 0, malformed: int = 0,
                             dropped: int = 0, unknown_lines: int = 0) -> Measurement:
    """One Measurement summarising the packets since the last log.

    ``record`` is the most recent packet; the counters describe the whole
    window, so no packet goes unaccounted for.
    """
    value = csi_packet_value(record)
    value.update({
        "packets": packets,
        "first_id": first_id,
        "last_id": record.seq,
        "gaps": gaps,
        "missing_packets": missing,
        "malformed": malformed,
        "dropped": dropped,
        "unknown_lines": unknown_lines,
        "link_state": getattr(getattr(health, "state", None), "value", None),
        "link_detail": getattr(health, "detail", ""),
        "packets_per_s": round(getattr(health, "packets_per_s", 0.0), 2),
        "silence_s": round(getattr(health, "silence_s", 0.0), 3),
        "reconnects": getattr(health, "reconnects", 0),
        "uptime_s": round(getattr(health, "uptime_s", 0.0), 1),
    })
    prov = Provenance(
        sensor_id=board_mac or "unknown",
        source=SOURCE,
        algorithm=ALGORITHM,
        model_version=None,
        frame_index=record.seq,
        parents=(),
        notes=("CSI packet id %d, device timestamp %d us"
               % (record.seq, record.local_timestamp)),
    )
    return Measurement(
        sensor=SOURCE,
        kind="csi_summary",
        t_host=record.received_at or 0.0,
        frame_id="csi",
        value=value,
        provenance=prov,
        # the device's own clock, in seconds since its boot
        t_sensor=record.local_timestamp / 1e6 if record.local_timestamp else None,
        confidence=None,
        covariance=None,
    )
