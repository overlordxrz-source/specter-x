# FRONTIER-001 architecture review and decision

2026-10-22. Implementation base `6e6afb3`; own branch `feature/frontier001-platform`. Alpha source, frozen experiments and firmware remain owned by OpenCode.

## Inspected and reused

`fusion/measurement.py` and its tests provide the legacy mutable Measurement contract. `events/log.py` provides a wall-clock JSONL event log and presence hysteresis. `net/clock.py` estimates arrival offsets; it is not acquisition synchronization. `fusion/coordinate_frames.py` provides transforms/projection; `calibration/rig.json` has placeholder intrinsics. `sensors/base.py` supplies driver health; sensor adapters range from acquired CSI/DAQ to parser-only or experimental simulations. `hud/renderer.py`, `hud/csi_views.py` and `app.py` provide an existing OpenCV desktop application. Alpha's `dispatcher.CsiParser` and captured phone-station fixtures supply real CSI parsing. Its newer capture/statistics and checkpoint 021 are an active research track, not a foundation to modify here.

Review of interrupted work found optional FRONTIER fields added to Measurement and corresponding tests in OpenCode's checkout, initially uncommitted. That includes defaults `evidence_level=software_verified` and `valid=True`: old records could silently acquire assurance. The extension did not enforce exact schema versions, finite/PSD uncertainty or complete acquisition domains. It is preserved in that checkout and **not imported**. Later OpenCode commits may supersede that initial state; this work remains pinned independently.

## Decision — accepted within the user's supplied implementation scope

Use a separate immutable, strict `specter.observation/1.0.0` envelope. Keep legacy Measurement and its JSON unchanged. Conversion is explicit and historical records become UNKNOWN with caveats, never hardware-verified by a default. Do not overload provenance or confidence as calibration, covariance or epistemic state.

Alternatives: extending Measurement offers fewer adapter lines but risks default upgrades and coupling every Alpha call site; a wholly separate web UI/runtime would add dependencies and duplicate the existing app. Chosen: independent platform boundary plus `specter.app --console`, reusing OpenCV and the CSI parser. CORE registry/capture services and VIEW share that envelope. No spatial fusion is implemented or claimed.

The v1 contract requires source/node identity, units/frame, origin/classification, native acquisition tick/domain/epoch, nullable original receive time, explicit calibration/uncertainty/validity and raw hash/line provenance. Schema validation rejects unknown fields/versions, NaN/infinity, negative counters and invalid covariances. Returned mappings are copies; internal canonical bytes are immutable. Future changes need an explicit schema version and migration; no permissive major-version fallback.

Replay reads preserved bytes and retains their original ticks. A receive time absent in raw serial text stays null. Playback time is separate, never substituted for acquisition. Wrap/reset estimates carry inferred epoch/validity flags, not certified boot identity or synchronized time. Finite ring buffers count evictions; malformed/non-CSI records and sequence discontinuities remain visible. Capture JSONL roundtrips canonical observations without wall-clock/random IDs, making replay deterministic.

## Limits and next boundaries

No live discovery, camera, serial open, firmware, fusion, PTP or device operation in this slice. DI-188 registration is infrastructure, with OFFLINE status and historical verification cited separately. Timing alignment, calibration/extrinsics and valid uncertainties must precede real two-sensor spatial association. Sensor identity is scoped to the named recording; it is not a cryptographic device identity. Only reviewed hardware-source hashes acquire recorded-hardware origin; arbitrary parsed CSI text stays UNKNOWN. Raw hashes establish integrity, not truthful experimental labels. Ferret/Ferettux is optional future platform work, not an SDK or kernel dependency.
