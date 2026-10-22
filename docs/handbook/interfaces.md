# Interface control document — draft 1

[Hub](../README.md) · **Baseline compatibility plus proposed requirements.**

Interface owner roles are recommendations; individual owners are unassigned. A proposed field or acceptance condition does not modify executable behavior. Use one implementation review to ratify each version.

## ICD-01: SENSE to CORE measurement

**Owner:** sensing/runtime. Existing Python `Measurement` fields are listed in the [data contract](data-contracts.md). Preserve provenance, frame, algorithm and parents. A sensor adapter must expose data health independently of transport health. Floating, unknown, uncalibrated and simulated payloads must not masquerade as valid physical values.

Proposed vNext adds explicit units, origin, time uncertainty and calibration IDs. Add version negotiation or a compatibility adapter; do not silently add required fields to current JSONL readers. Unknown schema must fail visibly and retain the raw record for diagnosis. Acceptance: fixture roundtrip, rejected invalid payloads, simulated-origin preservation and old-session replay.

## ICD-02: ESP32 USB data and control

**Owner:** device firmware/host integration. One host reader owns each physical port. Current [dispatcher](../../specter/sensors/esp32/dispatcher.py) separates CSI, supervisor and other lines. The [current supervisor parser](../../specter/sensors/esp32/protocol.py) accepts these exact record shapes:

```text
HELLO,<proto>,<board>,<chip>,<mac>,<fw_version>,<fw_build>
STAT,<uptime_s>,<heap_free>,<heap_min>,<health>
HB,<seq>,<uptime_s>
```

The baseline `STAT` requires exactly five comma-separated fields including its tag. The prior firmware design's added drop fields are **incompatible with that parser**. Proposed solution: retain legacy `STAT` and add a separately versioned diagnostic record, or agree a new negotiated protocol and implement both ends together. The new diagnostic record would carry boot ID, producer/drop counters, callback age, association state, channel and queue high-water mark. Its exact encoding is deliberately unratified.

CSI currently uses Espressif CSV plus a quoted complex-sample tail. Length is in bytes in the vendor structure; complex pairing, sign order, compensation and PHY layout must follow the pinned implementation. Preserve metadata, `first_word_invalid`, rate class and the unsigned timestamp. Keep a real captured fixture and truncated/wrong-length controls.

Proposed transport requirements: whole records, bounded maximum size, one serialized writer, counted overload, boot/session changes and time-wrap handling. Do not mistake UART's 921600 setting for native USB's physical transfer rate. Acceptance: stress beyond normal display workload; partial read/write and unplug; no unbounded memory; explicit malformed/gap/drop metrics; host resumes after a bounded blocked-output interval without a silent device wedge.

## ICD-03: CORE session and replay

**Owner:** runtime/data. Current event logs are JSONL with session, host time, event and optional measurement; raw sensor captures may live separately. Proposed manifest binds raw hashes, code/config/model versions, calibration, clock mapping, protocol, label file and exclusions. Preserve original acquisition time and add replay time separately. An existing JSONL event log is not automatically a complete raw replay archive.

Acceptance: the same frozen inputs produce the same supported derived outputs within declared numeric tolerance; changed model/config versions yield a distinct result artifact. Missing dependencies or raw files are explicit errors. Replay never emits real operational alerts or transmits peer messages by default.

## ICD-04: LINK team messages

**Owner:** communications/security. Current [schema v1](../../specter/net/messages.py) defines `heartbeat`, `pose`, `track`, `alert` with unit, sequence, boot and host time. Track reports retain source unit/sensor and measurement IDs. Existing shared-key HMAC authenticates possession of a team key; it does not encrypt traffic or uniquely authenticate an honest individual unit.

Known limits: cleartext payloads, shared-key insider impersonation and in-memory replay state. Proposed extension adds per-device identity/key management, authenticated encryption, durable freshness policy, explicit expiry, size/rate bounds and shared-anchor IDs. Do not invent v1 compatibility by appending fields without testing the decoder. Acceptance: wrong key, tamper, duplicate, stale, receiver reboot, reorder, unknown peer, clock step, packet loss and partition recovery.

## ICD-05: FUSION transforms and association

**Owner:** estimation. Input must include frame, acquisition-time estimate and usable uncertainty. `T_a_b` transforms b to a. Proposed rig/anchor ID accompanies peer coordinates. Reject absent transforms and unknown anchors. Test observable dimensions: a 2D keypoint is not a metric 3D location, and a range is not a unique position. Preserve shared-parent lineage and avoid double counting.

Acceptance: physical reprojection residuals, synthetic known transforms, timing-offset injections, wrong-axis/units controls, outlier/NLOS handling and covariance consistency. Report coverage and failure states alongside error.

## ICD-06: WORLD to VIEW

**Owner:** visualization. Each displayed hypothesis needs evidence references, estimate time, freshness, origin and validity. Render predictions differently from observations; show unknown space. A stale RF feature must not keep a person icon alive indefinitely. AI summaries cite IDs and have no authority to create sensor evidence or trigger certified safety decisions.

Acceptance: unplug a sensor, corrupt calibration, replay synthetic data and introduce conflicting observations; each must produce the intended visible invalid/degraded state. Accessibility and readability must be evaluated on the eventual display.

## Change control

Every interface change records owner/reviewer, version, units and field semantics, compatibility path, example record, parser fixture, malformed cases and acceptance evidence. Ratify transport budgets after measurement: payload size, peak/average rate, tolerated age/jitter, buffer limits, drop policy, privacy and power. Numeric budgets remain **TBD** where no measurements exist.
