# Alpha 003 exploratory screening v1

**Status:** **PLANNED — NOT RUN.** One session, no presence claim.
**Separate from:** `alpha003-presence-preregistration-v1.md` (confirmatory,
frozen with Amendment 1). Screening data are never used as confirmatory data
and are not pooled with it.

## Purpose

Test the physical procedure and estimate variance before committing to the
seven-session confirmatory design:

- can an empty trial be recorded with unchanged ESP32/phone traffic and
  placement?
- do the cues work with the subject outside/inside and the door closed?
- is the payload stream continuous through the whole sequence?
- what are the feature ranges, empty false-alarm rate and phase quality?
- is the stationary-vs-empty signal large enough to justify the full study?

This is **not** a hypothesis test and cannot produce a presence claim.

## Design

| item | value |
|---|---|
| sessions | 1 |
| blocks | 6 |
| conditions per block | `empty`, `stationary`, `moving` (acquired as `walking`) |
| trials | 18 |
| active window | 20 s |
| cue lead-in | 15 s (room transition included) |
| room settle | 15 s after door close |
| seed | **20261024** (pre-registered) |
| posture | standing only |
| evaluation | descriptive; leave-one-block-out or within-session descriptive only |

Trial order is shuffled within each of the six repetitions with seed
`20261024`. The session records `design.seed`, the order, door/roommate log,
and raw stream.

## Empty-trial procedure

1. Phone and ESP32 remain in their taped positions; ping app stays
   foreground; no app restart, no unplugging, no reconfiguration.
2. Subject/operator leaves the room; door closes; cue speaker remains fixed.
3. Wait 15 s; the cue says the trial label and lead-in.
4. During `empty`, no one enters. The laptop, board and phone remain exactly
   as in occupied trials.
5. At `stop`, remain outside until the next cue; the next entry happens
   during the 15 s lead-in, and the door is closed before the active window.
6. If the phone sleeps, payload rate falls, the door is open, or anyone
   enters, the trial is invalid. Do not touch the phone/board to fix it
   mid-session.

## Cues and continuity

- One voice at a time; blocking `say` for the explanation and stop; one
  `go`; no `--announce`, no notifications, no music.
- The cue track must be rehearsed once with the subject outside and the door
  closed; if inaudible, move the **cue speaker** (a fixed, non-RF device) to
  a position that works and keep it there for every trial. Record the
  position.
- The 10 s pre-check and the session run on the same taped setup. Any
  malformed line beyond the first startup torn line, gap > 0.5 s, boundary
  uncertainty > 0.10 s, clock reset or late frame makes the trial/session
  invalid.

## Duration

Approximate: 18 trials × (20 s active + 15 s lead-in + ~8–10 s explanation
+ stop) ≈ 15 min, plus 15 s empty settles and 10–15 min setup/pre-check.
Plan **30–40 min** on site. This is deliberately smaller than the
confirmatory 12-block, 30 s, seven-session design.

## Stop rules

- Abort on phone sleep, port loss, cue overlap, door/roommate violation, or
  a failed pre-check.
- Do not stop because a condition “looks” different.
- No analysis until the session ends.
- Preserve the session even if invalid.
- Screening success is **permission to proceed to confirmatory planning**,
  not a presence result.
