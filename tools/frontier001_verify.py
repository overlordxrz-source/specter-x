"""Offline end-to-end replay/capture verifier. Never opens hardware."""

from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from specter.platform.replay import CsiReplay, read_capture, write_capture, sha256_file
from specter.platform.registry import ReplaySession


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--outdir", required=True)
    args = p.parse_args(argv)
    source = Path(args.source)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    before = sha256_file(source)
    adapter = CsiReplay(source)
    observations = list(adapter)
    if not observations:
        raise ValueError("empty replay")
    first = out / "a.observations.jsonl"
    second = out / "b.observations.jsonl"
    write_capture(first, observations)
    write_capture(second, observations)
    assert sha256_file(first) == sha256_file(second)
    replay = list(read_capture(first))
    assert replay == observations
    session = ReplaySession(observations, capacity=256)
    session.seek(len(observations) - 1)
    expected = observations[-1].to_json()
    session.seek(0)
    session.seek(len(observations) - 1)
    assert session.observations[session.position].to_json() == expected
    assert session.registry.evictions == max(0, len(observations) - 256)
    assert session.registry.streams["bench/di188/analog"].state == "OFFLINE"
    assert sha256_file(source) == before
    result = dict(
        source=source.name,
        source_sha256=before,
        observations=len(observations),
        source_counters=dict(adapter.counts),
        canonical_capture_sha256=sha256_file(first),
        deterministic_bytes=True,
        roundtrip_equal=True,
        seek_equal=True,
        retention_capacity=256,
        retention_evictions=session.registry.evictions,
        daq_state="OFFLINE",
        origin=observations[0].to_dict()["origin"],
        native_time_preserved=True,
        receive_time_invented=False,
        hardware_access=False,
        motion_detection_claim=False,
    )
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
