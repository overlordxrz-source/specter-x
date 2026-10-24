# First device workflow — NODE capture → WORLD

24 October 2026 · local software candidate. [Work order](../review/bench-foundation-work-order.md)
· [Review findings](../review/pr7-pr9-independent-review-20261024.md).

The owner confirms **no camera, LiDAR/range sensor or thermal sensor has
arrived yet**. Do not select one as physically available from the old parts
list. The immediate milestone uses the existing ESP32 CSI recording format.
SPECTER-SYNC remains a separate timing investigation. No new purchase or
hardware operation is authorized by this document.

## Implemented boundary

`specter.node.csi_capture` owns one explicit byte transport. It records exact
read bytes, monotonic read-completion events and lifecycle status. After
the transport closes, the existing CSI parser/adapter produces the existing
Observation v1 JSONL plus its hash/count manifest. WORLD opens that finished
recording in REPLAY mode. It never imports NODE, opens a port or competes
with an Alpha recorder.

This completes the **software recording-to-replay seam**. Continuous live
WORLD streaming, device discovery, authenticated identity, firmware control
and automatic reconnect are not implemented. No physical capture was run.

## Lifecycle and accounting

`RECORDING → FINALIZING → COMPLETE`, or `FAILED` / `CANCELLED`.
COMPLETE means byte acquisition and derived artifacts completed. It does not
mean clean or scientific acceptance. `clean_first_run.status/reasons` rejects
sequence gaps, malformed/recovered/spliced/unsupported records and clock
discontinuities; dirty captures remain inspectable but CLI exits 2.
`scientific_acceptance` remains NOT_EVALUATED. Raw/receipt write lengths,
persisted sizes/counts/end offsets and expected/persisted hashes must reconcile
before COMPLETE; integrity failures always end FAILED/nonzero.
The status is operational metadata (`format_version=1`), not a new observation
envelope. A unique session directory is created exclusively. Existing output
directories are refused, and source files are opened read-only.

Artifacts inside a session:

| File | Meaning |
|---|---|
| `session.raw.csi` | Exact accepted byte chunks in order; no rewriting or line cleanup |
| `receipts.jsonl` | Cumulative byte end and monotonic read-completion time per chunk; offline feeds explicitly labeled |
| `status.json` | Current/terminal lifecycle, bytes read/written/rejected, errors, reasons, hashes and adapter counts |
| `session.observations.jsonl` | Existing Observation v1 envelopes, only after successful transport completion |
| `session.observations.jsonl.manifest.json` | Existing capture manifest; absent if observation generation fails partway |

On parser failure the partial derived JSONL may remain without a manifest;
WORLD rejects it as incomplete. Raw evidence remains available for diagnosis.
Cancellation preserves raw bytes but does not finalize a successful replay.
A late finalization cancellation may retain a complete derived artifact;
terminal session status and gates, not file existence, determine acceptance.
Direct BaseException/KeyboardInterrupt is re-raised after terminal publication
and cleanup. Uncatchable termination and storage failure cannot guarantee
terminal publication; storage errors are never reported as success.
Device-open failure occurs before recording starts and is an explicit CLI
error. A process crash may leave `RECORDING`/`FINALIZING`; neither means complete.

Limits: 4096 bytes/read, 512 MiB raw-byte cap, 100,000 accepted read events,
60 s default duration, 5 s byte-stall limit. Duration/stall are monotonic;
serial reads have 100 ms timeout. A deadline can overrun by a read timeout
and scheduling latency; this is not real-time scheduling. Limit-crossing
chunks are rejected and counted; the session fails rather than silently
claiming a loss-free result. Finalization time is separate from acquisition
duration and can exceed it. Derived JSONL can be substantially larger than
raw bytes; these limits are not a total disk quota or power-loss guarantee.

