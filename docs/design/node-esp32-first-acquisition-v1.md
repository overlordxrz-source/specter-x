# EXP-NODE-ESP32-001 — first acquisition-to-WORLD demonstration

**Version 1, prepared 24 October 2026. NOT AUTHORIZED / NOT RUN.**
**Pre-data Amendment 1, 24 October:** PR #10's corrected recorder now enforces
raw/receipt integrity and publishes a clean-run gate. Acquisition completion
alone is insufficient; dirty captures exit nonzero. This amendment changes
no Alpha protocol/evidence and grants no physical authorization.
This is a single empty-bench acquisition demonstration using the already
available ESP32-S3. It is not Alpha 003, a human trial, a motion experiment,
a firmware validation campaign or authorization to open any port.
[Workflow](../architecture/bench-device-workflow.md) ·
[Verification](../review/bench-foundation-verification.md).

## One outcome

One explicitly owned existing CSI port → **15 seconds** of raw recording →
closed port → validated Observation capture → WORLD READY/REPLAY → selected
record displays its matching raw hash/line, timestamps and radio metadata.
No continuous live WORLD connection is claimed.

## Authorization required before opening

The owner must authorize **EXP-NODE-ESP32-001 v1**, one 15-second capture,
the exact identified port/device and current candidate implementation SHA.
Approval of the draft PR or this document alone is not test authorization.
No serial-open command has been executed in preparing this plan; all current
transport tests use doubles or OS-created pseudo-terminals.

Freeze a pre-run note outside the Alpha evidence tree with:

- Candidate SHA, Python/pyserial versions and command; new output directory.
- Physical ESP32 board/USB identity and chosen endpoint. Port is currently
  **UNKNOWN**; do not reuse Shrike's port or a historical path by guesswork.
- Existing firmware/build evidence, if available; otherwise **UNKNOWN**.
  This candidate supports the existing 128-byte LLTF CSI layout. Do not
  change/reflash firmware or silently reinterpret another layout.
- Existing owned RF link/station and existing stimulus state. No new phone
  association, network change or generated traffic is part of this test.
  If the board is not already producing CSI, stop and propose a separate
  setup authorization; a silent link is not a reason to reset it.
- Exclusive operator ownership: confirm no Alpha recorder, terminal monitor,
  debugger or other process has the selected device open. A read-only
  `lsof` check of the verified device and its aliases can support this,
  but is not a race-free guarantee. Check again immediately before opening.

Acquiring a lock does not establish sensor identity, firmware correctness,
phase coherence, calibration or universal exclusion of noncooperating readers.
Do not stop or reconfigure another agent's process to obtain ownership.

## Fixed command after specific authorization only

Activate the existing project Python environment in the bench PR checkout.
Replace the port literal only from the approved pre-run note; choose a new
directory. The explicit limits are part of this version:

```sh
python -m specter.node.csi_capture \
  --port /dev/cu.REPLACE_WITH_VERIFIED_ESP32_ENDPOINT \
  --baud 115200 --allow-hardware --duration 15 --stall 5 \
  --max-bytes 4194304 --max-reads 4096 \
  --out /tmp/specter-node-esp32-001-new-session
```

This is the historical native-CDC reader's baud setting, not a verified
setting for every bridge. A CH343 diagnostic endpoint historically used
921600; do not substitute that endpoint/baud without revising the pre-run
note and obtaining authorization. No second diagnostic port is opened.

Read timeout is 100 ms; normal duration can overrun by a read timeout and
scheduling latency. Five seconds without bytes fails and closes. The owner
requests DTR/RTS inactive before opening, but USB-driver behavior can still
affect the board; no reset-free physical behavior has been established.

## Stop rules

- Ownership/identity uncertain, active competing reader, or unexpected board:
  **do not open**.
- Port open/lock failure, byte stall, read error, size/event limit, parser
  failure or sequence reset: preserve FAILED status/raw artifacts; **no retry**.
