#!/usr/bin/env python3
"""Read-only verification of the Shrike Lite FPGA heartbeat source/IO plan.

This script never opens a serial port, runs a programmer or writes a bitstream.
It checks the frozen source hash and expected ForgeFPGA IO-planner mapping. If a
generated bitstream is supplied, it prints/compares its hash and requires the
manifest to contain a reviewed expected hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "firmware/shrike_lite/fpga/proof_of_life/verification.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(source: Path, manifest: dict, bitstream: Path | None) -> list[str]:
    errors: list[str] = []
    if not source.is_file():
        return [f"source missing: {source}"]
    text = source.read_text(encoding="utf-8")
    actual_source_hash = sha256(source)
    if actual_source_hash != manifest.get("source_sha256"):
        errors.append(
            f"source hash mismatch: {actual_source_hash} != {manifest.get('source_sha256')}"
        )
    if manifest.get("top_attribute") not in text:
        errors.append("missing required top attribute")
    if f"module {manifest.get('module')}" not in text:
        errors.append("module name mismatch")
    for port in manifest.get("ports", []):
        if port not in text:
            errors.append(f"missing expected port: {port}")
    if not manifest.get("io_planner"):
        errors.append("IO planner mapping is empty")

    if bitstream is not None:
        if not bitstream.is_file():
            errors.append(f"bitstream missing: {bitstream}")
        elif bitstream.name != manifest.get("bitstream_name"):
            errors.append(
                f"bitstream name {bitstream.name!r} != expected "
                f"{manifest.get('bitstream_name')!r}"
            )
        else:
            actual_bitstream_hash = sha256(bitstream)
            expected = manifest.get("bitstream_sha256")
            print(f"bitstream_sha256={actual_bitstream_hash}")
            print(f"bitstream_size={bitstream.stat().st_size}")
            if not expected:
                errors.append(
                    "manifest bitstream_sha256 is unset; build hash must be reviewed/frozen"
                )
            elif actual_bitstream_hash != expected:
                errors.append("bitstream hash mismatch")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_MANIFEST.parent / "main.v")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--bitstream", type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = verify(args.source, manifest, args.bitstream)
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 1
    print(f"source_sha256={sha256(args.source)}")
    print("io_planner=" + json.dumps(manifest["io_planner"], sort_keys=True))
    if args.bitstream is None:
        print("bitstream_check=SKIPPED (not built)")
    print("verification=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
