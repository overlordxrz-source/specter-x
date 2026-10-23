# FRONTIER-001 reproducibility and limitations

2026-10-22. Tested implementation on `feature/frontier001-platform`, based on `6e6afb3`. This report is committed with the tested source; use `git rev-parse HEAD` in this worktree for its immutable revision. This is a local implementation, not a merged or published release. The final handoff records the resulting commit ID.

## Environment and exact commands

Working directory: `/Users/overlord/sideprojects/specter-x-frontier001`. Existing Python environment: `/Users/overlord/sideprojects/specter-x/.venv/bin/python` (Python 3.11, NumPy 2.4.6, OpenCV 5.0.0). The system Python initially lacked `cv2`; using the existing project environment resolved that environment issue without installing project dependencies or modifying OpenCode's environment.

```sh
cd /Users/overlord/sideprojects/specter-x-frontier001
export PYTHONDONTWRITEBYTECODE=1
/Users/overlord/sideprojects/specter-x/.venv/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_alpha001_acceptance_real.py
/Users/overlord/sideprojects/specter-x/.venv/bin/python tools/frontier001_verify.py --source /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi --outdir /absolute/path/to/a/new/private-verification-directory
/Users/overlord/sideprojects/specter-x/.venv/bin/python -m specter.app --console --replay /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi --at 255 --console-size 800x480 --headless --save-frame /absolute/path/to/preview.png
```

The verification directory must be new: capture files are exclusive-create. The verifier materializes this finite recording for comparison; it is not the bounded UI loader or a live streaming service. UI loading separately caps records at 4,096 by default, maximum 50,000; registry history is independently bounded.

## Observed results

| Check | Result and scope |
|---|---|
| Full appropriate suite | **422 passed**, 1 inherited warning, 16.88 s |
| New FRONTIER cases | **43 cases**, included in the full suite |
| Hardware acceptance module | Explicitly excluded, including collection; it can open a physical DI-188 |
| Preserved real CSI source | 7,290 observations; 299 non-CSI lines; zero missing source sequence numbers |
| Deterministic capture | Two independent exports had identical SHA-256 and canonical bytes |
| Roundtrip / seek | Every observation roundtripped identically; rebuilding after seek matched the final observation |
| Retention accounting | Capacity 256, 7,034 evictions; these are intentional retention evictions, not sensor drops |
| Time / evidence | Original native ticks retained; receive time remains unknown; reviewed source is hardware-origin |
| Other sources | DI-188 OFFLINE; future thermal UNAVAILABLE; no generated sensor feeds |
| Preview | Actual headless renders at 800×480 and 1440×900, visually inspected |
| Device access | No camera, serial port, firmware, flight control or live acquisition invoked |

Source SHA-256: `f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`.

Canonical exported capture SHA-256: `f375e0b1ff0a7c6ed4b7a2bbc8882b0347bcab17d87a2ab7524fcd2a2aa641b0`.

The raw source and canonical measurement exports remain private and are not committed. The source hash was checked before and after verification. No trial labels, motion statistics or scientific conclusions were changed or inferred from this platform replay. The old Alpha null result is not evidence that motion is impossible.

The inherited warning is NumPy's `RuntimeWarning: invalid value encountered in scalar subtract` from `tests/test_pipeline_positive_control.py`. Its test passed, but this warning is recorded rather than treated as evidence of scientifically valid nonfinite statistics. Alpha's analysis is outside this implementation scope.

## Adversarial controls

Tests reject invalid versions, missing/extra fields, duplicate JSON keys, nonfinite values, boolean/negative counters, invalid uncertainty dimensions, asymmetric or non-PSD covariance, evidence upgrades, malformed CSI, unsupported layouts, repeated sequences, false drop counts, acquisition-time reversal and source mismatches. Corrupted or truncated captures and missing manifests fail closed. Existing capture files and orphan manifests cannot be overwritten. Unknown CSI text stays UNKNOWN despite matching parser syntax. Simulated observations cannot be promoted into hardware evidence. UI tests monkeypatch the camera path to fail if called and exercise both supported display sizes, empty/offline state, provenance pages and node readiness.

These tests use inherited hardware fixture bytes plus synthetic adversarial metadata, corruptions, sequence/timing changes and covariance examples. Synthetic perturbations are software controls, not hardware validation. The separate end-to-end run above uses the entire preserved real Phase 0 recording.

## Remaining gates and safe handoff

- No live second sensor, synchronized multimodal fusion, calibrated geometry, authenticated node transport, WORLD persistence or motion inference is implemented by FRONTIER-001.
- Clock wrap/reset interpretation is conservative and flagged; no true boot ID, measured clock-map uncertainty or receive timestamps exist in this raw file.
- Native CSI amplitude metadata are preserved without claiming calibrated RF power, spatial localization, phase-based sensing or detection.
- Desktop keyboard/mouse and headless rendering are implemented. Interactive macOS window operation, physical Newhaven HDMI/USB touch and touch-only ergonomics still require user testing; a screenshot does not validate them.
- Hardware readiness is sourced from the owner's latest request and existing checkpoint history. The original complete procurement CSV is unavailable; shipment/donation confirmation does not establish delivery. Verify exact revisions and electrical requirements before acceptance work.
- OpenCode's checkout advanced independently to `e0d1247` during this task and had active uncommitted Alpha files at the final inspection. No reconciliation or merge was attempted. The isolated base remains `6e6afb3`.
- CI configuration now includes these tests, but no remote CI run, push or deployment occurred.

OpenCode can review this branch and reuse the explicit observation boundary and offline console later. Keep its frozen Alpha protocol, experimental code and firmware separate. Any migration from preliminary optional Measurement fields needs an explicit review; there is no automatic evidence upgrade or authorization to merge.
