# Checkpoint 022 — Alpha 002-C status and FRONTIER-001 preparation

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor` (parent `6e6afb3`)
**Status labels:** Alpha 002-C motion = **IN PROGRESS / NOT RUN**;
FRONTIER-001 = **PLANNED — preparatory**; long-term AIR/CORE/LINK/OS =
**VISION / RESEARCH**.

## Verdict first

**The frozen Alpha 002-C human-motion experiment has not been performed.**
There is no session record, no geometry record and no analysis result for the
v2 protocol. No PASS, FAIL or INCONCLUSIVE is claimed. The earlier six-block
exploratory run (checkpoint 019) remains retracted; the five-minute bench
(checkpoint 021) remains apparatus evidence only.

Audit performed on a clean tree at `6e6afb3`:

- `runs/alpha002c_motion_v2/` does not exist;
- no `*.geometry.json` or v2 session file exists under `runs/`;
- no acquisition or analysis process was running;
- the only motion evidence is the retracted 019 capture and the 021 bench.

The controlled motion-sensing validation therefore remains **OPEN**. The
frozen methodology was not modified, and no human trial was started.

## Priority

Alpha 002-C remains the immediate experimental priority: finish it, or record
an honest closure, before SPECTER-WORLD/FRONTIER-001 becomes the main
implementation effort. FRONTIER-001 work in this checkpoint is deliberately
limited to contract preparation; no registry, pipeline, adapter, fusion or
WORLD claim is made.

## What changed on this branch (preparatory only)

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
round-trip and rejection. Full suite: **386 passed, 1 skipped** (DI-188
hardware test, unrelated).

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

No capability was promoted to implemented or validated by that edit.

## Next physical step (blocked on owner authorization)

1. Owner authorizes the session and supplies the geometry line (measured or
   declared-estimate per Amendment 3). No value will be invented.
2. Write `<session>.geometry.json` from those values only.
3. Retry the 10 s non-human pre-check after the phone's ping app is confirmed
   running. The first attempt failed closed: 0 payload frames (see below).
   It must show ~10 payload/s, valid windows and uncertainty ≤ 0.10 s.
4. Run the frozen 20-trial protocol only after the pre-check passes.
5. Analyse with `tools/alpha002c_motion_v2.py`; preserve PASS/FAIL/
   INCONCLUSIVE/INVALID with the raw stream and counters.

### 10 s pre-check attempt (non-human, 2026-10-23T01:33:55Z)

Run on `/dev/cu.usbmodem1101` with no cues, no subject and no motion. Result:
**INVALID — 0 payload frames.** The trial reports `active_s=0.0`,
`payload_frames=0`, `null_frames=0`, `valid=False`, reason *"no sensor clock
at the boundaries"*.

The raw stream explains it: 12 `SPECTER_STAT` lines, one torn attach-time
splice, and 5 genuine `CSI_DATA` records in 10 s, all null-data frames
(`sig_len=128`, rate 9). Device counters at the end: `csi_cb=111633`,
`printed=105976`, `data=41141`, `null=64835`, `drop_old=0`, `drop_new=0`,
`q=0`, `q_high=27`; peer MAC stable, channel 6, RSSI −28 dBm.

Interpretation: the ESP32 is alive and the phone is associated, but the link
carried no payload traffic during the window. This is an apparatus/offered-load
failure, not a motion or sensing result. The most likely cause is that the
ping app stopped or the phone slept; that must be confirmed on the phone, not
assumed. Evidence is retained at
`runs/alpha002c_motion_v2/precheck-10s.json` and `.json.raw` (gitignored).

No 20-trial session and no human trial was started. One 10 s non-human
pre-check was run and failed closed.

## Limitations

- The frozen protocol still needs a recorded geometry and owner authorization.
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
- `docs/design/alpha002c-motion-preregistration-v2.md` (frozen, unchanged)
- `docs/handbook/` at `f0fef9a` on `docs/main-handbook-sync`
