# Independent repository audit and WORLD/OS hardening

**23 October 2026 · local branch `audit/world-os-hardening`.**

**The repository is not certified “all good.”** This audit found and reproduced
software faults, fixed the scoped boundary defects below, improved the desktop and
added an engineering contract. Five executable legacy blockers remain. The whole
source/config surface is inventoried and syntax-checked where supported, with
repository suites run; **this is not a completed manual semantic review of every
line, exhaustive path coverage, hardware certification or scientific replication**.
Do not interpret this report or green tests as such a claim.

[Engineering contract](../architecture/ENGINEERING_CONTRACT.md) ·
[Agent work orders](../architecture/WORK_ORDER.md) · [Next concrete work order](../architecture/NEXT_WORK_ORDER.md) · [Reproduce](REPRODUCE.md) ·
[Integration source inventory](source-inventory.json) · [Alpha inventory](alpha-inventory.json).

## Scope, concurrent work and preservation

Started from integration `0929ad6`, main `1edabbc`, Alpha `285bc2c`. The initial audit
working diff was saved in task artifacts and committed locally as `83e1a02` before
reconciliation. A final live check found newer main `7ca4a8a` and OpenCode's clean
remediation checkout at `cf05def` (`fix/pr5-second-remediation`). Read main's newer
canonical handoff and inspected the intervening changes. The audit commit was
rebased onto **`cf05def`**, preserving its replay parser, approved-root restrictions,
source/evidence generation guards, state clearing, regression coverage and canonical
memory. No other checkout or branch was rewritten.

Three content conflicts were resolved deliberately: docs hub retained the newer
integration wording plus audit links; server retained the new catalog response object
plus path revalidation; session browser retained completeness warnings plus search.
The newer CI, handbook, frozen Alpha evidence and feature branches remain outside
the audit diff relative to `cf05def`. No push, merge, firmware edit, flashing,
physical sensor read, human trial or Ferret modification occurred in this audit.
The local parent already contains an OpenCode main merge; this audit did not perform it.

## Verified bugs fixed in this branch

References are current source locations; use `git diff cf05def` for exact changes.

| Defect / before | Fix and independent control | Source |
|---|---|---|
| Clock domain, tick frequency or wrap convention could change within one epoch | Reject before advancing counters; three distinct mutation controls | `specter/platform/registry.py:62` |
| Tiny negative diagonal variance passed the PSD tolerance | Negative variance rejected independently of eigenvalue tolerance | `specter/platform/observation.py:55` |
| NumPy nonfinite payloads emitted nonstandard JSON; legacy invalid covariance accepted | Recursive null compatibility conversion, strict JSON, finite timestamps and PSD covariance checks | `specter/fusion/measurement.py:57`, `:89` |
| Signing JSON with ordinary whitespace failed its own round trip | Sign the same compact representation that verification uses | `specter/net/security.py:42` |
| Bad/negative/bool/fraction sequence headers accepted; invalid authenticated type consumed a higher sequence and suppressed later valid traffic | Strict header, typed finite/vector/covariance validation before replay state mutation; malformed messages dropped | `specter/net/security.py:80`, `specter/net/messages.py:124`, `specter/net/transport.py:121` |
| Future or NaN timestamps passed freshness | Fail closed for nonfinite or excessive forward/backward skew; receive duration uses monotonic time | `specter/net/clock.py:35`, `specter/net/transport.py:121` |
| Event session names escaped the output directory; reopening a session appended duplicate sequence IDs; NaN details accepted | Restricted IDs, exclusive creation and strict serialization before sequence increment | `specter/events/log.py:22`, `:38` |
| Split DI-188 start echo lost its remaining prefix; split GNSS sync lost a valid frame | Advance pending echo suffix; retain the possible first sync byte. Every GNSS byte split tested | `specter/sensors/di188/driver.py:479`, `specter/sensors/gnss/neom9n.py:210` |
| Invalid gas input could display OK | Invalid readings return UNKNOWN; measurement creation rejects invalid concentration | `specter/sensors/experimental/gas.py:28` |
| Thermal pixel spread was mislabeled as measurement covariance, with invented confidence | Keep scene variance as an explicitly named descriptive field; unknown uncertainty/confidence; reject empty/nonfinite frames and simulated physical verification | `specter/sensors/thermal/interface.py:21` |
| Ordinary EKF predict(dt) never advanced its clock, so GNSS mode did not expire | Advance clock, reject negative/nonfinite intervals and reversed explicit time | `specter/localization/ekf.py:90` |
| Catalog path could be replaced by an escape symlink after approval | Re-resolve before serving and check approved root; synthetic canary regression | `specter/world/server.py`, `Handler.item` |
| Delayed filter response could leave restored rows blank | Reject responses for superseded source/query state; deterministic delayed-filter browser control | `specter/world/web/app.js`, `refresh` |
| New remediation selected only 512 names per directory, silently losing eligible evidence behind irrelevant files; Path.iterdir can allocate the full directory first | Stream with os.scandir under global scan budget; sort only bounded results; preserve truncation/scan-error metadata. Both faults reproduced before fixing | `specter/world/server.py`, `_catalog_walk` / `catalog_result` |

