#!/usr/bin/env python3
"""Mutation gate: prove the regression tests actually constrain the fixes.

A test suite can pass while the defect it is supposed to prevent is silently
reintroduced. This tool copies the analysis and acquisition code into a
scratch tree, injects one specific historical defect at a time, runs the
test that is supposed to catch it, and requires that test to **fail**.

A mutation that survives (the tests still pass) is reported as a gate
failure. That is the difference between "the tests pass" and "the tests
enforce".

    python3 tools/mutation_check.py
    python3 tools/mutation_check.py --keep    # inspect the scratch trees

Exit status is 0 only when every mutation is killed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Each entry injects one defect the audit found, and names the test that
#: must fail because of it.
MUTATIONS = [
    {
        "name": "held-out scaler fitted on the test fold",
        "file": "specter/sensors/esp32/analysis.py",
        "old": "    Zte = (test_X - mu) / sd           # transform uses train statistics only",
        "new": "    Zte = _zscore(test_X)",
        "test": "tests/test_analysis_leakage.py"
                "::test_a_held_out_prediction_cannot_depend_on_another_test_sample",
    },
    {
        "name": "tied AUC ranked in argument order",
        "file": "specter/sensors/esp32/analysis.py",
        "old": "        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0",
        "new": "        ranks[order[i:j + 1]] = np.arange(i + 1, j + 2)",
        "test": "tests/test_analysis_leakage.py::test_tied_scores_give_auc_one_half",
    },
    {
        "name": "constant separated groups reported as no effect",
        "file": "specter/sensors/esp32/analysis.py",
        "old": '        return 0.0 if diff == 0 else math.copysign(float("inf"), diff)',
        "new": "        return 0.0",
        "test": "tests/test_analysis_leakage.py"
                "::test_perfectly_separated_constant_groups_are_infinite_not_zero",
    },
    {
        "name": "change_rate floor fitted on held-out trials",
        "file": "specter/sensors/esp32/analysis.py",
        "old": "              if j != i and parts[j] is not None",
        "new": "              if parts[j] is not None",
        "test": "tests/test_analysis_leakage.py"
                "::test_change_rate_never_uses_its_own_trial",
    },
    {
        "name": "preregistration p gate relaxed",
        "file": "tools/alpha002c_motion_v2.py",
        "old": "P_GATE = 0.01",
        "new": "P_GATE = 0.5",
        "test": "tests/test_motion_v2_prereg.py"
                "::test_the_preregistered_constants_are_frozen",
    },
    {
        "name": "preregistration confound gate removed",
        "file": "tools/alpha002c_motion_v2.py",
        "old": '    if not (out["confounds"]["rate_ok"] and out["confounds"]["phy_ok"]):',
        "new": "    if False:",
        "test": "tests/test_motion_v2_prereg.py"
                "::test_a_payload_rate_confound_is_inconclusive",
    },
    {
        "name": "preregistration validity rules skipped",
        "file": "tools/alpha002c_motion_v2.py",
        "old": "def validate_trials(trials):\n    problems = []",
        "new": "def validate_trials(trials):\n    return []",
        "test": "tests/test_motion_v2_prereg.py"
                "::test_one_invalid_trial_invalidates_the_session",
    },
    {
        "name": "boundary-uncertainty check removed",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "        elif unc > self.guard_s:",
        "new": "        elif False:",
        "test": "tests/test_adversarial_gates.py"
                "::test_high_boundary_uncertainty_invalidates_the_trial",
    },
    {
        "name": "sample-span check removed",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "        elif abs(sample_span - active) > self.span_tolerance_s:",
        "new": "        elif False:",
        "test": "tests/test_adversarial_gates.py"
                "::test_an_incomplete_window_invalidates_the_trial",
    },
    {
        "name": "uncertainty always reported as zero",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "        return lo, max(0.0, med - lo)",
        "new": "        return lo, 0.0",
        "test": "tests/test_adversarial_gates.py"
                "::test_offset_uses_the_minimum_delay_and_reports_the_spread",
    },
    {
        "name": "offset from the 10th percentile instead of the minimum",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "        lo = float(min(deltas))",
        "new": "        lo = float(np.percentile(deltas, 10))",
        "test": "tests/test_adversarial_gates.py"
                "::test_offset_uses_the_minimum_delay_and_reports_the_spread",
    },
    {
        "name": "block list not shuffled with the trials",
        "file": "specter/sensors/esp32/analysis.py",
        "old": "        blocks = [blocks[i] for i in order]",
        "new": "        blocks = list(blocks)",
        "test": "tests/test_adversarial_gates.py"
                "::test_a_passed_block_list_is_shuffled_with_the_trials",
    },
    {
        "name": "clock offset from the median (burst-sensitive)",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "        lo = float(min(deltas))",
        "new": "        lo = float(np.median(deltas))",
        "test": "tests/test_adversarial_gates.py"
                "::test_a_delivery_burst_before_go_does_not_pull_in_old_frames",
    },
    {
        "name": "device reset treated as ordinary jitter",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "                elif back > RESET_THRESHOLD_US:",
        "new": "                elif False:",
        "test": "tests/test_adversarial_gates.py"
                "::test_a_device_clock_reset_invalidates_the_trial",
    },
    {
        "name": "held-out features fitted on the test block",
        "file": "specter/sensors/esp32/analysis.py",
        "old": "        fitted = extract_features(trials, stationary_label, fit_idx=train)",
        "new": "        fitted = extract_features(trials, stationary_label, fit_idx=None)",
        "test": "tests/test_adversarial_gates.py"
                "::test_a_test_block_trial_cannot_change_another_test_trial",
    },
    {
        "name": "late in-window frames not counted",
        "file": "specter/sensors/esp32/acquisition.py",
        "old": "                    w[\"late\"] += 1",
        "new": "                    pass",
        "test": "tests/test_adversarial_gates.py"
                "::test_late_in_window_frames_are_counted_by_settle",
    },
    {
        "name": "permutation does not rebuild the supervised feature",
        "file": "specter/sensors/esp32/analysis.py",
        "old": "        vals = _feature_values(inv, parts, pl, feature)",
        "new": "        vals = _feature_values(inv, parts, labels, feature)",
        "test": "tests/test_analysis_leakage.py"
                "::test_every_permutation_passes_permuted_labels_to_the_supervised_feature",
    },
]


def _copy_tree(dst: str) -> None:
    for name in ("specter", "tests", "tools"):
        shutil.copytree(os.path.join(REPO, name), os.path.join(dst, name),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(os.path.join(REPO, "pytest.ini"),
                 os.path.join(dst, "pytest.ini")) if os.path.exists(
        os.path.join(REPO, "pytest.ini")) else None


def _run(test: str, cwd: str) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = cwd
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
        cwd=cwd, env=env, capture_output=True, text=True).returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    failures = []
    for m in MUTATIONS:
        tmp = tempfile.mkdtemp(prefix="specter-mutation-")
        try:
            _copy_tree(tmp)
            path = os.path.join(tmp, m["file"])
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            if m["old"] not in src:
                failures.append((m["name"], "mutations no longer apply: marker missing"))
                continue
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src.replace(m["old"], m["new"], 1))
            rc = _run(m["test"], tmp)
            if rc == 0:
                failures.append((m["name"], "SURVIVED - the test still passes"))
            else:
                print(f"  killed: {m['name']}")
        finally:
            if args.keep:
                print(f"    kept {tmp}")
            else:
                shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print("MUTATION GATE: FAIL")
        for name, why in failures:
            print(f"  - {name}: {why}")
        return 1
    print(f"MUTATION GATE: PASS ({len(MUTATIONS)} defects re-injected, all caught)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
