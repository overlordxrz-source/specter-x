"""Five disposable PR10 mutations; no repository changes or device opens."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NODE = "specter/node/csi_capture.py"
IMU = "specter/sensors/imu/bno085.py"
MUTATIONS = [
    ("write_and_accounting", NODE, [
        ('if stream.write(data) != len(data):', 'if (stream.write(data), False)[1]:'),
        ('    """Reconcile closed files, not just the writer\'s claimed return values."""',
         '    status["raw_sha256"] = sha256_file(directory / "session.raw.csi")\n    return  # deliberate missing integrity checks'),
    ], "short_writes"),
    ("baseexception", NODE, [('except BaseException as exc:', 'except Exception as exc:')],
     "baseexception or startup"),
    ("receipt_clock", NODE, [
        ('if now < last_data:', 'if False:'),
        ('if completed < max(now, last_data):', 'if completed < now:'),
        ('next_completed < completed', 'False'),
    ], "previous_completion"),
    ("quaternion_overflow", IMU, [
        ('(TypeError, ValueError, OverflowError)', '(TypeError, ValueError)'),
    ], "nonrepresentable"),
    ("clean_gate", NODE, [
        ('    return dict(status="FAIL" if reasons else "PASS", reasons=reasons)',
         '    return dict(status="PASS", reasons=[])'),
    ], "dirty"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new results directory")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results = []
    for name, relative, replacements, selector in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="specter-pr10-mutant-") as folder:
            target = Path(folder)
            shutil.copytree(ROOT / "specter", target / "specter",
                ignore=shutil.ignore_patterns("__pycache__"))
            (target / "tests/fixtures/esp32_csi").mkdir(parents=True)
            for file in ("test_pr10_remediation.py", "fixtures/esp32_csi/phone_station_lltf.jsonl"):
                shutil.copy2(ROOT / "tests" / file, target / "tests" / file)
            source = (target / relative).read_text()
            for before, after in replacements:
                if before not in source:
                    raise ValueError(f"mutation {name} anchor absent: {before}")
                source = source.replace(before, after)
            (target / relative).write_text(source)
            run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "tests/test_pr10_remediation.py", "-k", selector], cwd=target,
                env=dict(os.environ, PYTHONPATH=str(target), PYTHONDONTWRITEBYTECODE="1"),
                capture_output=True, text=True, timeout=60)
            (args.out / (name + ".log")).write_text(run.stdout + run.stderr)
            detected = run.returncode == 1 and " failed" in run.stdout and "ERROR collecting" not in run.stdout
            results.append(dict(mutation=name, detected=detected, exit_code=run.returncode))
    (args.out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
    return 0 if all(result["detected"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
