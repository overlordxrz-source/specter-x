# Consolidated independent-review handoff — PRs #7, #8 and #9

**24 October independent-review addendum (bench draft, not main integration):**
The exact heads below have now been reviewed. The owner requires follow-up
for #7 direct-API validation, #8 UBX/NMEA validity/integrity and duplicate
evidence, and #9 incomplete-frame recovery. Read the
[canonical branch handoff](agent-handoff.md) and
[exact findings/reproducers](../review/pr7-pr9-independent-review-20261024.md).
The original implementation packet below remains historical and unchanged;
its green tests do not resolve the newly reproduced gaps. No PR approved,
merged or modified by this review.

**Checkpoint: 24 October 2026.** These are three unreviewed draft PRs. This
document is an engineering handoff, **not an approval** and not authorization
to merge. The implementing agent did not independently approve its own work.

Canonical `main` at packet creation: `d1b5986` (radar handoff documentation).
The PR branches are preserved unchanged. PR #7 and PR #8 currently conflict
only in `docs/handbook/agent-handoff.md` because canonical handoff text has
advanced; their code/test/docs review surfaces are intact. PR #9 is currently
mergeable.

## PR map

| PR | Base commit | Head commit | State | Remote CI |
|---|---|---|---|---|
| #7 team evidence validity | `35a11569d352c54316a2a2973f05988d23461a94` | `939240eb34e158a9cf038291cb9c73c468ebe5d3` | draft, open, conflicting in handoff only | manual dispatch `40050348307`: **266 passed, 1 deselected** |
| #8 GNSS validity | `68cbc00300a4a4ed97ac272b949b38669e06f277` | `9ca4f3aa32d410ebcc2e04ec30167fdda3234ba2` | draft, open, conflicting in handoff only | pull-request run `40052792379`: **290 passed, 1 deselected** |
| #9 radar packet validation | `f382ab50d3789ba1145dc587d0a77975b214d13a` | `9e2f1d57bf1826f30b0c871284761388e46c3fc9` | draft, open, clean/mergeable | pull-request run `40057651691`: **265 passed, 1 deselected** |

PR #7’s final docs-only head did not receive an automatic pull-request check;
the same workflow was dispatched manually at exactly `939240e` and passed.
PR #8 and PR #9 have green pull-request checks on their final heads.

## PR #7 — legacy team evidence validity

**Branch:** `fix/team-evidence-validity`
**Review surface:** 11 files, +615/−107.

### Changed files

```text
docs/architecture/NEXT_WORK_ORDER.md
docs/audit/INTEGRATION.md
docs/audit/README.md
docs/audit/STATUS.md
docs/handbook/agent-handoff.md
docs/handbook/decisions.md
specter/fusion/team.py
specter/net/messages.py
tests/test_stage4b_fusion.py
tests/test_team_evidence_validity.py
tools/audit_legacy_probes.py
```

### Original defect

Two independently demonstrated failures:

1. Peer report created at `t=1` was restamped with local fusion time
   `t=100`, making stale evidence appear fresh.
2. Local and peer reports sharing the same parent measurement ID were
   precision-fused, halving covariance (`1.0 → 0.5000000005`) and implying
   independent evidence.

### Baseline reproduction

```sh
git worktree add /tmp/specter-pr7-base 35a11569d352c54316a2a2973f05988d23461a94
cd /tmp/specter-pr7-base
PYTHONPATH=. python - <<'PY'
import numpy as np
from specter.fusion.team import TeamFuser
from specter.net.messages import TrackReport

stale = TeamFuser('local', max_age_s=5)
stale.ingest_report(TrackReport('peer', 1, 1.0, 1, [0, 0, 0], np.eye(3)))
print('stale last_update:', stale.fuse(t_now=100.0)[0].last_update)  # 100.0

shared = TeamFuser('local')
shared.add_local(1, [0, 0, 0], np.eye(3), 'thermal', ['same-parent'])
shared.ingest_report(TrackReport(
    'peer', 1, 1.0, 1, [0, 0, 0], np.eye(3),
    source_unit='peer', source_sensor='thermal',
    measurement_ids=['same-parent']))
print('shared covariance xx:', shared.fuse(t_now=1.0)[0].covariance[0, 0])
# 0.5000000005
PY
```

