# Independent review — PRs #7–#9

24 October 2026. Read-only review of the exact heads below; live GitHub
metadata confirms all three remain open drafts at those heads. No approval,
comment, branch change, push or merge was submitted. See the
[work order](bench-foundation-work-order.md) and [executable results](pr7-pr9-probes-20261024.json).

| PR | Reviewed head | Independently run offline suite | Local verdict |
|---|---|---|---|
| #7 team | `939240eb34e158a9cf038291cb9c73c468ebe5d3` | 266 passed, 1 hardware deselected | Original two controls validated; P2 API validation follow-up; not validated for WORLD |
| #8 GNSS | `9ca4f3aa32d410ebcc2e04ec30167fdda3234ba2` | 290 passed, 1 hardware deselected | **Request changes**: physical validity still bypassed |
| #9 radar | `9e2f1d57bf1826f30b0c871284761388e46c3fc9` | 265 passed, 1 hardware deselected | **Request changes**: incomplete-frame recovery has no deadline |

These are targeted source/diff reviews and independent executions, not an
exhaustive sensor-driver or hardware certification. Some findings are
inherited gaps left open by a hardening PR, not newly introduced regressions.

## P1 VERIFIED BUG — GNSS receiver-invalid 3D fixes still anchor

At PR #8, `specter/sensors/gnss/neom9n.py:96–113` drops NAV-PVT
`flags` at payload offset 21. `pvt_to_measurement:125–155` constructs
positive confidence from fix type alone. `specter/localization/ekf.py:185–207`
checks fix type/satellite count but has no receiver-validity bit to check.

Two checksum-correct UBX frames differing only in `gnssFixOK` (clear/set)
both anchor `(47,8,400)` and enter GNSS mode. The fixture builder itself
sets byte 11 (date validity), not byte 21 (fix validity), so its default
“valid fix” tests conceal this distinction.

The [u-blox NEO-M9N SPG 4.04 interface description](https://content.u-blox.com/sites/default/files/u-blox-M9-SPG-4.04_InterfaceDescription_UBX-21022436.pdf),
UBX-NAV-PVT table, pages 141–143, defines `flags.gnssFixOK` independently
of the dimensional fix type. Exact installed receiver firmware is unknown.

**Minimal fix:** preserve receiver flags and explicit validity through the
adapter, reject unknown/false validity before EKF mutation; correct the
fixture builder and test matched flags-on/off frames. Keep NMEA validity
explicitly separate rather than inventing a UBX flag for NMEA.

## P1 VERIFIED BUG — NMEA integrity/quality is discarded

At PR #8 `neom9n.py:167–198`, the parser strips the checksum without
validation and maps every positive quality integer to 3D. A normal GGA
sentence with deliberately wrong `*00` checksum anchors the filter; a
checksum-correct sentence with unsupported quality **99** also anchors it.
No spoofing hardware is needed; the supplied probe uses strings only.

**Minimal fix:** strict sentence/checksum and quality allowlist, explicit
provenance and estimated accuracy semantics, rejection without state mutation.
If this exceeds the PR scope, disable NMEA anchoring until its dedicated
validity audit is complete. Do not describe the present path as accepting
only valid physical fixes.

## P2 VERIFIED BUG — repeat GNSS evidence adds precision again

At PR #8 `ekf.py:228–246`, equal timestamps and the same Measurement ID are
accepted repeatedly. Reapplying the exact same object reduces Pxx
**12.5 → 8.333333333333332** without new evidence. This is an inherited
identity gap, distinct from rejecting old timestamps.

**Minimal fix:** reject/idempotently ignore duplicate measurement IDs per
epoch; freeze identity and same-timestamp policy. A new independent fix may
share a host timestamp, so a blanket timestamp-only deduplication is inadequate.
First-fix epoch initialization remains a **documented limitation**: it cannot
establish physical freshness without an independent clock reference.

## P1 VERIFIED BUG — plausible corrupted radar length blocks recovery

At PR #9 `specter/sensors/radar/tlv.py:145–149`, a shape-valid incomplete
header waits indefinitely for its declared length. A 40-byte corrupt prefix
declaring 4096 bytes followed by a complete 96-byte reference packet emits
**0 frames**. Ten more complete packets still emit **0**. Adding 4096 dummy
bytes finally releases all **11** good frames. An idle stream has no expiry
or end-of-stream operation, so loss can persist indefinitely after corruption.

**Minimal fix:** explicit bounded assembly deadline/end-of-stream policy with
diagnostic resynchronization and a fragmented-valid-frame control. Do not
blindly search every payload for magic: legal payload bytes can resemble a
header. Choose bounds from the supported firmware/configuration and test an
oversized plausible prefix plus valid trailing frames.

The basic length-1 rejection, finite-points check and frozen fixture parse
are **VALIDATED offline**. Physical board/SDK compatibility is **DATA
UNAVAILABLE**. The fixture is spec-derived. The vendor
[OOB output guide](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/1023/6153.understand_5F00_OOB_5F00_output.pdf)
describes configuration-dependent TLV presence and payload-only TLV lengths;
its header-length prose says 44 bytes whereas its displayed fields sum to
40. Pin the exact SDK source/configuration before hardware enablement. A
missing points TLV alone is **not** classified as a bug: output is configurable.

## P2 VERIFIED BUG — direct team API permits NaN confidence

At PR #7 `specter/fusion/team.py:250–252,320–325`, peer confidence and parent
IDs are not fully validated/snapshotted at ingestion. A direct TrackReport
with NaN confidence produces a TeamTrack with NaN confidence. JSON decoding
rejects this, so this finding is specifically the public Python API, not a
demonstrated network bypass. Validate before enqueueing and copy accepted
metadata; keep failure from poisoning the next valid report.

Original stale-peer rejection and shared-parent covariance **1.0**, rather
than 0.5, independently reproduce. Disjoint IDs still do not prove
independence, report-creation time is not acquisition age, and a shared
frame string is not an anchor/calibration proof. These are explicit
limitations; keep team fusion outside WORLD's validated path.

## Reproduce

Use the project's Python environment, with each snapshot in a separate
read-only checkout. No device is opened by these commands:

```sh
PYTHONDONTWRITEBYTECODE=1 python tools/review_pending_prs.py \
  --team /Users/overlord/.cache/review-pr7 \
  --gnss /Users/overlord/.cache/review-pr8 \
  --radar /Users/overlord/sideprojects/specter-x-radar
# At each exact head:
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -m 'not hardware'
PYTHONDONTWRITEBYTECODE=1 python tools/check_architecture.py
```

## Integration gate and next work

No integration recommended for #8/#9 until the reproduced findings are
resolved and independently retested. Preserve #7's working original controls
and address its smaller API validation issue. Re-run combined tests on an
explicitly authorized integration branch later; separate branch counts cannot
be added together. No existing branches, frozen protocols or PRs were edited.

The remaining IMU finite-vector fix and NODE recording seam are developed
locally in this separate bench branch. Their verification does not change
these PR verdicts or promote any physical sensing capability.
