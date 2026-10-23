# Alpha 002-C independent replication protocol v1

**Status:** **PLANNED — NOT RUN.** No session, no data and no verdict exists
under this protocol.
**Purpose:** independent replication of the first completed positive
Alpha 002-C result, using the same frozen primary feature and decision
criteria, with measured geometry, a complete ping-counter record and
practical analyst blinding.
**Not:** a re-analysis of the first session, a pooled analysis, a new
endpoint, or a change to the first result.

## 1. Claim under test

In a new session, on a new subject or at minimum with a separate operator and
analyst, `roughness_used` during instructed hand motion is greater than
during instructed stationary standing, using the same 10-block paired design
and the same exact one-sided decision rule.

The first session remains a separate exploratory result. The two sessions
are **not pooled** and the first session is not re-used as a training set.

## 2. Frozen analysis and decision criteria

Unchanged from `tools/alpha002c_motion_v2.py`:

- primary feature: `roughness_used`;
- 10 randomised blocks, exactly one `stationary` and one `hand` per block;
- 25 s active window per trial, 0.10 s guard, `max_gap_s = 0.5`;
- exact one-sided within-block sign-flip, alternative `hand > stationary`;
- **PASS** only if exact p ≤ 0.01, d_z ≥ 0.8 and the bootstrap 95 % CI lower
  bound > 0;
- **INCONCLUSIVE** for a payload-rate difference > 10 % or a different modal
  PHY rate;
- **INVALID** for any frozen validity failure, including a malformed record
  after the first startup torn line, a second torn line, recorder
  `malformed > 1`, clock resets, late frames, missing/empty raw, fewer raw
  CSI records than selected payload frames, trial/design/geometry failure;
- no endpoint, exclusion, threshold or feature change is permitted.

The corrected validator (the one that allows **at most the first startup
torn line**) must be committed and hashed before the session. The original
INVALID output from the first session remains historical evidence and is not
deleted or rewritten.

## 3. Lead-in decision

The **direct replication uses the accepted 3 s lead-in**. This keeps the
estimand identical to the first session.

The 3 s lead-in is not the whole rest: the blocking spoken explanation adds
7.4–12.6 s in the first session, so the observed stop-to-go gap was
10.4–15.6 s. The protocol records these gaps; they are part of the analysis
record.

If the owner wants to remove the Amendment 4 limitation entirely, an **8 s
lead-in** is a different, separately pre-registered robustness session. It
must not be substituted silently for the direct replication.

## 4. Exact physical requirements

### 4.1 Link geometry (measured, not estimated)

Target layout, the same nominal geometry as the first session:

| Quantity | Target | Allowed measured range |
|---|---:|---:|
| Board antenna to phone antenna, horizontal `L` | 1.50 m | 1.45–1.55 m |
| Phone antenna height | 0.80 m | 0.75–0.85 m |
| Board antenna height | 0.80 m | 0.75–0.85 m |
| Subject spot S, lateral offset from midpoint | 0.30 m | 0.25–0.35 m |
| Subject spot S, longitudinal offset | 0.00 m | −0.05 to +0.05 m |
| S horizontal distance to each antenna | 0.808 m | consistency ±0.03 m |
| S slant distance (record only) | 1.137 m | derived |

Procedure:

1. Use a tape measure or laser measure; do not pace or eyeball.
2. Measure `L` between the antenna centres (not the phone body edges) three
   times; record all three values, the mean and the maximum deviation.
3. Measure both antenna heights from the floor to the antenna centre three
   times; record all values.
4. Mark the midpoint of the link on the floor. Mark S at 0.30 m lateral
   offset on the perpendicular bisector; mark the heel/foot position.
5. Measure the longitudinal offset (target 0.00 m) and both horizontal S
   distances; they must agree with the `L`/lateral/longitudinal values within
   0.03 m.
6. Record `"accuracy": "measured"`, `"method": "tape measure"` (or laser),
   `"recorded_utc"`, `"confirmed_by"`, and `"phone_orientation"`.
7. Never record the 1.137 m slant in the horizontal-distance fields.

If any measured value is outside the table, stop before the session; do not
estimate, round into range, or start and hope the analysis accepts it.

### 4.2 Room and apparatus

- Quiet room, door closed; no other people, pets or moving metal in the link
  path during trials.
- Phone and board on rigid **non-metallic** stands; no metal tripods, laptop
  lids, chargers or cables in the first Fresnel zone.
- Phone screen facing the board; record the phone model, board revision,
  firmware commit/version, antenna orientation and USB port.
- Channel 6; peer MAC recorded; same phone hotspot/app as the first session
  where possible. Record the app name/version.