### Behavior and API compatibility

- `TrackReport.t_host` is explicitly report-creation time, not acquisition
  time. A caller must provide `clock_offset_s = peer_t - local_t`; omitted or
  non-finite mapping means unknown age and no fusion.
- Peer age must satisfy `max_future_s`/`max_age_s`; unknown, stale and future
  reports are rejected. `TeamTrack.last_update` retains evidence time instead
  of fusion time.
- `own_anchor` is rejected. `frame_id` is an additive shared-frame declaration
  on `TrackReport`; a mismatch is rejected, but `frame_id` is not proof of
  anchor identity.
- Precision fusion requires non-empty, pairwise-disjoint parent IDs. Shared,
  looped or unknown parentage keeps the newest contribution at its own
  covariance and sets `fusion_status="shared_evidence"`.
- `TeamTrack` gains `fusion_status`; `add_local` gains optional `t_host` and
  `frame_id`; `ingest_report` gains `clock_offset_s`.

### Commands at PR head

```sh
git worktree add /tmp/specter-pr7 939240eb34e158a9cf038291cb9c73c468ebe5d3
cd /tmp/specter-pr7
python -m pytest -q tests/test_team_evidence_validity.py \
  tests/test_stage4b_fusion.py tests/test_stage4b_net.py \
  tests/test_audit_hardening.py          # 79 passed
python -m pytest -q -m 'not hardware'     # 266 passed, 1 deselected
python tools/check_architecture.py        # PASS
PYTHONPATH=. python tools/audit_legacy_probes.py
```

Expected probe on this branch: stale-peer and shared-parent controls are
`false`; the other three recorded P1s are `true`.

### Mutation control

In a disposable copy only, restore the old behavior by making `_eligible`
return `True` and `_fusion_status` return `"independent"`, then run:

```sh
python -m pytest -q tests/test_team_evidence_validity.py
# 8 failed, 13 passed
```

### Review focus and limitations

- **Evidence identity:** disjointness is only as good as the supplied parent
  IDs. Shared IDs are suppressed; empty/unknown parentage is treated as
  `shared_evidence`, not independent.
- **Cross-correlation remains unresolved.** Two disjoint IDs may still be
  statistically correlated. The branch does not invent a correlation model;
  this is a reason to keep team fusion gated.
- `frame_id` is a declaration, not an anchor proof. Schema v1 still has no
  anchor identity or synchronized peer clock field.
- Confidence for independent contributions remains a simple mean; treat it as
  legacy metadata, not a probabilistic fusion result.
- No hardware: needs real clock mapping/delay tests and anchor validation
  before any physical claim.

## PR #8 — GNSS validity hardening

**Branch:** `fix/gnss-validity-hardening`
**Review surface:** 7 files, +462/−28.

### Changed files

```text
docs/handbook/agent-handoff.md
docs/handbook/decisions.md
specter/localization/ekf.py
specter/sensors/gnss/neom9n.py
specter/sim/team.py
tests/test_gnss_validity.py
tools/audit_legacy_probes.py
```

### Original defect

A `gnss_fix` with `fix_type=0` (NO_FIX) established the anchor
`(0.0, 0.0, 0.0)` and switched the EKF to `GNSS` because
`PoseEKF.update_gnss()` ignored fix validity.

### Baseline reproduction

```sh
git worktree add /tmp/specter-pr8-base 68cbc00300a4a4ed97ac272b949b38669e06f277
cd /tmp/specter-pr8-base
PYTHONPATH=. python - <<'PY'
from specter.localization.ekf import PoseEKF
from specter.sensors.gnss.neom9n import Neom9nDriver, build_nav_pvt
m = Neom9nDriver().feed(build_nav_pvt(fix_type=0))[0]
p = PoseEKF('A').update_gnss(m)
print(p.anchor, p.mode)  # (0.0, 0.0, 0.0) GNSS
PY
```

### Behavior and API compatibility

