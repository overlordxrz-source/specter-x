# Sensor and fusion research program

[Hub](../README.md) · **All performance goals here are proposed. No new sensing result is claimed.**

> **Edition 2 reconciliation:** Project intent follows the [canonical charter](north-star.md). Local code links below still target `77abdd0`; newer Alpha `95eae17` source/build/simulation status is recorded in the [separate review](alpha-95eae17-review.md), without a merge. Reported builds and 261 tests do not establish flashed or hardware-validated firmware.

## Observability before fusion

Each modality measures a different physical quantity. A camera keypoint, a thermal region, a radar point and a change in a radio channel are not interchangeable sightings of a named person. Start with an observation model, expected failure modes and an independent reference. Add an inference only after a held-out experiment supports it.

| Modality | Useful observable / intended role | Main limits and experiment |
|---|---|---|
| Low-light optical | Image texture, 2D keypoints, bearings | Needs light; motion blur, occlusion and model bias. Calibrate camera, then compare pose against annotated/reference frames |
| Camera depth / stereo | Metric depth tied to pixels; skeleton geometry | Stereo needs baseline/texture; active depth can suffer sunlight, reflections and interference. Model and interface undecided; compare to physical surveyed targets |
| Thermal | LWIR radiance / apparent surface temperature and regions | Emissivity, reflections, drift and occlusion; test reference targets and heated geometric calibration rig |
| 60-GHz radar | Range, radial velocity, angular information and phase under the selected waveform/processing | Multipath, ghost detections, finite aperture and target aspect; reference distances, motion and angle sweeps |
| LiDAR | Optical range and geometric structure | Weather, surface reflectivity, glass, occlusion and scan distortion; reference geometry and motion correction |
| GNSS | Outdoor position/time under reception conditions | Indoor/urban reception and multipath; compare to surveyed route, retain fix quality and uncertainty |
| IMU | Acceleration and angular rate; orientation estimates | Bias/drift, vibration and magnetic disturbance; no unbounded dead-reckoning accuracy from IMU alone |
| UWB | Inter-device time-of-flight ranges | Anchor geometry, antenna delays and NLOS bias; compare measured LOS/NLOS ranges; no universal centimeter claim |
| Wi-Fi CSI | Complex received-channel response and changes | Traffic, channel, rate, AGC, oscillator offsets and multipath; controlled Tx/Rx geometry and independent activity labels |
| Acoustic / event / gas | Directional audio, brightness-change events, selected environmental chemistry | Experimental stubs; each needs its own calibration, artifact controls and privacy policy |