- Unexpected reboot/reset/banner, device disappearance or interference with
  another workload: cancel, preserve evidence, do not reset/reconnect.
- Ctrl-C/SIGTERM requests cancellation and closes the transport; cancelled
  sessions are not promoted to successful recordings.

No deliberate unplug/stall test is bundled into this first physical run;
those failure paths are already tested offline. A physical fault-injection
run would require its own authorization.

## Predeclared acceptance

All must hold; otherwise report FAILED/INCOMPLETE, not a sensing null:

1. Terminal status COMPLETE, reason `duration`, no errors, no rejected or
   unaccounted bytes. Raw-file byte size equals bytes read and written.
   Receipts terminate at exactly that byte count; read chunks ≤4096 bytes,
   completion times monotonic. Capture duration and finalization duration
   are reported separately.
2. At least **10 parsed observations**, including at least **one 138-byte
   payload frame**; 28-byte null frames reported separately. These are
   minimal demonstration thresholds, not a rate/quality specification.
   Any sequence gaps, malformed/recovered lines, unsupported layout or
   clock discontinuity must be reported and fails this clean first run.
   Non-CSI banners/telemetry are retained and counted, not observations.
3. Raw SHA-256 independently recomputed after close; derived capture hash,
   count and raw line references validate. Selected raw IQ amplitudes,
   `sig_len`, PHY/RSSI and native tick match their source lines.
4. WORLD opens the completed JSONL through the existing interface, shows
   READY/REPLAY and the same observation count; inspect first/middle/last
   records and their provenance. No LIVE indicator or synthetic fallback.
5. Serial-origin observations remain UNKNOWN/unverified, uncalibrated and
   clock-unsynchronized; chunk-completion receive times are not acquisition
   timestamps. Physical source promotion needs separate review of this run.

Example post-close checks and replay (no device operation):

```sh
python - <<'PY'
import json
from pathlib import Path
from specter.platform.replay import read_capture, sha256_file
p = Path('/tmp/specter-node-esp32-001-new-session')
s = json.loads((p/'status.json').read_text())
assert s['state'] == 'COMPLETE' and s['reason'] == 'duration'
assert s['acquisition_complete'] and s['clean_first_run']['status'] == 'PASS'
assert s['scientific_acceptance'] == 'NOT_EVALUATED'
assert not s['errors'] and s['rejected_bytes'] == s['unaccounted_bytes'] == 0
assert s['raw_file_bytes'] == s['bytes'] == s['read_bytes']
assert sha256_file(p/'session.raw.csi') == s['raw_sha256']
assert s['accepted_read_sha256'] == s['raw_sha256']
assert sha256_file(p/'receipts.jsonl') == s['receipts_sha256']
assert s['receipt_write_sha256'] == s['receipts_sha256']
assert s['counters'].get('payload_frames', 0) >= 1
count = sum(1 for _ in read_capture(p/'session.observations.jsonl'))
assert count == s['observations'] and count >= 10
print({'count': count, 'raw_sha256': s['raw_sha256'], 'physical_claim': 'pending review'})
PY
python -m specter.world \
  --replay /tmp/specter-node-esp32-001-new-session/session.observations.jsonl \
  --root /tmp/specter-node-esp32-001-new-session
```

The script checks only a subset; payload selection, receipts, raw IQ and
first/middle/last WORLD inspection remain explicit acceptance steps.

## Evidence and interpretation

Retain original failed/partial output as well as success, command/pre-run note,
raw data, receipts, status, derived JSONL/manifest, screenshots and result note
with hashes. Keep identifying RF/participant details out of public Git.
Record PASS only for this acquisition/replay demonstration after review.
No motion, presence, respiration, spatial location, synchronization accuracy,
sustained USB reliability or superiority claim follows. No merge, flash or
Alpha protocol/evidence change is permitted by this experiment.
