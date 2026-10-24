"""Independent offline CSI cross-check and disk-index responsiveness benchmark."""

from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import platform
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from specter.world.store import WorldStore
from specter.platform.observation import Observation
from specter.platform.replay import write_capture


def run(source, outdir, large_records=50000):
    outdir.mkdir(parents=True, exist_ok=False)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    independent = []
    # Intentionally does not call CsiParser/CsiReplay or FRONTIER's amplitude code.
    with source.open() as f:
        for line_no, line in enumerate(f, 1):
            if not line.startswith("CSI_DATA,"):
                continue
            row = next(csv.reader([line]))
            try:
                seq = int(row[1])
            except ValueError:
                continue
            iq = json.loads(row[24])
            amps = [
                math.sqrt(iq[i] ** 2 + iq[i + 1] ** 2) for i in range(0, len(iq), 2)
            ]
            if int(row[23]):
                amps[:2] = [None, None]
            independent.append(
                dict(
                    seq=seq,
                    tick=int(row[18]),
                    rssi=int(row[3]),
                    sig_len=int(row[20]),
                    line=line_no,
                    amplitudes=amps,
                )
            )
    s = WorldStore()
    try:
        start = time.perf_counter()
        s.load(source)
        latencies = []
        while s.worker.is_alive():
            t = time.perf_counter()
            s.snapshot()
            latencies.append(time.perf_counter() - t)
            time.sleep(0.03)
        d = s.snapshot()
        assert d["status"] == "READY", d["error"]
        assert d["count"] == len(independent)
        for index in (0, len(independent) // 2, len(independent) - 1):
            observed = s.snapshot(index=index)["observation"]
            reference = independent[index]
            assert observed["seq"] == reference["seq"]
            assert observed["acquisition"]["ticks"] == reference["tick"]
            assert observed["received"]["time_ns"] is None
            assert observed["evidence"]["raw"]["sha256"] == before
            assert observed["evidence"]["raw"]["line"] == reference["line"]
            for actual, expected in zip(
                observed["value"]["amplitudes"], reference["amplitudes"]
            ):
                assert (
                    actual is None
                    if expected is None
                    else math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
                )
            assert observed["value"]["rssi_dbm"] == reference["rssi"]
            assert observed["value"]["sig_len_bytes"] == reference["sig_len"]
        s.control("seek", len(independent) - 1)
        end = s.snapshot()
        assert end["health"]["source_missing"] == 0
        result = dict(
            source=source.name,
            source_sha256=before,
            independent_count=len(independent),
            count_matches=True,
            sample_indices=[0, len(independent) // 2, len(independent) - 1],
            iq_independent_route=True,
            native_ticks_and_raw_line_match=True,
            origin=end["observation"]["origin"],
            live_verified=end["live_verified"],
            load_seconds=d["load_seconds"],
            max_snapshot_seconds_during_load=max(latencies, default=0),
            source_missing=end["health"]["source_missing"],
            source_counters=end["counters"],
            index_bytes=s.path.stat().st_size,
            hardware_access=False,
        )
        prototype = end["observation"]
    finally:
        s.close()
    if large_records:
        capture = outdir / "synthetic-stress.observations.jsonl"

        def synthetic():
            for i in range(large_records):
                d = json.loads(json.dumps(prototype))
                d["id"] = f"synthetic-stress:{i}"
                d["seq"] = i
                d["origin"] = "simulated"
                d["classification"] = "simulated"
                d["evidence"]["level"] = "simulated"
                d["acquisition"].update(
                    ticks=i * 1000, unwrapped_ticks=i * 1000, wrap_bits=None
                )
                d["dropped_before"] = 0
                yield Observation(d)

        write_capture(capture, synthetic())
        s = WorldStore(max_records=large_records)
        try:
            s.load(capture)
            latencies = []
            while s.worker.is_alive():
                t = time.perf_counter()
                s.snapshot()
                latencies.append(time.perf_counter() - t)
                time.sleep(0.03)
            assert s.status == "READY", s.error
            s.control("seek", large_records - 1)
            d = s.snapshot()
            assert (
                d["count"] == large_records
                and len(d["rows"]) == 80
                and len(d["series"]) == 160
            )
            assert d["health"]["buffer_evictions"] == large_records - 256
            assert d["observation"]["origin"] == "simulated" and not d["live_verified"]
            result["synthetic_stress"] = dict(
                records=d["count"],
                load_seconds=s.elapsed,
                max_snapshot_seconds_during_load=max(latencies, default=0),
                index_bytes=s.path.stat().st_size,
                retention_evictions=d["health"]["buffer_evictions"],
                rows=len(d["rows"]),
                series=len(d["series"]),
            )
        finally:
            s.close()
        capture.unlink()
        Path(str(capture) + ".manifest.json").unlink()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    result["source_unchanged"] = True
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["process_peak_rss_bytes"] = (
        peak if platform.system() == "Darwin" else peak * 1024
    )
    (outdir / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--large-records", type=int, default=50000)
    a = p.parse_args()
    run(a.source, a.outdir, a.large_records)