Thermal cameras observe surface effects rather than arbitrary interiors; [FLIR's explanation](https://www.flir.com/en-gb/discover/home-outdoor/can-thermal-imaging-see-through-walls/) distinguishes walls/glass and the observed surface. [TI's IWR6843AOP page](https://www.ti.com/product/IWR6843AOP) identifies a 60–64-GHz radar part; that specification is not a through-wall performance guarantee. [NIST's UWB measurements](https://www.nist.gov/ctl/wireless-networks-division/ultra-wideband-location) emphasize building/material and multipath conditions. No equipment choice alone resolves these constraints.

## Skeletons and scene understanding

First milestone: optical 2D skeletons with source, model version and keypoint confidence. Next: metric 3D pose from calibrated depth or multi-view geometry, evaluated for occlusion, limb error and frame latency. Thermal may support coarse human-region association where a trained and validated model exists. Radar/CSI skeleton reconstruction would require a separately validated inference model and suitable hardware; it is not a parser feature or a consequence of fusion.

A rendered skeleton can be physically plausible yet wrong. Preserve observed joints, inferred joints and missing joints separately. Evaluate held-out people, clothing, distance, pose and lighting. Do not use identity labels by default. A prior skeleton must not continue moving through an obstruction as though new joints were observed.

## Fusion sequence

1. Optical plus depth/range: validate metric geometry and reprojection on static targets.
2. Optical plus thermal: calibrate independent optics and thermal drift; measure association accuracy across contrast and occlusion.
3. Radar plus optical/depth: compare range/Doppler support to optical-only tracking, with distractors and deliberate time offsets.
4. GNSS/UWB/IMU: estimate unit pose with declared anchor and growing uncertainty during loss of reference.
5. CSI: first attach a scene-level RF-change feature to the correct spatial/temporal support; only localize if geometry and experiments support it.
6. Distributed fusion: avoid double-counting peer reports of the same raw observations. Evaluate synchronization and communication loss explicitly.

Prefer the smallest estimator that matches the observable. Kalman-style estimation needs stated state, dynamics, noise assumptions and association rules. Learned fusion needs training provenance and splits by independent session/person/site; adjacent windows from the same recording must not leak into both train and test.

## Through-obstruction inference — unproven research track

Question: under which specified materials, thicknesses, layouts and geometries can a sensor distinguish a controlled change from nuisance variation? Separate detection, counting, localization, pose and identity: they are different tasks with different information requirements.

Start with an empty-scene control, one consenting participant or mechanical target, fixed transmitter/receiver and independently logged labels. Compare no barrier, a documented barrier, RF-blocking control where appropriate, moved furniture, fan motion and platform motion. Hold out entire sessions and layouts. Report sensitivity at a fixed false-alarm rate, false alarms/hour, detection latency, localization error where meaningful and abstention/coverage.

60 GHz must not be assumed to penetrate a building usefully because Wi-Fi sometimes does. Material loss and multipath must be measured at the actual frequency and geometry. A positive result behind one panel establishes only that condition. No barrier result is sufficient for rescue, rubble searches or an “empty room” conclusion. No covert or non-consensual trials are part of this program.

## SPECTER-BIO: non-contact respiration and cardiac motion

Begin with a driven motion phantom and a known displacement/time reference. Establish the instrument's detectable displacement versus frequency, distance, aspect, traffic and motion artifacts. Record complex samples if available; phase needs oscillator/common-phase handling and amplitude can also respond through multipath. Avoid claiming either channel is inherently sufficient or impossible.

Simple reflection/path-length relationships are geometry dependent: monostatic reflected phase and bistatic Wi-Fi paths have different displacement sensitivity. A long path alone does not supply a non-detection proof. Compute the selected geometry and then test coupling and noise empirically. Existing campus CSI is an unsuitable controlled validation apparatus, not a proof of universal infeasibility.

For respiration, compare to a synchronized respiratory reference, with quality rejection and deliberate body/rig motion. For cardiac motion, use an appropriate independently timed physiological reference chosen with laboratory expertise; ECG and peripheral pulse are different signals with different timing. Any body-connected equipment must be approved for that use. Report rate error, waveform timing where relevant, valid-time coverage and artifact rejection. No diagnosis, medical monitoring or life detection is claimed.

[TI's vital-sign lab](https://www.ti.com/video/5428037798001) illustrates seated chest-motion measurements; its [IWR6843 example](https://dev.ti.com/tirex/explore/content/radar_toolbox_4_00_00_05/source/ti/examples/Industrial_and_Personal_Electronics/Vital_Signs/Vital_Signs_With_People_Tracking/docs/vital_signs_with_people_tracking_user_guide.html) describes vendor-specific tracking/vitals output. Those examples motivate feasibility experiments; they do not validate SPECTER hardware, performance or use behind debris.

## SPECTER-BIO: quantum magnetometry — long-term laboratory research

Optically pumped magnetometers measure magnetic fields using atomic-spin physics; magnetocardiography concerns cardiac magnetic signals. This is different from radar displacement sensing and does not follow from the existing IMU magnetometer. A compact sensor does not make the environment magnetically quiet.

A [NIST microfabricated magnetic gradiometer study](https://www.nist.gov/publications/microfabricated-optically-pumped-magnetic-gradiometer) provides a concrete instrument reference. A [2026 research preprint on ambient magnetocardiography](https://arxiv.org/abs/2602.14264) is a literature lead, not an independently verified portable SPECTER capability. Neither source establishes a military device with the range or performance mentioned in the prior conversation; that story remains unverified.

Begin with a university lab partner, a documented sensor noise spectrum and calibrated test coil. Characterize shielding/active compensation needs, environmental noise, magnetic materials, motion, vibration, separation and synchronized reference signals. Only then consider consent-based biomagnetic work. A coil-detection experiment does not establish cardiac detection, and near-field laboratory cardiac detection would not establish remote through-obstruction detection. Keep this track off the near-term portable-unit critical path.