The legacy thermal test was intentionally updated to require **unknown** confidence
and covariance instead of an arbitrary score ≤0.3; the unverified/simulation assertions
remain. No delayed-response regression was removed or weakened. A synthetic invalid
first-word fixture exercises masked history slots; a clean fixture is not falsely
assumed to contain masks.

## Unfixed release blockers: do not expose as validated WORLD capabilities

`PYTHONPATH=. python tools/audit_legacy_probes.py` reproduces all five with synthetic
inputs and no hardware. These are scoped blockers, not proof that all other code is
correct. The WORLD dependency gate prevents importing these legacy paths.

| Priority / classification | Evidence | Required work order |
|---|---|---|
| P1 **VERIFIED BUG**: peer from t=1 becomes fresh at t=100 | `specter/fusion/team.py:119` assigns current fusion time; age filter cannot reject the old input | Validate mapped acquisition ages before association; preserve observation update time. Test stale/future/unsynchronized epochs |
| P1 **VERIFIED BUG**: same parent on local and peer reports halves covariance | `specter/fusion/team.py:119` / `_merge_one`; identical unit covariance becomes ≈0.5 | Deduplicate shared evidence and define cross-correlation handling before precision fusion; test repeated/looped network reports |
| P1 **VERIFIED BUG**: no-fix GNSS anchors the EKF and sets GNSS mode | `specter/localization/ekf.py:117` ignores fix validity | Define validity, altitude datum, finite bounds, fix flags and timestamp contract before state mutation; preserve REL on invalid fix |
| P1 **VERIFIED BUG**: radar header declaring total length 1 is accepted | `specter/sensors/radar/tlv.py:41` returns a frame after early TLV break | Reject inconsistent packet/TLV lengths/counts, finite point values; freeze exact SDK fixture before changing length conventions |
| P1 **VERIFIED BUG**: NaN quaternion accepted | `specter/sensors/imu/bno085.py:23` normalizes without finite/shape checks | Require finite 4-vector with nonzero norm; validate filter inputs and distinguish heuristic from calibrated orientation uncertainty |

Additional **UNVERIFIED CONCERNS / source-evidenced limitations** require targeted
work, not a promise of production readiness:

- Team schema v1 has no anchor identity; `ingest_report` ignores `own_anchor`
  (`team.py:106`). Its introductory calibrated-transform claim overstates the code.
  Pose covariance, correlation and calibration are not established by team simulation.
- `specter/sensors/di188/measure.py:236` iterates `driver.stream()` without a stall
  timeout; cancellation is checked only after a sample. `driver.py:188` does not map
  its port argument to a specific USB descriptor. Mock stalled reads/identity matching
  before sustained live acquisition. Alpha already differs here: review targeted
  changes; do not bulk-import its application or frozen protocols.
- Experimental `try_open_hardware` paths can indicate package availability rather than
  device operation (`experimental/acoustic.py:57`, `event_camera.py:56`). BNO polling,
  calibrated thermal/radar/UWB, RF/optical safety and field accuracy remain **DATA
  UNAVAILABLE** in this audit. Do not update receipt/readiness status from imports.
- YOLO construction (`specter/ml/pose/estimator.py:68`) may resolve/download a model;
  make offline/local-model policy explicit before enabling automatic inference.
- Legacy tracker covariance, IMU covariance proxies, advisory man-down/vitals and VLM
  templates are prototypes. They do not establish physical uncertainty, physiology,
  rescue capability or deployment safety. NMEA validity/checksum/altitude semantics
  need a dedicated driver audit and vendor-reference tests.
- Group HMAC is not individual identity or encryption. Replay state is memory-only;
  boot ordering depends on wall-clock order. Queues, key lifecycle, per-peer limits,
  clock mapping and authenticated capability negotiation need a LINK work order.
- Path revalidation is not an OS sandbox against concurrent code running as the same
  local user. CSI framing without a checksum cannot detect every metadata/IQ boundary
  splice. The inherited verification docs explicitly retain that physical wire limit.

## Actual verification and scientific interpretation

Initial adversarial controls on `0929ad6`: **20 failed, 2 passed**, before fixes.
Further catalog controls failed on `cf05def` before the streaming fix. These failures
are retained in private task artifacts, alongside the original working diff.

