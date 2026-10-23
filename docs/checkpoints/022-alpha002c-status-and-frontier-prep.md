# Checkpoint 022 — Alpha 002-C status and FRONTIER-001 preparation

**Date:** 2026-10-22 (local; session timestamps are 2026-10-23 UTC)
**Branch:** `feature/alpha002-esp32-supervisor` (parent `6e6afb3`)
**Status labels:** Alpha 002-C motion = **PASS — single session, disclosed
analysis correction**; FRONTIER-001 = **PLANNED — preparatory**; long-term
AIR/CORE/LINK/OS = **VISION / RESEARCH**.

## Verdict first

**Alpha 002-C ran and passed the pre-registered test: PASS.** 20/20 trials
valid, 10 randomised blocks, seed `20261023`, 3 s lead-in (Amendment 4).
Primary `roughness_used`: exact one-sided sign-flip p = 1/1024 = 0.00098,
d_z = 1.69, 95% CI [1.34, 2.91], mean paired difference +0.000334, all 10
paired differences positive. Payload-rate difference 0.8 % (10.16 vs
10.24/s); modal PHY 11 in both conditions with concentration 1.0.

**Disclosed correction:** the first run of the frozen analysis returned
INVALID solely because of one startup torn line. The frozen rule allows *at
most the first torn line*; the check marked a line valid before testing it.
The raw stream and the original INVALID output are preserved, and the
correction with both results is recorded in
`docs/design/alpha002c-analysis-correction-01.md`. No design, endpoint,
feature, test, threshold or exclusion was changed.

Geometry is **estimated** (visual), not verified: L = 1.50 m, heights
0.80 m, lateral 0.30 m, longitudinal 0.00 m; derived S distances 0.808 m
horizontal / 1.137 m slant.

## Priority

Alpha 002-C is complete for this single session and no longer blocks the
implementation effort. The frozen methodology was not replaced. Independent
replication, a measured geometry and an independently verified ping budget
remain open but are not claimed here. FRONTIER-001 work in this checkpoint is
still deliberately limited to contract preparation; no registry, pipeline,
adapter, fusion or WORLD claim is made.

## Preparatory contract work on this branch

`Measurement` gained additive, defaulted fields for the future versioned
observation contract. Existing call sites and serialised records are
unchanged.

| Field | Purpose |
|---|---|
| `schema_version` | `specter.observation.v1` |
| `measurement_type` | e.g. `csi_lltf_amplitude` |
| `units` | explicit unit, e.g. `adc_counts` |
| `calibration_version` | calibration identity, or explicit `uncalibrated/...` |
| `evidence_level` | `simulated`, `software_verified`, `hardware_measured`, `experimentally_validated` |
| `valid` / `validity_flags` | contract validity plus explicit caveats (`signal_domain`, `not_spatial`, `raw_unavailable`, ...) |
| `raw_ref` | raw evidence reference (path/hash/format) |
| `uncertainty` | uncertainty kind/value/units |
| `seq` / `dropped_before` | per-sensor sequence and explicit loss accounting |

Validation rejects unknown evidence levels, unknown validity flags, negative
sequence/drop values and an empty schema version. Tests cover defaults,
round-trip and rejection. Full suite after this session and the raw-validation
fix: **388 passed, 1 skipped** (DI-188 hardware test, unrelated).

This is contract foundation, not a sensing result. No observation was
produced by this change.

## Documentation changed (separate handbook branch)

Committed as `f0fef9a` on `docs/main-handbook-sync` (the branch that owns the
handbook; **not merged**). It:

- adds the five-label status vocabulary (VISION / RESEARCH / PLANNED /
  IN PROGRESS / VALIDATED) and maps older labels onto it;
- records SPECTER-AIR as a heterogeneous fleet (fixed-wing scout, multirotor,
  thermal overwatch, mapping, relay) — VISION/PLANNED;
- records SPECTER-CORE as the planned edge-AI and mission-coordination hub,
  separated into an evidence plane and an authorized control plane;
- records SPECTER-LINK's provenance/time/freshness/authorization duties;
- records onboard local safety and degraded-link operation (flight must not
  depend on CORE or cloud);
- records the incremental Ferret → Ferettux/SPECTER-OS host path, with MCUs
  and flight controllers keeping dedicated firmware;
- expands the differentiation list and adds export-control gates and the
  DARPA CODE prior-art reference (inspiration only, no affiliation);