No queue, background reconnect or second reader is created. The POSIX owner
requests pyserial's nonblocking `flock` and `TIOCEXCL`, and fails closed if
either acquisition fails. Cross-process virtual-terminal tests demonstrate
that a second **cooperating** owner is rejected and the lock releases on close.
However, the Mac pseudo-terminal probe accepted `TIOCEXCL` and still allowed
a raw noncooperating open. The original failing assertion and diagnostic
result are retained; kernel ioctl success is not an ownership proof.
See [ownership measurements](../review/node-ownership-20261024.json).

Neither request evicts/proves absence of an already-open reader. USB-driver
and callout/dial-in alias behavior remain physically unverified. The operator
must verify the exact device and absence of competing readers before any
authorized capture; this work never stops another agent's acquisition.

## Time and provenance

File rehearsal retains original acquisition ticks, raw hash/line and original
unknown receive times. Offline-feed monotonic timestamps are **not** physical
receive times and are not put into those observations.

For serial input, native clocks remain unchanged; the inferred epoch is
scoped to the new session. A complete line is mapped to the host read event
that supplied its last byte. Its receive timestamp is a **chunk-completion
upper bound**, not an acquisition timestamp or per-packet USB latency estimate.
The explicit `receive_time_is_chunk_completion` flag survives replay.
No host/device clock transform, calibration or phase coherence is invented.

Serial observations remain origin/classification UNKNOWN with unverified
evidence—even if the bytes match a known recording. Opening a port cannot
establish device identity or freshness. `live_verified` stays false in all
software tests. Promoting a physical source requires a separately reviewed
identity/acceptance artifact; this candidate provides no shortcut toggle.

## Offline rehearsal and WORLD handoff

From the candidate checkout, with the project's Python environment activated:

```sh
python -m specter.node.csi_capture \
  --input /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi \
  --out /tmp/specter-csi-new-session
python -m specter.world \
  --replay /tmp/specter-csi-new-session/session.observations.jsonl \
  --root /tmp/specter-csi-new-session
```

Use a new output directory each time. Approving `--root` is explicit; the
initial replay path does not automatically approve its parent for browsing.
The existing UI branch can inspect these same files without merging either
branch or changing software during a capture.

## Physical acceptance still required

Only after explicit owner authorization and exclusive-device review:

```sh
python -m specter.node.csi_capture \
  --port /dev/cu.REPLACE_WITH_OWNED_PORT --baud 115200 \
  --allow-hardware --duration 15 --stall 5 \
  --max-bytes 4194304 --max-reads 4096 \
  --out /tmp/specter-csi-new-physical-session
```

The [frozen 15-second demonstration plan](../design/node-esp32-first-acquisition-v1.md)
defines the specific proposed authorization and acceptance gate. The `daq`
optional dependency supplies pyserial. Verify the actual firmware's
baud/protocol before use; this command does not change baud on the firmware,
flash, restart, configure an AP or generate traffic. CDC open behavior and
DTR/RTS effects are unverified on the actual ESP32 and can disrupt existing
firmware. The owner requests inactive DTR/RTS before opening but cannot
guarantee OS/USB-driver behavior. No physical opening/reset test was done here.

Acceptance: empty owned bench, fixed traffic/stimulus, one device owner,
identified firmware/port, bounded capture, byte/frame/loss accounting,
controlled cancellation/disconnect, immutable raw hash, successful WORLD
replay and truthful UNKNOWN/unverified source status. This is acquisition
validation, not a motion/presence experiment or authorization for Alpha 003.

## Second-sensor gate

When an actual part arrives, first record exact model/revision/interface and
receipt, then prove raw acquisition. Select one modest task using its genuine
observable: image motion/reference timing for a camera, or known target range
for a range sensor. CSI stays a separate channel-change research signal.
Do not render a CSI amplitude as a spatial point or force cross-modal identity.

Before fusion: choose a rigid bench frame, measure clock mapping and its
uncertainty, establish necessary intrinsics/extrinsics, freeze a reference
procedure, and compare each sensor alone with the combined method. Include
static/null, missing-sensor, stale-time, wrong-transform and held-out-session
controls. Set quantitative tolerances from the selected task; no universal
timing/accuracy specification is assumed. Shrike is adopted only if measured
requirements justify it.
