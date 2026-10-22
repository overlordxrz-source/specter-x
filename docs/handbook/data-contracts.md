# Observation, provenance, time, calibration and uncertainty contracts

[Hub](../README.md) · **Baseline code versus proposed stronger contract.**

## Existing contract

The current [Measurement / Provenance dataclasses](../../specter/fusion/measurement.py) carry `sensor`, `kind`, `t_host`, optional `t_sensor`, `frame_id`, `value`, `confidence`, `covariance`, an ID and provenance fields `sensor_id`, `source`, `algorithm`, optional `model_version`, `frame_index`, `parents` and `notes`.

At this snapshot construction requires sensor and frame identifiers, checks source/sensor agreement, constrains confidence to [0,1], and checks covariance shape/symmetry. Those checks do **not** establish finite timestamps, physical units, a positive-semidefinite covariance or calibrated confidence. Serialization support is not comprehensive scientific validation.

`t_host` uses `time.time()`: it is wall-clock time and can step. The source comment “monotonic-ish” must not be interpreted as a monotonic guarantee. Proposed fields below are not already implemented and must not be injected into the existing schema without versioned compatibility work.

## Epistemic state is separate from origin and confidence

The [canonical doctrine](north-star.md) requires measured, inferred, predicted, simulated and unknown to remain distinguishable at observation, skeletal-joint, track and rendered-inference level. A real camera image is measured input; model-generated keypoints are inferred, extrapolated joints are predicted, and absent depth can leave metric position unknown. Replayed hardware data retains its acquisition origin and adds replay status. These semantics are required design direction; the baseline dataclass does not enforce a complete per-value state field. Add them through a versioned contract, not an undocumented payload convention.

## Proposed vNext envelope

| Group | Required meaning |
|---|---|
| Identity | schema version, observation ID, session, unit, device instance and boot ID, producer sequence |
| Observation | kind, dimensions, explicit SI units or documented native unit, frame ID, finite payload or explicit invalid mask |
| Provenance | raw artifact/hash, parent IDs, software commit, model hash, configuration hash and preprocessing version |
| Time | sensor tick and tick unit/width, host receive monotonic time, UTC estimate, clock-map version and uncertainty |
| Calibration | calibration ID/hash, device identity, method, reference traceability, validity interval and conditions |
| Quality | real/simulated/replayed origin, calibrated/nominal/unknown validity, stale/occluded/drop/overflow reasons |
| Uncertainty | state variable ordering and units; covariance or empirical interval with method and assumptions |
| Privacy | session consent scope, retention class and allowed recipients; private registry reference instead of personal details |

Illustrative proposal, not a runnable baseline message:

```json
{
  "schema": "specter.observation.vNext-draft",
  "id": "sessionA-nodeA-daq0-boot1-42",
  "origin": "hardware",
  "kind": "analog_voltage",
  "value": {"channel": 0, "voltage": 1.23, "unit": "V"},
  "frame_id": "daq0/channel0",
  "time": {"sensor_tick": null, "host_rx_monotonic_ns": 42000000,
           "utc_estimate": null, "clock_map_id": null, "uncertainty_s": null},
  "calibration": {"id": "cal-example", "validity": "example_only"},
  "quality": {"usable": false, "reason": "illustrative_not_measured"},
  "provenance": {"parents": ["raw-example"], "config_hash": "example"}
}
```

## Time rules

Store receive time separately from acquisition time. Fit sensor ticks to a monotonic host clock, recording offset, drift and residuals. Map that clock to UTC separately; retain discontinuities. Counter wrap and device reboot are different events. The CSI 32-bit microsecond counter wraps in about 71.6 minutes; the DW1000 path also has a finite tick counter. Never subtract wrapped counters naïvely or bridge a reset as though time were continuous.

USB batching can put many DAQ samples at one receive time. Preserve sample index and sample-rate assumptions; do not claim per-sample UTC from burst arrival times. Cross-node synchronization, GNSS PPS and PTP/chrony are mechanisms to evaluate, not evidence that the sensors are synchronized. Reject or marginalize cross-modal associations when timing uncertainty exceeds the task's preregistered tolerance.

## Frames and calibration

Existing convention: `T_a_b` maps frame b into a: `p_a = R p_b + t`; optical axes +x right, +y down, +z forward; body axes +x forward, +y left, +z up. ENU is east/north/up relative to a declared shared anchor. Source: [frame utilities](../../specter/fusion/coordinate_frames.py) and [root conventions](../../README.md).

Each transform needs device IDs, method, residual error, uncertainty, validity and rig revision. Placeholder intrinsics in [rig.json](../../specter/calibration/rig.json) are not calibrated values. Re-mounting, lens changes, temperature excursions and firmware changes may invalidate calibration. Test inverse and composition numerically and with physical targets.

DAQ calibration needs reference values and ground/common-mode checks. Thermal temperature requires validated raw conversion, reference target and emissivity assumptions. UWB needs antenna delay and NLOS characterization. IMU calibration separates accelerometer/gyro bias, scale and magnetic disturbances. Calibration records are immutable; supersede them rather than editing history.

## Uncertainty and evidence rules

Missing covariance means unknown, never zero. Reject nonfinite payloads and invalid covariances before fusion; record the rejected artifact and reason. State confidence is not a posterior probability unless calibration demonstrates that interpretation. Use task metrics and reliability diagrams for learned scores; use residual-based covariance assessment for physical estimators.

Do not independently fuse two reports that share raw parents as though they were independent evidence. Track lineage and correlation; use conservative methods or defer association when cross-correlation is unknown. Project an image skeleton into 3D only with valid depth/geometry and propagate uncertainty. Presence-only CSI must not acquire a precise point by being fused with an unrelated camera person.

VIEW must show observation time, age, source and validity on inspection. Missing coverage and sensor disagreement remain visible. Prediction-only tracks expire under a stated policy; they do not turn into continuing observations.