- updates the roadmap status table and backlog to show Alpha 002-C as frozen
  and not run.

No capability was promoted to implemented or validated by that edit. That
handbook snapshot predates the session and still records Alpha 002-C as not
run; it must be updated to the PASS result before merge. No merge was
performed.

## What was run (2026-10-23 UTC)

1. Geometry was written from the owner's declared estimates (Amendment 3):
   L = 1.50 m, heights 0.80 m, lateral 0.30 m, longitudinal 0.00 m,
   `accuracy: estimated`, method `visual`. Derived S distances 0.808 m
   horizontal / 1.137 m slant. Never described as verified.
2. The 10 s non-human pre-check was retried after the phone's ping app was
   confirmed running. **PASS** (see below).
3. The frozen 20-trial session ran as attempt 4 (attempts 1–3 aborted and
   archived as apparatus evidence only). **20/20 valid.**
4. Analysed with `tools/alpha002c_motion_v2.py`. The first output was
   INVALID on one startup torn line; the documented raw-validation bug was
   corrected without touching the statistics. Corrected verdict: **PASS**.
   Both outputs and the raw stream are preserved.

### 10 s pre-check attempt 1 — failed closed (2026-10-23T01:33:55Z)

Run on `/dev/cu.usbmodem1101` with no cues, no subject and no motion. Result:
**INVALID — 0 payload frames.** The trial reports `active_s=0.0`,
`payload_frames=0`, `null_frames=0`, `valid=False`, reason *"no sensor clock
at the boundaries"*.

The raw stream explains it: 12 `SPECTER_STAT` lines, one torn attach-time
splice, and 5 complete `CSI_DATA` records in 10 s. A field-map correction:
those frames are **28-byte** frames (`sig_len=28`, rate 9); the `128` in the
record is `info->len`, the CSI buffer length in bytes, not the frame length.
The firmware classifies by `sig_len` because the driver exposes no frame type:
`≤28` null, `29–32` ambiguous, `>32` data (`SIG_LEN_NULL_DATA_MAX` /
`SIG_LEN_AMBIGUOUS_MAX`). The host recorder uses the same boundary
(`payload_min_sig_len=33`). These five are therefore classified **null-data**
by the firmware's documented length rule — not by the 128-byte buffer — and
the 28-byte size is consistent with an 802.11 Null frame (24-byte header plus
4-byte FCS). No independent frame-type evidence is available. Device counters
at the end: `csi_cb=111633`, `printed=105976`, `data=41141`, `null=64835`,
`drop_old=0`, `drop_new=0`, `q=0`, `q_high=27`; peer MAC stable, channel 6,
RSSI −28 dBm.

Interpretation: the ESP32 was alive and the phone was associated, but the
link carried no payload traffic during the window. This was an
apparatus/offered-load failure, not a motion or sensing result. Evidence is
retained at `runs/alpha002c_motion_v2/precheck-10s.json` and `.json.raw`
(gitignored).

### 10 s pre-check retry — PASS

Same port, no cues, no subject and no motion:

- 100 payload frames, 153 null frames;
- active 10.0199 s, sensor span 10.0199 s, sample span 9.6998 s;
- 10.31 payload/s on the sample span;
- max sensor gap 0.1033 s; boundary uncertainty 0.0338 s;
- 0 clock resets, 0 late frames, 0 malformed, `valid=True`.

Evidence: `runs/alpha002c_motion_v2/precheck-10s-retry.json`, `.json.raw`,
`.json.trials.jsonl` (gitignored). The 20-trial session was allowed only
after this pass.

### Session attempts

| Attempt | Disposition | Evidence |
|---|---|---|
| 1 | Aborted after 2 valid trials (operator confusion); not analysed as a session | `runs/alpha002c_motion_v2/aborted-01/` |
| 2 | Aborted after 1 valid trial when two cue voices overlapped; not analysed | `runs/alpha002c_motion_v2/aborted-02/` |
| 3 | Aborted before trial 1; 9 KB raw, 0 trial lines | `runs/alpha002c_motion_v2/aborted-03/` |
| 4 | Complete, 20/20 valid, one startup torn line | `session.json`, `.raw`, `.trials.jsonl` |

Attempts 1–3 are apparatus evidence only. They are not sessions and no
verdict is derived from them.

### Cue-overlap bug and fix