- The ping app must be freshly started with a **numeric counter at 0** (or
  the numeric start count recorded). Do not use `NNN` or an estimate.
- Host: same recorder script, committed and hashed before the session;
  `caffeinate` enabled; serial port recorded.

### 4.3 Subject and instructions

- One adult subject who can stand still for 25 s and sweep one hand for 25 s.
  The subject should not be the analyst. A different subject from the first
  session is stronger; if the owner is the subject, say so explicitly.
- Stationary: stand at S, arms down, feet still, breathe normally, do not
  sway or shift weight.
- Hand: stay at S, feet and torso still, sweep **one hand** across the direct
  line between phone and board at about 1 Hz for the whole 25 s. Keep the
  hand near chest/waist height (record the approximate height); cross the
  line by roughly 0.5–0.6 m; do not step, lean or turn the torso.
- Record clothing, hand used, hand height and any jewelry/pocket contents
  that could affect the link.
- The subject may rest before the session, but no extra rest or coaching
  inside the randomised 20-trial sequence.

### 4.4 Cues and timing

- Automated spoken cues, same host flow: full explanation spoken to
  completion → 3 s silence → one `go` → 25 s → `stop. relax.` spoken to
  completion → guard.
- No manual cueing, no talking over the cue, phone silent.
- Record the stop-to-next-go and stop-to-lead-in gaps for every trial.
- Session length is approximately 12–13 min because the explanations add
  time; the analysis uses sensor time, not wall time.

## 5. Blinding

Subject blinding to condition is impossible: the subject must know whether to
stand or move. Use the strongest practical alternative:

1. The **operator** who cues the subject does not analyse the session.
2. After the session, a **blinding officer** replaces the condition labels
   with codes `A`/`B` using a random mapping and seals the mapping.
3. The **analyst** receives the coded session and computes the primary
   feature table without condition labels. The feature extraction is
   label-independent for `roughness_used`.
4. The blinding officer unseals the mapping and runs the frozen decision
   script, or releases the mapping only after the analyst's feature table is
   frozen and hashed.
5. The analyst records the decision before seeing condition means; the
   unblinding and decision are logged.

If a separate analyst is unavailable, the session is still runnable, but it
must be labelled **unblinded** and cannot be called a blinded replication.

## 6. Ping counter and budget

- Record the app's numeric counter immediately before the first cue and
  immediately after the last trial; photograph or log both values.
- Expected delta: about **7,500** pings for a full 20-trial, 3 s-lead-in
  session (the observed first session was 752.6 s from first lead-in to last
  stop; 5,095 selected payload frames). Budget **≤ 8,000**; stop at 9,000.
- If the app cannot be reset to a known start, do not start the session.
- If the counter reaches 9,000 before the session ends, stop and record the
  session as apparatus-invalid; do not silently use a new app instance.

## 7. Procedure

1. Commit and hash this protocol, the analysis source, the recorder source
   and the test suite. Record the commit hash.
2. Measure and record geometry; write the geometry sidecar.
3. Start the phone ping app at a known numeric count; start `caffeinate`.
4. Run the 10 s non-human pre-check. It must pass the frozen gates
   (~10 payload/s, valid windows, boundary uncertainty ≤ 0.10 s, 0 late
   frames, 0 malformed, max gap consistent).
5. Only after the pre-check passes, run the 20-trial session with a new
   recorded seed, `--lead-in 3`, `--cue`, `--guard 0.10`, `--max-gap 0.5`.
6. Preserve the raw stream, trials JSONL, session JSON, geometry, console log
   and both ping-counter values. Hash them.
7. Run the frozen analysis unchanged. Run the independent minimal
   recomputation as a cross-check. Report both, including any mismatch.
8. Report PASS/FAIL/INCONCLUSIVE/INVALID exactly as the frozen rules define.
   Do not pool with the first session.

## 8. Stop and replacement rules

- No analysis, condition means or p-values may be inspected before the
  session ends.
- Stop only for apparatus/pre-check failure, cue failure, subject inability
  to continue, or a pre-registered validity failure.
- Do not stop because a condition "looks" different, because the subject is
  performing unusually well/poorly, or because a preliminary result would be
  inconvenient.
- If the session is INVALID, preserve it; a replacement requires a new
  session ID and a written reason, and all attempts are reported.
- No endpoint, exclusion or threshold may be changed after seeing data.

## 9. What counts as replication

A **new** session, with its own protocol hash and seed, analysed under the
same primary feature and decision criteria. A PASS replicates the phenomenon;
a FAIL, INCONCLUSIVE or INVALID is reported as such and is not reinterpreted
as a pass. The first session is not counted twice, and the two sessions are
not pooled without a separate pre-registered meta-analysis.
