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

## ADR-008 — GNSS fix validity is explicit and fail-closed

**Status:** accepted · 24 October 2026
**Context:** The EKF previously accepted any `gnss_fix` Measurement. A
receiver NO_FIX report could establish the ENU anchor and switch localization
to GNSS mode, and the altitude datum was not carried in the measurement
contract. ADR-007 is reserved for the pending team evidence-validity work.

**Decision:** `PoseEKF.update_gnss()` validates the complete receiver fix
before mutating any state:

- kind `gnss_fix`, sensor `gnss`, frame `wgs84`;
- integer fix type `3` (3D), satellite count `4..64`;
- explicit boolean `sim` marker; simulated fixes require
  `allow_simulated=True`;
- explicit `alt_datum` in `{wgs84_hae, msl}`; the datum cannot change after
  the first valid anchor;
- finite latitude `[-90, 90]`, longitude `[-180, 180]`, altitude
  `[-1000, 20000]` m, positive horizontal/vertical accuracy and an explicit
  confidence in `(0, 1]`;
- finite, symmetric, positive-diagonal positive-semidefinite 3x3 covariance;
- finite nonnegative `t_host`; after the first valid GNSS fix establishes
  the time epoch, later fixes may not be older than the filter clock beyond a
  `1e-6` s numerical tolerance nor more than `1.0` s in the future.

A rejected report raises `ValueError` before anchor, position, mode,
measurement IDs or timestamps change. The existing relative state remains
intact. Valid physical UBX fixes work as before. NMEA GGA fixes are accepted
only with their explicit `msl` datum; UBX and NMEA datums cannot be mixed
without a geoid conversion. `SyntheticGnss` uses simulation time and requires
an explicit simulated-fix allowance.

**Consequences:** No-fix, malformed, out-of-range, wrong-datum, synthetic or
timestamp-invalid reports cannot promote a relative pose to GNSS. The filter
does not infer a geoid correction, an anchor offset, or satellite truth from
the absence of fields. This closes only the GNSS validity P1; the remaining
audit blockers stay gated.

**Links:** [GNSS regressions](../../tests/test_gnss_validity.py),
[EKF](../../specter/localization/ekf.py), [audit](../audit/README.md),
[team simulation](../../specter/sim/team.py).

---

## Adding a decision

Use the next ADR number. Include status, date, context, decision,
consequences and links. If a decision is reversed, mark it **superseded**
and add the replacement; do not delete the old entry.