Final local suite: **245 passed, 1 hardware deselected**. Alpha snapshot `285bc2c`:
**414 passed, 1 hardware deselected**, one inherited NumPy warning. These are different
branches/surfaces and must not be added together as one capability score. The WORLD
architecture gate traverses 14 in-repository modules and rejects direct, indirect and
dynamic import mutations. It is a limited static check, not a sandbox.

Browser: **37 passing checks** on the reconciled application, Chromium 149 and
Playwright 1.62.1; actual recording, unavailable/SIM/UNKNOWN/error states, keyboard
step, recording search, packet-history inspection, source switching, delayed filter restoration, persistent and
delayed evidence clearing, and 900/1280/1512/1920 layouts. A separate copied-asset
mutation removing source-generation guards fails the retained **Prior-session READY
response never reappears** check. A separate mutation ignoring changed filters fails to restore rows in the
deterministic delayed-filter control. No physical source opened.

Replay: independent CSV route finds **7,290 records**; sampled amplitudes, native ticks,
raw line references and hash match. Source SHA-256 remains
`f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`.
50,000-record simulated stress exercises bounded queries (80 rows / 160 history
records). Runtime timings are environment-specific, not real-time guarantees.

Newer Alpha v2 raw check: **17,837 parsed packets**, one malformed startup fragment
and one concatenated line recovered; **11,554/11,554 selected samples** match raw IQ
amplitudes and recorded radio metadata; no cross-trial sample reuse. Ten paired
blocks reproduce **p = 1/1024**, **d_z = 1.6946320189**, percentile bootstrap
**[1.3414406479, 2.9061288846]**. Frozen d/CI differences are ≤2.1e-7. The independent
raw checker imports no Alpha parser or statistic implementation; synthetic shape
injection gives p=1/1024, its null p=1, and a modified sample fails raw matching.
See [sanitized summary](evidence-summary.json).

This supports arithmetic and recorded provenance for **one exploratory session**.
It does not independently verify motion labels, causal specificity, reference motion,
physical sensitivity, calibration, power/generalization or confirmation. It does not
rehabilitate the original `699d199` run's contaminated windows. The prior independent
audit remains in task artifacts; newer v2 sensor spans (25.007–25.024 s) must not be
confused with that earlier run's 43–55 s contamination. No absence-of-motion claim.
No new trial is authorized; follow the latest canonical experiment ledger.

## WORLD improvements and architecture direction

The desktop now adds a bounded, interactive CSI packet-history canvas with retained
masked slots, relative-scale legend, packet/slot/radio metadata and evidence inspection.
The layout uses clearer typography/contrast, a compact status row, bounded sticky-header
tables, recording search and keyboard stepping. It keeps replay/source identity
visible. This is signal-domain history, not a spatial map or motion classifier.

`AGENTS.md` leads future agents to the canonical handbook and the engineering contract.
The contract defines NODE/CORE/LINK/FUSION/WORLD/VIEW ownership, observations and clocks,
resource/lifecycle rules, UI truthfulness, first-party ESP-IDF strategy, gates for
new sensors, 30/90-day and longer milestones, and a concrete scoped work-order template.
SPECTER-OS is the unified ecosystem; it does not depend on a custom kernel. Ferret was
read-only context at local `6a2eddeb5595`; physical boot/performance/support were not
verified. Keep it an optional future Linux-compatible target with separate validation.
No arriving component is recorded as received until identified by the owner.

## Coverage ledger and decision

The inventories cover **119 integration source/config/test files (16,786 lines)** and
**152 Alpha files (26,379 lines)** at the recorded snapshots; shared files overlap.
They include CSS/HTML/configuration missed by the first inventory. Python AST,
JavaScript syntax and JSON parsing pass; C, shell, TOML and YAML are inventoried but
not generically compiled/validated by that tool. Alpha's suite includes native C
formatter tests; no new ESP-IDF build or hardware validation was performed.

Semantic review concentrated on evidence contracts, WORLD lifecycle/API/UI, parsers,
network validation, logging, time, legacy fusion and scientific endpoints. Remaining
HUD/calibration/driver/tool/test paths have automated repository checks and targeted
inspection, **not a claimed exhaustive line-by-line proof**. Each inventory entry
explicitly says NOT_CERTIFIED_LINE_BY_LINE. Counts are traceability, not quality scores.

**GO:** local offline development and review of this branch, reproducible replay,
mocked acquisition and scoped fixes. **STOP:** claiming all code safe/complete,
enabling blocked legacy paths as calibrated/live WORLD features, merging based only
on this audit, or advancing human/physiology/hardware experiments without their
separate evidence and authorization gates. Next engineering work should close one
listed P1 blocker at a time with its negative control, rather than begin a sweeping
rewrite or new sensor feature.