Root cause: the long spoken explanation used a non-blocking `Popen`, so the
lead-in began when the explanation *started*; on the long `hand` instruction,
`go` fired while the explanation was still speaking, producing two voices.
Host-side fix in `tools/esp32_csi_motion.py`: the explanation and
`stop. relax.` are spoken to completion (`_speak(..., wait=True)`), then the
full lead-in elapses, then a single asynchronous `go`. The acquisition and
sensor markers are unchanged. This is a cue-delivery fix, not a measurement
parameter.

### Amendment 4 — 3 s lead-in

At the owner's request the settling/washout was reduced from 8 s to 3 s
before data (Amendment 4 in
`docs/design/alpha002c-motion-preregistration-v2.md`). Scheduled time
20 × 25 + 20 × 3 = 560 s; ping budget ≈5,600. The shorter washout is a
stated limitation; the statistics, gates and exclusions are unchanged.

### Analysis result and the one correction

`runs/alpha002c_motion_v2/result.json` — **PASS**:

- primary `roughness_used`: p = 1/1024 = 0.0009765625, d_z = 1.6946,
  95% CI [1.3414, 2.9061], mean paired difference +0.000334; all 10 paired
  differences positive;
- confounds: payload rate 10.16 vs 10.24/s (0.8 % relative difference);
  modal PHY 11 in both conditions, concentration 1.0;
- secondary `amp_volatility`: p = 1/1024, d_z = 3.37; `shape_shift`,
  `mean_amplitude` and `rssi` do not pass in the pre-registered positive
  direction; `change_rate` is descriptive only.

The raw stream has one torn startup line: a partial record concatenated with
the first complete record. The frozen rule allows at most the first torn
line. `validate_raw` initially marked the line valid before testing it and
returned INVALID; the original output is preserved at
`runs/alpha002c_motion_v2/result-frozen-invalid.json`. The fix counts torn
lines, allows only the first, and still rejects a torn line after a valid
record or a second torn line. Two regression tests cover this. Full record:
`docs/design/alpha002c-analysis-correction-01.md`.

The corrected PASS is therefore a PASS on the frozen design with a disclosed
raw-validation correction, not a re-run and not a changed hypothesis.

## Limitations

- The PASS is one session (10 pairs), not an independent replication. The
  design has ~29 % power at d_z = 0.8; the observed effect is large
  (d_z = 1.69), but a single PASS does not establish generality.
- Geometry is **estimated**, not measured. The derived S distances are
  computed from estimates.
- The 3 s lead-in (Amendment 4) is shorter than the original 8 s washout;
  carryover between trials is a stated limitation.
- The ping app's numeric starting count was never supplied; the
  `app_start=NNN` placeholder remains and the 9,999-ping budget is not
  independently verified.
- One startup torn line was tolerated under the frozen "at most the first
  torn line" rule. The original INVALID analysis output is preserved, and
  the correction is disclosed rather than hidden.
- The raw evidence is gitignored and large: `session.json` 12.7 MB,
  `.raw` 8.25 MB, `.trials.jsonl` 7.36 MB. It is preserved locally.
- The observation contract has fields and validation only; registry, bounded
  replay pipeline, ESP32 adapter, camera adapter and diagnostic VIEW remain
  unimplemented.
- No spatial observation, human detection, fusion or WORLD model exists.
- Evidence levels are metadata; they do not by themselves validate a claim.

## Evidence

- `docs/checkpoints/019-alpha002c-motion-exploratory.md` (retracted result)
- `docs/checkpoints/020-alpha002c-audit-remediation.md`
- `docs/checkpoints/021-alpha002c-review-closure-and-bench.md` (bench PASS)
- `runs/alpha002_hw_validation_20261022b/` (immutable apparatus evidence)
- `docs/design/alpha002c-motion-preregistration-v2.md` (frozen + Amendment 4)
- `docs/design/alpha002c-analysis-correction-01.md` (torn-line correction)
- `runs/alpha002c_motion_v2/session.json` and `.raw` / `.trials.jsonl`
  (accepted session, gitignored, 20/20 valid)
- `runs/alpha002c_motion_v2/result.json` (corrected PASS)
- `runs/alpha002c_motion_v2/result-frozen-invalid.json` (original INVALID)
- `runs/alpha002c_motion_v2/precheck-10s-retry.json` (passing pre-check)
- `runs/alpha002c_motion_v2/aborted-01/`, `aborted-02/`, `aborted-03/`
  (apparatus evidence only; not sessions)
- `docs/handbook/` at `f0fef9a` on `docs/main-handbook-sync`
