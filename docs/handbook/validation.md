# Experiments, benchmarks, simulation and replay

[Hub](../README.md) · **Proposed validation policy; no experiment executed here.**

## Evidence ladder

A result graduates through distinct gates: source/fixture validity → real acquisition → independent calibration/reference → controlled task → held-out replication → integrated stress → field research in a declared environment. Passing a lower gate does not imply the next one. Zero observed failures is a finite observation with a denominator and interval, not a universal zero-error guarantee.

Before each experiment, confirm the intended mechanism is active using an upstream observable. For CSI, that means received qualifying frames and known traffic, not just a configured SSID. For DAQ, it means a connected and referenced input, not an open serial port. A null with no stimulus or dead acquisition is an apparatus result, not evidence against sensing.

## Acceptance matrix

| Gate / claim | Positive evidence | Deliberately wrong control it must reject | Blind spot / limitation |
|---|---|---|---|
| Parser understands data | Captured fixture matched against pinned definition | Truncate tail, corrupt length/type and invalid-sample flags | Does not prove physical calibration |
| Acquisition is complete | Producer IDs/counters versus received records, declared run duration | Inject dropped/duplicate/torn records or starve host | Consecutive emitted IDs do not prove no missed RF frames before callback |
| DAQ voltage is meaningful | Multiple independently measured reference points | Floating input, wrong scale and missing ground | Reference accuracy/common mode may dominate |
| Thermal conversion is valid | Reference targets across chosen range | Wrong raw frame half/units, reflective target | Does not validate people detection or other emissivities |
| Timing is usable | Clock-fit residuals and independently timed event | Wrap, reboot, UTC step and injected skew | Clock sync is not sensor exposure synchronization |
| Frame alignment is correct | Physical reprojection / surveyed target residuals | Wrong axes, inverse transform, meters/mm mismatch | One pose may hide geometric degeneracy |
| Motion inference works | Randomized independently labeled trials | Empty room, shuffled labels, fan/rig motion | Labels may be imperfect; a single room is not generalization |
| Fusion improves a task | Prespecified held-out improvement over best single sensor | Wrong time alignment, duplicate shared evidence, removed modality | A visually smoother display can still be less accurate |
| Vitals signal is physiological | Phantom first, then synchronized appropriate references | Empty scene, vibrating target/rig and motion artifacts | Rate agreement alone can be coincidental |
| LINK rejects invalid traffic | Authentic fresh peer accepted | Tamper, stale/replay, wrong identity/key and receiver reboot | Current HMAC does not provide confidentiality or insider isolation |
| VIEW tells the truth | Source/time/quality visible | SIM input, stale prediction, sensor disconnect | Good labels cannot repair an invalid estimator |

When implementing gates, include an executable negative control (for example `test_<gate>_negative_control`) and record its failure on the wrong case. These are future engineering requirements; this docs task adds no runtime tests.

## CSI experiment card

**Question:** Can a fixed feature/procedure distinguish predefined movement conditions on an owned link at a useful false-alarm rate?

**Before capture:** freeze primary endpoint, preprocessing, time windows, thresholds and exclusion rules. Declare the useful effect or operating point for power planning. Record hardware, firmware, channel, bandwidth, rate/MCS, gain state, traffic generator, antenna orientation, room/materials, participant/target geometry and clock mapping. Verify capture continuity first.

**Design:** randomize condition order and record seed. Use matched quiet baselines, independently recorded labels and repeated sessions. Freeze analysis before labels are revealed where feasible. Include a positive mechanical/large-motion control and nuisance/empty-room controls. Select trial count using realistic simulation and uncertainty; do not treat the previous seven-per-condition suggestion as settled power analysis.

**Analysis:** split by independent trial/session/person/site, not adjacent packet windows. Report prespecified detection metrics, effect intervals, permutation assumptions and null distribution, missingness, false alarms/hour, latency and abstention. Small-sample pairwise Cohen's d is not independently convincing evidence. Account for multiple features and threshold selection.

**Exclusions:** predeclare transport, association and PHY-change criteria and report every excluded trial. PHY behavior can be affected by activity; dropping all changed-rate trials can create selection bias. Compare exclusion sensitivity or use an agreed covariate/stratified model. “No packet gaps” is about emitted IDs unless producer-side evidence says more.

## Reference experiments

- DAQ: independently measured low-voltage source, physical board/ground confirmation, two-point fit plus separate check points, uncertainty and drift. Keep floating-input negative control.
- Geometry: surveyed stationary targets, varied range/angle/depth and frame/timing perturbations. Calibrate on one set and evaluate another.
- UWB/GNSS/IMU: outdoor reference route, indoor LOS/NLOS distances, anchor geometry and deliberate reference outages; report error tails and uncertainty coverage.
- Obstruction: documented material/thickness, controlled positions, nuisance variation, blocked-path control and held-out layouts; no extrapolation to arbitrary walls.
- Vitals: known displacement rig before people; synchronized references, empty-scene and mechanical controls, motion rejection and valid-time coverage.
- Portability: startup/peak/steady power, enclosure temperature, RF obstruction by enclosure/body, cable strain, storage pressure and recovery after loss of link or power.

## Simulation scope and replay

Existing [synthetic CSI link](../../specter/sensors/esp32/synthetic_link.py), sensor simulators and [team demo](../../specter/sim/team.py) support known-ground-truth pipeline checks. Sweep independent seeds and model variants; train/tune on one set and evaluate another. Report sensitivity and null results with counts and intervals. A finite simulator sweep cannot establish real RF sensitivity, universality or a true zero FPR.

Use replay to isolate software changes on fixed inputs. Log original acquisition time, receive time and replay time separately. Freeze configuration, calibration, model and raw hashes. Match supported outputs within declared tolerance and explain nondeterminism. Replaying labels or ground-truth synthetic joints through the UI is a display test, not pose-estimation accuracy.

A physical reference supplies ground truth with uncertainty; a real link is not inherently ground-truth-free. Keep simulation assumptions explicit and test which assumptions real data violate.

## Run manifest and report template

Every accepted run needs: claim/status; question and frozen protocol; commit/dirty diff; device/boot/firmware identity; raw/config/model/calibration hashes; environment/geometry; start/end and clock mapping; seeds and labels; reference instrument and uncertainty; received/produced/dropped/malformed counts; excluded and failed trials; controls; analysis version; metrics with denominators/intervals; blind spots; conclusion limited to the tested regime.

Use **PROVEN** only for a logically established statement under explicit hypotheses; **MEASURED** for an observed metric with artifacts and passed controls; **CONJECTURED** for an untested explanation or extrapolation. The hub's richer labels describe source/readiness and do not promote a historical record into a newly measured result.

## Stop and release rules

Stop interpretation when reference signals are missing, clock/units are invalid, nonfinite values appear, mechanism activity is unconfirmed or controls do not behave as expected. Preserve the failed run. Corrections to instrumentation and changes to the scientific treatment must be logged separately. Do not retune a gate on its evaluation set. A candidate research result requires a second independent check before any external claim; no publication or deployment is performed by this documentation handoff.
