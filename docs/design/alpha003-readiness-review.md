# Alpha 003 physical readiness and statistical review

**Date:** 2026-10-23
**Status:** pre-data review. **No Alpha 003 human session has been run.**
**Scope:** Alpha 003 only. Alpha 002-C evidence and its replication protocol
are untouched.

## 1. Verdict

The physical setup is feasible, but the original 3-session confirmatory
plan is **not statistically defensible for a presence claim**. Three
sessions give only three independent test units; a session bootstrap over
three clusters is unstable, and a within-session label permutation does not
test generalisation to new sessions.

Pre-data amendment 1 therefore:

- treats **3 sessions as exploratory only**;
- requires **7 independent sessions** (different days) for a confirmatory
  session-level claim;
- makes the confirmatory test a **session-level exact sign test** on
  per-session balanced accuracy;
- keeps the pooled accuracy, FPR, posture, RSSI-ablation and rate/PHY gates
  as supporting criteria;
- adds a separate **6-block, 20 s, one-session screening** (seed
  `20261024`) that cannot produce a presence claim.

The smallest scientifically useful next experiment is that screening, not
the seven-session confirmation.

## 2. Physical setup for the screening (and confirmatory family)

### 2.1 Room

- Single-occupancy dorm room. **Roommate must be absent for the entire
  session.** A closed door does not make a room empty if the roommate is
  inside; if the roommate cannot be out, do not run.
- Door closed for every recorded window. Door opened/closed only during the
  15 s settle. Record door events; if the door is metal or heavy, use a
  30 s settle.
- No hallway foot traffic if it can be avoided; schedule a quiet period. A
  person walking past in the corridor can perturb the link through the door.
- Fixed furniture. If a chair is used for sitting, it stays in the same
  place for empty and stationary. For the screening, use standing only; no
  chair.
- No fans, moving curtains, pets or other people. Laptop notifications and
  phone sounds off.
- Tape the phone, board, subject spot S and moving path. Tape the laptop
  host position too; it is part of the static environment.

### 2.2 Link

Same controlled link as Alpha 002-C:

| item | target |
|---|---|
| phone-to-board antenna distance | 1.50 m measured (1.45–1.55) |
| both antenna heights | 0.80 m (0.75–0.85) |
| S lateral offset | 0.30 m (0.25–0.35) |
| S longitudinal offset | 0.00 m (±0.05) |
| S horizontal distance to each antenna | 0.808 m (consistency ±0.03) |
| moving path | 1.5 m marked line, ~0.5 m from the link |

Measure three times with tape/laser; record all values. Phone screen faces
the board. Non-metallic stands. No metal in the link path.

### 2.3 ESP32 and phone: do not disturb the traffic

- Phone: ping app foreground, screen on, auto-lock off, plugged in, volume
  off, notifications off. The phone is a fixed transmitter; do not touch it
  between trials.
- ESP32: fixed, powered from the host USB; no re-plug, no reset, no baud or
  port change, no firmware flash.
- Host laptop: fixed on the desk, `caffeinate` on, notifications off, volume
  fixed. It may remain in the room as a static object; it is not a person.
- An **empty trial changes only the human presence**. It does not restart
  the app, pause pings, move the phone/board, change channel/PHY, or change
  the acquisition flags.
- The phone may sleep during empty trials. Check payload rate at the start
  and end of every empty trial; a drop invalidates the trial. The charger
  and auto-lock setting are part of the setup.

### 2.4 Cues

- One cue speaker, fixed position, fixed volume. Use the host speaker or a
  wired speaker; do not use a Bluetooth speaker (2.4 GHz interference).
- One voice at a time. Explanation and `stop. relax.` are blocking; `go`
  is a single short cue. No `--announce`, no overlapping `say`, no OS
  sounds.
- For the screening, a **15 s lead-in** gives the subject time to leave or
  enter and close the door. The cue text must say the condition and the
  lead-in. The same lead-in is used for every trial (no condition-dependent
  timing).
- Rehearse the cue track once with the subject outside and the door closed.
  If inaudible, move the fixed speaker and keep that position for all
  trials; record it.
- The laptop is inside during the screening; the subject can hear the cue
  through the door or when entering. If not, use a wired speaker outside,
  fixed; the door remains closed. Do not put a radio device (phone/BT
  speaker) outside as a cue source.

### 2.5 Empty-trial sequence

1. Setup, tape, phone ping, pre-check.
2. Start cue track. Subject/operator leaves; door closes.
3. 15 s settle; cue names the trial and 15 s lead-in.
4. During empty, no one enters; the phone/board/laptop continue exactly as
   in occupied trials.
5. Stop cue; remain outside until the next cue. Enter during the next 15 s
   lead-in; close the door; go to S/path before the active window.
6. After the session, leave/enter normally; do not move hardware.

If the next condition is moving, the subject needs enough lead-in to reach
the marked path; 15 s is the minimum, 20 s is safer. The screening uses
15 s; if rehearsal shows it is too short, increase it **before data** and
record the change.

### 2.6 Dorm contamination checklist

- [ ] Roommate out for the whole session; confirmed at start and end.
- [ ] Door closed during every active window; door events logged.
- [ ] No other person enters; no hallway conversation at the door.
- [ ] Phone silent; laptop notifications and system sounds off.
- [ ] No music, TV, fan, heater or moving curtain.
- [ ] Chair/furniture fixed; nothing moved between trials.
- [ ] Phone/board/laptop positions taped and unchanged.
- [ ] Ping app visible and running; payload rate checked per trial.
- [ ] Cue rehearsal passed; no overlapping voices.
- [ ] Pre-check passed; no port re-plug.

