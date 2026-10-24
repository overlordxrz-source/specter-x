# Architectural decision record

[Hub](../README.md) · **Decision log · started 23 October 2026.**

This is the lightweight ADR index for choices that affect SPECTER-X's
architecture, evidence claims or agent continuity. It records **why** a
boundary exists; detailed contracts remain in [architecture](architecture.md),
[data contracts](data-contracts.md) and [interfaces](interfaces.md).

Statuses: **proposed**, **accepted**, **superseded**. A superseded decision
stays in the record with a link to its replacement.

---

## ADR-001 — Canonical memory is in the repository

**Status:** accepted · 23 October 2026
**Context:** Agents and long sessions lose context; chat history is not a
reliable project record.
**Decision:** The repository is canonical. Maintain five memory surfaces:
North Star, research-ideas log, this ADR log, experiment ledger and current
agent handoff. Update them at checkpoints, before context compaction and
when an idea/decision/evidence gate changes.
**Consequences:** A future agent can reconstruct the project state from
versioned files. Memory entries are not evidence; they must link to
artifacts. Routine chat is not logged.
**Links:** [research ideas](research-ideas.md), [experiment ledger](experiment-ledger.md),
[agent handoff](agent-handoff.md).

## ADR-002 — Fusion preserves provenance, uncertainty and shared evidence

**Status:** accepted · 23 October 2026
**Context:** Multimodal fusion can improve coverage, but it can also hide
blind spots or double-count correlated observations.
**Decision:** Every fused value retains contributing observation IDs,
source, acquisition clock, coordinate frame, calibration validity, age,
uncertainty and alternatives. WORLD may retain conflicting hypotheses.
Fusion must not convert a weak or missing observation into a measured one.
**Consequences:** Fusion is a consumer of validated observations, not a
shortcut around them. Peer reports of the same raw observation are not
independent evidence. Unknown space remains unknown.
**Links:** [architecture — evidence plane](architecture.md#evidence-plane-and-control-plane),
[data contracts](data-contracts.md).

## ADR-003 — Confidence is not new spatial information

**Status:** accepted · 23 October 2026
**Context:** The symbolic complementary-observation example can be
misread as “confidence fills gaps.” A confident CSI channel-change result is
still not a 3-D location.
**Decision:** A confidence score is only a calibrated score over the task
the sensor/model measured. It does not add range, bearing, depth, identity
or occupancy. Cross-modal complementarity requires independent observables,
calibration, time alignment and association. Correlated sensors require a
shared-evidence model, not naive Bayesian multiplication. Missing values
stay unknown; no forced completion of the illustrative `1..10` row.
**Consequences:** A high-confidence single-link CSI detection cannot be
reported as a localized person. Radar range, thermal radiance and CSI
channel change remain distinct observables until a validated association
model exists.
**Links:** [research ideas — complementary observations](research-ideas.md#complementary-partial-observations).

## ADR-004 — Learned fusion must beat calibrated baselines

**Status:** accepted research policy · 23 October 2026
**Context:** Cross-attention and learned world models are attractive but can
overfit, leak adjacent windows or hide missing-modality failures.
**Decision:** Learned fusion is **RESEARCH**, not a default architecture. It
must be compared with calibrated Bayesian/factor-graph/late-fusion and
single-sensor baselines, use held-out sessions/people/sites, include
missing/stale/degraded channels and report abstention and wrong-high-confidence
cases. Attention is an architecture family, not evidence.
**Consequences:** A fusion project starts with two validated modalities and
a modest defined task. A learned model that does not beat a simple calibrated
baseline is a negative result, not a capability.
**Links:** [research program — fusion sequence](research-program.md#fusion-sequence),
[validation](validation.md).

## ADR-005 — Capability promotion requires frozen evidence

**Status:** accepted · 23 October 2026
**Context:** A single exploratory session or a software demo can be
mistaken for a validated capability.
**Decision:** A claim moves toward **VALIDATED** only with a frozen protocol,
recorded raw evidence, honest exclusions, independent replication where the
claim generalises, and a stated boundary. Exploratory, simulated and
acquisition-only results keep their labels. Historical results are amended
by dated notes, never rewritten.
**Consequences:** Alpha 002-C remains **IN PROGRESS — exploratory positive,
replication pending**. Alpha 003 is **PLANNED**. No presence, occupancy,
respiration or localization claim follows from the offline Alpha 003 code.
**Links:** [experiment ledger](experiment-ledger.md),
[Alpha 002-C forensic record](https://github.com/overlordxrz-source/specter-x/blob/a3c540d/docs/checkpoints/023-alpha002c-forensic-validation.md).

## ADR-006 — Agent startup and update ritual

**Status:** accepted · 23 October 2026
**Context:** Parallel worktrees and long-running experiments make stale
handoffs dangerous.
**Decision:** Every future agent reads, in order: North Star → relevant
research ideas → relevant ADRs → latest experiment ledger entry → current
agent handoff. Then inspect actual `git status` and worktrees before acting.
Update memory at checkpoints and before compaction. Do not merge, flash or
start human experiments without explicit authorization.
**Consequences:** Handoffs are short and link to evidence. A memory entry
that conflicts with a raw artifact is corrected by a dated note.
**Links:** [agent handoff](agent-handoff.md), [North Star](north-star.md).

---

## ADR-009 — Radar packets must satisfy the frozen OOB frame contract

**Status:** accepted · 24 October 2026
**Context:** The legacy TI mmWave parser accepted a frame whose
`totalPacketLen` was 1, returned after an early TLV break, and did not validate
the detected-point payload count or finite values. The exact board/SDK
capture was unavailable, so the offline contract is taken from TI’s documented
out-of-box-demo UART format and frozen in a spec-derived fixture, not claimed
as hardware evidence. ADR-007 and ADR-008 are reserved for the pending team
and GNSS PRs.

**Decision:** The parser accepts a TI OOB frame only when all of the following
hold:

- the 40-byte header starts with the documented magic word;
- `totalPacketLen` includes the header, is at least the header size, is at
  most the engineering buffer bound, and is a multiple of 32 bytes;
- `numTLVs` fits within the packet’s available 8-byte TLV headers;
- every TLV has a non-zero payload that ends inside `totalPacketLen`;
- no TLV silently runs into another, and any residual bytes are less than one
  32-byte alignment block;
- detected-points TLV type 1 is present at most once, its length is exactly
  `numDetectedObj × 16`, and all four float32 values per point are finite;
- unknown TLVs are skipped only after boundary validation.

Truncated, impossible or internally inconsistent frames return no frame and
do not allocate from untrusted length fields. `RadarFrameStream` handles
fragmented input and resynchronises one byte at a time to the next magic word,
so a malformed prefix does not poison a later valid frame.

**Compatibility:** This intentionally rejects non-32-byte-aligned packets and
zero-length TLVs. Both are outside the frozen TI OOB contract. Firmware/SDK
identity, platform/version fields, antenna calibration, point semantics and
range/Doppler validity remain unverified; the parser does not invent them.

**Links:** [reference fixture](../../tests/fixtures/radar/README.md),
[parser](../../specter/sensors/radar/tlv.py),
[regressions](../../tests/test_radar_validity.py),
[audit](../audit/README.md).

---

## Adding a decision

Use the next ADR number. Include status, date, context, decision,
consequences and links. If a decision is reversed, mark it **superseded**
and add the replacement; do not delete the old entry.
