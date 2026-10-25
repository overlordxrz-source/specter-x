"""Read-only, isolated probes of the exact pending PR snapshots.

No application module is imported by the parent process. Each child imports
only its selected checkout, opens no devices and disables bytecode writes.
Output is observations, not an automatic approval or a hardware claim.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PROBES = {
    "team": r'''
import json, math
import numpy as np
from specter.fusion.team import TeamFuser
from specter.net.messages import TrackReport
def peer(t=100., mids=("peer",), confidence=.8):
    return TrackReport("peer", 1, t, 1, [0,0,0], np.eye(3),
        measurement_ids=list(mids), confidence=confidence)
f = TeamFuser("local")
f.ingest_report(peer(1.), clock_offset_s=0.)
stale_rejected = f.fuse(100.) == []
f = TeamFuser("local")
f.add_local(1,[0,0,0],np.eye(3),"camera",["shared"],t_host=100.)
f.ingest_report(peer(mids=("shared",)),clock_offset_s=0.)
t, = f.fuse(100.)
shared_cov = float(t.covariance[0,0])
f = TeamFuser("local")
f.ingest_report(peer(confidence=float("nan")),clock_offset_s=0.)
t, = f.fuse(100.)
print(json.dumps(dict(stale_rejected=stale_rejected,
    shared_covariance_xx=shared_cov,
    direct_api_nan_confidence_accepted=math.isnan(t.confidence))))
''',
    "gnss": r'''
import json
from specter.sensors.gnss.neom9n import Neom9nDriver, build_nav_pvt, ubx_checksum
from specter.localization.ekf import PoseEKF
def ubx(flags):
    frame=build_nav_pvt(lat_deg=47,lon_deg=8,height_m=400)
    payload=bytearray(frame[6:-2]); payload[21]=flags
    return frame[:6]+bytes(payload)+ubx_checksum(1,7,bytes(payload))
def accepts(m):
    f=PoseEKF("review")
    try:
        p=f.update_gnss(m)
        return dict(accepted=True,mode=p.mode,anchor=list(p.anchor))
    except ValueError as e:
        return dict(accepted=False,error=str(e))
driver=Neom9nDriver()
invalid=accepts(driver.feed(ubx(0))[0])
valid=accepts(driver.feed(ubx(1))[0])
bad_checksum=accepts(driver.feed_nmea(
    "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00"))
body="GPGGA,123519,4807.038,N,01131.000,E,99,08,0.9,545.4,M,46.9,M,,"
checksum=0
for character in body: checksum ^= ord(character)
unknown_quality=accepts(driver.feed_nmea("$"+body+"*"+format(checksum,"02X")))
f=PoseEKF("review")
m=driver.feed(ubx(1))[0]; m.t_host=1000.; f.update_gnss(m)
before=float(f.P[0,0]); f.update_gnss(m); after=float(f.P[0,0])
print(json.dumps(dict(gnssFixOK_clear=invalid,gnssFixOK_set=valid,
    invalid_nmea_checksum=bad_checksum,nmea_unknown_quality_99=unknown_quality,
    duplicate_fix_covariance_before=before,duplicate_fix_covariance_after=after)))
''',
    "radar": r'''
import json,struct
from pathlib import Path
from specter.sensors.radar.tlv import RadarFrameStream,parse_frame
good=Path("tests/fixtures/radar/iwr6843aop_oob_points_2.bin").read_bytes()
bad=bytearray(good[:40]); struct.pack_into("<I",bad,12,4096)
stream=RadarFrameStream()
initial=stream.feed(bytes(bad)+good)
later=stream.feed(good*10)
complete=stream.feed(bytes(4096))
print(json.dumps(dict(reference_parses=parse_frame(good) is not None,
    complete_frames_after_corrupt_length=len(initial),
    complete_frames_after_ten_more=len(later),
    recovered_after_4096_extra_bytes=len(complete))))
''',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PROBES:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    results = {}
    for name, code in PROBES.items():
        root = getattr(args, name).resolve()
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(root))
        child = subprocess.run(
            [sys.executable, "-c", code], cwd=root, env=env,
            text=True, capture_output=True, check=True, timeout=30,
        )
        results[name] = dict(head=head, probes=json.loads(child.stdout))
    print(json.dumps(results, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