Any failure is recorded; if it affects an active window, the trial is
invalid rather than silently cleaned.

## 3. Pre-check and continuity

Use the same acquisition and port for the 10 s pre-check and the session.
A reliable sequence:

1. `tools/esp32_lab_preflight.py --seconds 60` for device/USB health and
   counters (existing, unattended, fail-closed).
2. A 10 s `esp32_csi_motion.py record --trial precheck:10 --lead-in 0`
   with the same port, guard and max-gap; require ~100 payload frames,
   valid windows, uncertainty ≤ 0.10 s, max gap ≤ 0.5 s, 0 clock resets,
   0 late frames, and at most the first startup torn line.
3. Only then start the session. If the port stalls or the phone sleeps,
   abort; do not “fix it” by changing configuration mid-session.

The recorder has one port session for the actual trials. Opening the port
for the pre-check is the only re-open; if that causes a stall, the
pre-check itself fails and the session does not start.

## 4. Duration

Assumptions: 15 s lead-in, ~8–12 s blocking explanation, 30 s active,
~1 s stop, 15 s settle for empty transitions; setup/pre-check ~15 min.

| design | active | estimated on-site |
|---|---:|---:|
| screening: 6 blocks ×3 ×20 s | 6 min | **30–40 min** |
| confirmatory: 12 blocks ×3 ×30 s | 18 min | **45–60 min/session** |
| 7 confirmatory sessions | 2.1 h | **~5–7 h total** |
| 3-session exploratory (old plan) | 0.9 h | **~2.5–3 h** |

The confirmatory seven-session commitment is a real cost. It is the price
of a session-level p < 0.01, not an arbitrary preference.

## 5. Statistical amendment 1 (pre-data)

### Problem

- Three sessions = three independent test units. A bootstrap over three
  clusters cannot support a stable 95% CI.
- A within-session label permutation tests whether labels matter inside the
  observed sessions; it does not test generalisation to new sessions.
- With 3 sessions, the smallest session-level sign-test p is 1/8 = 0.125,
  not < 0.01. The old gate could be met only by a within-session p that
  answers a narrower question.
- The old “lower 95% session-bootstrap CI > 0.60” is not credible with
  n = 3.

### Amendment

1. **Screening:** one 6-block ×3×20 s session (seed `20261024`),
   exploratory only. No presence claim. Separate protocol:
   `docs/design/alpha003-screening-v1.md`.
2. **Exploratory 3-session stage:** may run for variance and logistics, but
   no confirmatory claim; its data are not pooled with confirmatory data.
3. **Confirmatory:** minimum **7 sessions**, different days. Session seeds
   are fixed in the freeze manifest. Each session: 12 blocks ×3×30 s.
4. **Primary confirmatory test:** per-session balanced accuracy for empty
   vs stationary; one-sided exact sign test across the 7 sessions; require
   all 7 sessions > 0.5 (p = 1/128 = 0.0078). If any session ≤ 0.5, no
   confirmatory presence claim (6/7 gives p = 0.0625).
5. **Supporting gates:** pooled balanced accuracy ≥ 0.80; empty FPR ≤ 0.10;
   both postures recall ≥ 0.70 (if posture is included); full model beats
   RSSI-only by ≥ 0.05; rate/PHY gates clear.
6. **Session bootstrap** remains descriptive; it is not the primary
   confirmatory p-value. Within-session permutation is also descriptive.
7. **Posture:** the primary confirmatory claim is **standing** presence.
   Sitting is a separate posture-generalisation stage; do not claim
   posture-invariance from standing-only data.
8. H1 (empty vs moving) uses the same session-level structure; H3/H4/H5 are
   exploratory. No endpoint substitution.

Seven sessions is the minimum because 6 sessions give a session-level floor
of 1/64 = 0.0156 > 0.01; 7 give 1/128 = 0.0078. Eight or more are
preferred. A claim is limited to the tested room, link, subject and
protocol; different subjects/rooms are separate replications.

## 6. Pre-freeze

Before any session:

- freeze this review, the screening protocol, the amended confirmatory
  protocol and the analysis code by SHA-256;
- record the commit hash;
- record the screening seed `20261024` and the seven confirmatory session
  seeds before data;
- commit the hash manifest; do not edit a frozen file after data starts
  without a dated amendment.

Seed plan:

| stage | seeds |
|---|---|
| screening | `20261024` |
| confirmatory sessions | `20261025` … `20261031` (7 sessions) |

If a session is aborted, preserve its artifacts and do not replace it
silently; a replacement uses the next seed and is reported.

## 7. Smallest scientifically useful next experiment

**One screening session:** 6 blocks × 3 conditions × 20 s, seed
`20261024`, standing only, 15 s lead-in, 15 s settle, one operator-subject,
door closed, ping app continuous, pre-check passed.

It answers:

- whether the empty/occupied transitions and cues are physically workable;
- whether the empty trial keeps the payload stream alive;
- the feature ranges, phase quality and empty false-alarm rate;
- whether the stationary-vs-empty effect is large enough to justify seven
  confirmatory sessions.

It cannot answer presence. If it is logistically clean and the effect is
not obviously negligible, the next decision is whether to commit to the
seven-session confirmatory study; that decision must not use screening
data to change confirmatory endpoints or thresholds.

## 8. Guardrails

- No human session was run for this review.
- No firmware was flashed.
- No branch was merged.
- Alpha 002-C evidence and its replication protocol are untouched.
- The FRONTIER/SPECTER-WORLD worktree is untouched.
