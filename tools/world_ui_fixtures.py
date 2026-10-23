"""Create explicitly synthetic/faulted browser test controls, never real observations."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from specter.platform.observation import Observation
from specter.platform.replay import CsiReplay, write_capture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    a.outdir.mkdir(parents=True, exist_ok=False)
    line = json.loads(
        (ROOT / "tests/fixtures/esp32_csi/phone_station_lltf.jsonl")
        .read_text()
        .splitlines()[0]
    )["line"]
    original = a.outdir / "fixture-input.raw.csi"
    original.write_text(line + "\n")
    d = next(iter(CsiReplay(original))).to_dict()
    d.update(origin="simulated", classification="simulated")
    d["evidence"]["level"] = "simulated"
    write_capture(a.outdir / "synthetic-control.observations.jsonl", [Observation(d)])
    fields = line.split(",")
    fields[1] = str(int(fields[1]) + 2)
    fields[18] = str(int(fields[18]) + 100000)
    (a.outdir / "quality-control.raw.csi").write_text(
        line + "\n" + ",".join(fields) + "\nCSI_DATA,broken\n"
    )
    (a.outdir / "broken-control.raw.csi").write_text("CSI_DATA,broken\n")
    original.unlink()
    print(a.outdir)


if __name__ == "__main__":
    main()