- `PoseEKF(..., allow_simulated=False)` is added. Synthetic fixes require an
  explicit opt-in; the team simulator opts in.
- Valid updates require `kind="gnss_fix"`, sensor `gnss`, frame `wgs84`,
  3D fix type `3`, `4..64` satellites, explicit boolean `sim`, explicit
  `alt_datum`, finite/range-checked latitude/longitude/altitude, positive
  horizontal/vertical accuracy, explicit confidence in `(0,1]`, and finite,
  symmetric, positive-diagonal PSD covariance.
- **First-fix/timestamp semantics:** the first valid fix may establish the
  wall-clock epoch even after prediction starts at `t=0`. Once GNSS time is
  established, reports older than the filter clock beyond `1e-6 s` or more
  than `1.0 s` in the future are rejected.
- **Altitude datum:** UBX `height` is labelled `wgs84_hae`; NMEA GGA altitude
  is labelled `msl`. The datum cannot change after anchor. No geoid conversion
  is invented.
- `SyntheticGnss` now uses simulation time rather than wall time.
- Invalid reports raise before changing anchor, position, mode, IDs or
  timestamps. Initial REL state remains REL.

### Commands at PR head

```sh
git worktree add /tmp/specter-pr8 9ca4f3aa32d410ebcc2e04ec30167fdda3234ba2
cd /tmp/specter-pr8
python -m pytest -q tests/test_gnss_validity.py \
  tests/test_stage4b_uwb_ekf.py tests/test_stage4b_sensors.py \
  tests/test_stage4b_net.py tests/test_audit_hardening.py   # 116 passed
python -m pytest -q -m 'not hardware'                       # 290 passed, 1 deselected
python tools/check_architecture.py                           # PASS
PYTHONPATH=. python tools/audit_legacy_probes.py
```

Expected probe on this branch: `no_fix_anchors_and_claims_gnss: false`; the
other P1 controls remain unchanged on this base.

### Mutation control

In a disposable copy only, replace `PoseEKF.update_gnss` with the body from
`68cbc00300a4a4ed97ac272b949b38669e06f277:specter/localization/ekf.py`, then:

```sh
python -m pytest -q tests/test_gnss_validity.py
# 42 failed, 3 passed
```

### Review focus and limitations

- **First-fix clock epoch:** the deliberate compatibility choice allows a
  first valid GNSS fix to jump the filter clock to wall time. Verify this is
  acceptable for replay and live callers.
- **Datum mixing:** UBX HAE and NMEA MSL are both accepted only within a single
  anchor epoch; no geoid correction is implemented.
- **NMEA fallback:** GGA fix quality is approximated as `fix_type=3` after the
  driver's existing mapping; this needs vendor/NMEA validation.
- **Synthetic mode:** simulation is explicit, but the EKF still reports mode
  `GNSS` when allowed. Reviewers should decide whether a distinct simulation
  mode is required.
- **Hardware:** no receiver was used. Future tests need real UBX-NAV-PVT and
  NMEA GGA samples, actual `valid`/fix flags, HAE/MSL comparison, antenna
  conditions and timestamp/clock behavior.

## PR #9 — radar packet validation

**Branch:** `fix/radar-packet-validation`
**Review surface:** 8 files, +423/−31.

### Changed files

```text
docs/handbook/agent-handoff.md
docs/handbook/decisions.md
specter/sensors/radar/tlv.py
tests/fixtures/radar/README.md
tests/fixtures/radar/iwr6843aop_oob_points_2.bin
tests/test_pipeline.py
tests/test_radar_validity.py
tools/audit_legacy_probes.py
```

### Original defect

A radar header declaring `totalPacketLen=1` was accepted, and the parser could
return after an early TLV break. Detected-point counts and finite point values
were not validated.

### Baseline reproduction

```sh
git worktree add /tmp/specter-pr9-base f382ab50d3789ba1145dc587d0a77975b214d13a
cd /tmp/specter-pr9-base
PYTHONPATH=. python - <<'PY'
import struct
from specter.sensors.radar.tlv import HEADER_FMT, MAGIC, parse_frame
frame = struct.pack(HEADER_FMT, MAGIC, 1, 1, 1, 1, 1, 0, 1, 0)
print(parse_frame(frame) is not None)  # True (bug)
PY
```

