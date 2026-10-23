# Experiment ledger

[Hub](../README.md) · **Index of experiment families and current gates · updated 23 October 2026.**

This ledger is an **index**, not a replacement for the checkpoints. The
original checkpoint, protocol, raw artifact and result remain canonical; this
page records where they live and what may be claimed now. Historical labels
are not retroactively upgraded.

**Evidence rule:** a memory entry is not evidence. Open the linked commit,
checkpoint, protocol and hash manifest before repeating a claim. Raw
Alpha evidence is gitignored and local; the committed hash manifests are the
reference.

## Current gates

| ID | Experiment / family | Status | Current boundary |
|---|---|---|---|
| **EXP-A002C-001** | Controlled CSI hand motion vs stationary (Alpha 002-C) | **IN PROGRESS — exploratory positive; independent replication pending** | One completed 20-trial session, 20/20 valid. Primary `roughness_used`: exact one-sided p = 1/1024 = 0.00098, d_z = 1.69, 95% CI [1.34, 2.91], all 10 paired differences positive; rate/PHY confounds clear. The raw validator was corrected after the first INVALID; the original INVALID and corrected PASS are both preserved. Single session, estimated geometry, 3 s lead-in, post-data correction, no independent replication. **Do not call confirmatory or general motion detection.** |
| **EXP-A003-001** | Human presence: empty / stationary / moving | **PLANNED — protocols and offline code only; no human session** | 3 sessions are exploratory only; confirmatory needs 7 sessions and a session-level exact sign test. Screening is one session, 6 blocks × 3 × 20 s, seed `20261024`. No presence claim. |
| **EXP-FRONTIER-001** | FRONTIER-001 observation/replay slice | **PLANNED / Work-owned** | Separate `specter-x-frontier001` worktree owned by Work. This documentation branch does not inspect, merge or modify it. |
| **EXP-A001/002** | DI-188, Alpha 001/002 acquisition and integration | **historical — see each record** | Acquisition/integration evidence only; not a motion, presence or vital-sign claim. |

## Alpha 002-C evidence map

| Artifact | Location |
|---|---|
| Forensic validation and what the result proves/does not prove | [checkpoint 023](https://github.com/overlordxrz-source/specter-x/blob/a3c540d/docs/checkpoints/023-alpha002c-forensic-validation.md) |
| SHA-256 evidence manifest | [023-alpha002c-evidence-sha256.txt](https://github.com/overlordxrz-source/specter-x/blob/a3c540d/docs/checkpoints/023-alpha002c-evidence-sha256.txt) |
| Analysis correction (startup torn line) | [alpha002c-analysis-correction-01.md](https://github.com/overlordxrz-source/specter-x/blob/a3c540d/docs/design/alpha002c-analysis-correction-01.md) |
| Frozen replication protocol | [alpha002c-replication-protocol-v1.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha002c-replication-protocol-v1.md) |
| Original INVALID / corrected PASS | Local `runs/alpha002c_motion_v2/result-frozen-invalid.json` and `result.json` (gitignored; hashes in the manifest) |

The replication protocol is frozen and available. **No replication has been
run.** Do not start one without owner authorization.

## Alpha 003 evidence map

| Artifact | Location |
|---|---|
| Preparation checkpoint | [checkpoint 024](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/checkpoints/024-alpha003-preparation.md) |
| Feasibility | [alpha003-human-presence-feasibility.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-human-presence-feasibility.md) |
| Confirmatory preregistration (Amendment 1) | [alpha003-presence-preregistration-v1.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-presence-preregistration-v1.md) |
| Physical/statistical readiness | [alpha003-readiness-review.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-readiness-review.md) |
| One-session screening | [alpha003-screening-v1.md](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-screening-v1.md) |
| Pre-data freeze manifest | [alpha003-freeze-v1.sha256](https://github.com/overlordxrz-source/specter-x/blob/e7af1ad/docs/design/alpha003-freeze-v1.sha256) |

Current status: offline code and synthetic controls exist; **no human Alpha
003 session exists**. The smallest next experiment is the one-session
screening; it is not a presence claim. See
[agent handoff](agent-handoff.md).

## Historical checkpoint families

The following are existing records, not re-summarised here:

- `001` DI-188 stability; `002` Alpha 001 DAQ end-to-end.
- `003–008` Alpha 002A/002B supervisor, hardware identification, firmware
  plan, CSI integration and USB-stall diagnosis.
- `009–012` first motion experiment, CSI view, scientific validation and
  controlled-RF research.
- `013–018` firmware preflight, first hardware validation, phone-station CSI,
  Alpha 002B hardening and hardware validation.
- `019–021` Alpha 002-C exploratory run, audit/remediation and bench review.
- `022–024` Alpha 002-C status, forensic validation and Alpha 003
  preparation.

Open the checkpoint files in the repository history for exact dates, failed
attempts, exclusions and hashes. Never replace a failed or superseded result
with a later narrative; add a dated note.

## Promotion rule

An experiment moves to **VALIDATED** only when the frozen protocol, recorded
evidence, honest exclusions and (where the claim generalises) independent
replication support the specific claim. Acquisition preflight is not a
sensing result; a synthetic benchmark is not a physical result; a single
session is not confirmation.
