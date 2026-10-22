#!/usr/bin/env python3
"""Find transport-integrity events in a preserved raw CSI stream.

The audit of checkpoint 020 left one class of defect deliberately open: the
USB stream can lose bytes *inside* a line, so a record is truncated and the
next record's text is concatenated onto it without a newline. The parser
survives this (``feed_resilient`` recovers the second record when it is a CSI
record), but the first record is lost and the wire format carries no
checksum, so the loss is not always detectable.

This tool does not fix anything. It measures:

* each malformed CSI line, with the byte context and the embedded record
  start, if any;
* whether the damaged line was CSI (data loss) or only a status line
  (diagnostic loss);
* the sequence numbers on either side, so a lost CSI record is visible as a
  gap;
* splices that did not break parsing but contain two record starts.

    python3 tools/transport_integrity.py runs/.../*.raw
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from specter.sensors.esp32.dispatcher import CsiParser  # noqa: E402

STARTS = ("CSI_DATA,", "SPECTER_STAT,")


def scan(path: str) -> dict:
    raw = open(path, "rb").read()
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    csi = [l for l in lines if l.startswith("CSI_DATA,")]
    stat = [l for l in lines if l.startswith("SPECTER_STAT,")]
    parser = CsiParser()
    malformed = []
    seqs = []
    for i, l in enumerate(lines):
        if not l.startswith("CSI_DATA"):
            continue
        try:
            rec = parser.feed(l)
            seqs.append(rec.seq)
        except ValueError as exc:
            malformed.append((i, l, str(exc)))
    # splices: a record start that is not at position 0
    splices = []
    for i, l in enumerate(lines):
        for marker in STARTS:
            idx = l.find(marker, 1)
            if idx > 0:
                splices.append((i, marker, l[:idx], l[idx:]))
                break
    gaps = [(a, b) for a, b in zip(seqs, seqs[1:]) if b != a + 1]
    return {"path": path, "bytes": len(raw), "lines": len(lines),
            "csi": len(csi), "stat": len(stat), "malformed": malformed,
            "splices": splices, "seq_gaps": gaps}


def report(r: dict) -> None:
    print(f"\n{r['path']}")
    print(f"  {r['bytes']} bytes, {r['lines']} lines, "
          f"{r['csi']} CSI, {r['stat']} STAT")
    if not r["malformed"] and not r["splices"]:
        print("  clean: no malformed CSI line, no embedded record start")
        return
    for i, line, err in r["malformed"]:
        kind = "CSI (data lost)" if line.startswith("CSI_DATA,") else "other"
        print(f"  malformed line {i} [{kind}]: {err}")
        print(f"    head: {line[:110]!r}")
        print(f"    tail: {line[-80:]!r}")
        for marker in STARTS:
            idx = line.find(marker, 1)
            if idx > 0:
                print(f"    embedded {marker!r} at byte {idx} - "
                      f"the tail may be a recoverable record")
    for i, marker, before, after in r["splices"]:
        print(f"  splice on line {i}: {marker!r} at byte {len(before)}")
        print(f"    before: {before[-60:]!r}")
        print(f"    after : {after[:60]!r}")
    if r["seq_gaps"]:
        print(f"  CSI sequence gaps: {r['seq_gaps'][:8]}"
              f"{' ...' if len(r['seq_gaps']) > 8 else ''}")
    else:
        print("  CSI sequence continuous: no record lost from the parsed set")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)
    files = []
    for p in args.paths:
        files.extend(sorted(glob.glob(p)))
    if not files:
        print("no files matched", file=sys.stderr)
        return 2
    total_bad = 0
    for p in files:
        r = scan(p)
        total_bad += len(r["malformed"])
        report(r)
    print(f"\n{len(files)} file(s), {total_bad} malformed CSI line(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