### Behavior and API compatibility

- `parse_frame` now returns `None` for invalid/truncated/inconsistent frames;
  valid frames still return `(FrameHeader, points)`.
- Enforces 40-byte header, documented magic, `totalPacketLen` including header,
  32-byte packet alignment, bounded TLV count, non-zero in-packet TLV payloads,
  no duplicate detected-points TLV, exact `numDetectedObj × 16` point length,
  and finite float32 x/y/z/velocity values.
- Unknown TLVs with valid boundaries are skipped.
- Adds `RadarFrameStream` for fragmented input and one-byte resynchronisation
  after malformed prefixes.
- **Compatibility change:** non-32-byte-aligned packets and zero-length TLVs
  are intentionally rejected. Callers relying on those out-of-contract forms
  must adapt.
- Frozen fixture: 96 bytes, spec-derived, SHA-256
  `ea26d5ef056ced916ee39f3b6120cffa8c6acb335fdff94326cad80b4dd1d8db`.

### Commands at PR head

```sh
git worktree add /tmp/specter-pr9 9e2f1d57bf1826f30b0c871284761388e46c3fc9
cd /tmp/specter-pr9
python -m pytest -q tests/test_radar_validity.py tests/test_pipeline.py  # 23 passed
python -m pytest -q -m 'not hardware'                                    # 265 passed, 1 deselected
python tools/check_architecture.py                                       # PASS
PYTHONPATH=. python tools/audit_legacy_probes.py
```

Expected probe on this branch:
`radar_impossible_packet_length_accepted: false`.

### Mutation control

In a disposable copy only, replace `parse_frame` with the body from
`f382ab50d3789ba1145dc587d0a77975b214d13a:specter/sensors/radar/tlv.py`, then:

```sh
python -m pytest -q tests/test_radar_validity.py
# 11 failed, 9 passed
```

### Review focus and limitations

- **SDK assumptions:** the fixture is derived from TI’s documented OOB demo
  layout, not a capture from the actual board/SDK. Header version and platform
  are recorded but not enforced. Verify against the exact IWR6843AOP firmware
  before claiming compatibility.
- Packet padding is accepted as 0–31 trailing bytes; the fixture uses zeros but
  the parser does not require zero padding.
- The parser validates detected-points TLV type 1 only. Side-info, heatmap,
  stats and other TLVs are boundary-skipped, not semantically validated.
- No antenna, calibration, range/Doppler validity or missed-detection claim
  follows from a valid frame.
- Future hardware validation must capture real frames, measure MTU/throughput,
  confirm TLV types and padding, and test actual truncated/noisy streams.

## Remaining P1 — BNO085 quaternion validation (not implemented)

The final P1 is in `specter/sensors/imu/bno085.py`: `quat_measurement` converts
the input and checks only `norm == 0`, then normalizes. A NaN/Inf 4-vector or
wrong shape can therefore pass; no finite/shape precondition is enforced.

**Next isolated work order (do not start without owner authorization):**

- Add tests for valid unit quaternion, NaN/Inf components, wrong lengths,
  zero norm, and near-zero norm.
- Require a finite 4-vector with nonzero norm before constructing the
  `Measurement`; preserve SIM provenance and existing valid behavior.
- Decide explicitly whether a non-finite/invalid quaternion raises or returns
  an unavailable state. Do not invent calibrated orientation uncertainty.
- Run focused tests, full offline suite, architecture gate and audit probe.
- Keep this separate from PRs #7–#9; no hardware or firmware work.

## Common review commands

```sh
python -m pytest -q -m 'not hardware'
python tools/check_architecture.py
PYTHONPATH=. python tools/audit_legacy_probes.py
git diff --stat <base>..<head>
git diff --name-status <base>..<head>
```

Do not merge, rebase, push to, or approve PRs #7, #8 or #9 from this review
packet. Use disposable worktrees. Alpha 003, frozen evidence, CI configuration
and Work checkouts remain outside this scope.
