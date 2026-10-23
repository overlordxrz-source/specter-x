# Alpha 003 — Human presence with the current single-link ESP32-S3 CSI setup

**Date:** 2026-10-23
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** feasibility and staged plan only. **No human session has been
run. No presence, occupancy, respiration, tracking or localization claim is
made.** Alpha 002-C and its replication protocol are unchanged.

## 1. Bottom line

| question | current hardware | verdict |
|---|---|---|
| Empty vs **moving** human | one 2.4 GHz link, 10 Hz payload CSI, 64 subcarriers | **Physically strong; expected easiest.** Not yet measured as empty-vs-moving. Movement changes multipath and Doppler-like phase quickly; this is still movement detection, not stillness detection. |
| Empty vs **stationary** human | same | **Hard.** A still body changes the *static* multipath by a small amount. That change competes with channel drift, posture, furniture, door state and device orientation. Plausible only with a controlled baseline and long windows; unproven. |
| Three classes | same | **Staged.** Do the two binary questions first. A 3-class result is exploratory until both binaries replicate. |
| Respiration | raw IQ available; 10 Hz; uncalibrated phase | **Exploratory only.** Raw phase exists, but CFO/SFO/packet-boundary jitter dominate; a controlled short link, still subject, 60 s windows and a respiratory belt are prerequisites. Not a product claim. |
| Tracking / localization | one transmitter, one receiver, one antenna each | **Not possible now.** One link gives a scalar/multipath signature, not an angle or range. Needs multiple antennas or links, synchronized clocks and an array/switch; wait for components. |

The honest sequencing is: **moving detection → stationary presence with a
baseline → three-class → respiration → localization.** Skipping to
"occupancy" or "tracking" would produce a demo, not evidence.

## 2. What the current hardware actually provides

| item | current state |
|---|---|
| link | ESP32-S3 SoftAP; phone station; 2.4 GHz, 20 MHz channel 6 |
| traffic | phone ping app, ~10 payload frames/s during trials; null frames alongside |
| CSI | 64 subcarriers (0 and 27–37 unused), 128 raw I/Q integers per frame |
| metadata | RSSI, PHY rate, MCS, channel, noise floor, frame length, sequence, local timestamp |
| raw evidence | the acquisition writes the raw serial stream; trial JSON keeps amplitudes and metadata |
| phase | present in raw IQ; **not calibrated**; per-packet common offset and linear slope |
| antennas | one antenna at each end; no array, no RF switch, no second link |
| clock | host monotonic clock and the board's local timestamp; no phase-coherent shared clock |

### Raw IQ is recoverable without a firmware change

`presence.attach_iq_from_raw()` parses the already-recorded raw stream and
matches each trial sample by CSI sequence id. On the accepted Alpha 002-C
session it matched **11,554/11,554** samples; the IQ-derived amplitude
difference from the stored amplitudes was at most **0.005 ADC count**. All
phase work is therefore host-side and offline. This does **not** make the
phase calibrated; it only means the data exists.

## 3. The physics in one page

For subcarrier `k` and time `t`:

```
H_k(t) = sum_p a_p(t) exp(-j 2π f_k τ_p(t))
```

A person adds a reflection and may shadow the direct path. Both amplitude
and phase change.

| motion | scale | what it does |
|---|---|---|
| walking / arm movement | 0.1–1 m, seconds | large, fast time-varying multipath; easy to see in temporal features |
| standing still | body-sized static change plus 5–12 mm breathing | changes the *mean* multipath pattern; breathing gives a small 0.2–0.3 Hz phase component |
| empty room | no body; slow drift | drift, AGC, temperature and traffic still move the channel |

At 2.4 GHz the wavelength is 124 mm. A 5–12 mm chest displacement is
0.25–0.61 rad of path phase; a 0.2–0.5 mm cardiac displacement is only
0.010–0.025 rad. Respiration is the large slow signal; heartbeat is not a
current target.

The critical distinction:

- **Moving vs empty** is a *temporal variation* problem.
- **Stationary vs empty** is a *distribution shift* problem. The signal is
  the change in the static multipath, not a large temporal variance.
- **Localization** is neither: it needs angle/range diversity that one link
  does not have.

## 4. What each feature can and cannot measure

| feature | physical meaning | useful for | main confounds |
|---|---|---|---|
| `roughness_used` | mean packet-to-packet change of the normalised spectrum | moving vs empty; motion | traffic rate, PHY changes, AGC, real motion outside the area |
| `amp_volatility` | relative change of total amplitude | moving; large body motion | RSSI/AGC, phone power, orientation |
| normalised profile distance | distance of a trial's mean spectrum from an empty reference | stationary presence **with a baseline** | room/drift changes, furniture, device movement; the reference may not transfer across sessions |
| differential-phase roughness | temporal change of phase differences between adjacent used subcarriers | moving; micro-motion; exploratory respiration | CFO/SFO, packet jitter, phase noise; common-mode cancellation is imperfect |
| phase band ratio 0.1–0.5 Hz | slow phase modulation | controlled respiration only | drift, harmonics, subject motion, uncalibrated phase |
| RSSI | one received-power scalar | coarse shadowing / link health | not specific; body orientation and AGC dominate; must be an ablation, not the primary feature |

The phase used here is **differential phase**, not absolute phase. Absolute
ESP32 phase is not a distance: each packet has a common carrier-offset phase
and a sampling-frequency slope across subcarriers. Adjacent-subcarrier
differences remove the common offset; the static slope is removed by
temporal centring. This is a reasonable exploratory feature, not a
calibrated phase measurement. Espressif's phase-coherent sensing examples
use two chips with a shared clock; the current single link does not.

## 5. Why empty vs stationary is the hard problem

1. **The static change can be small.** A body at 0.8 m from a 1.5 m link
   changes the normalized spectrum by a few percent, not by the large
   packet-to-packet swings of walking.
2. **Drift looks like presence.** A door, a chair, a laptop lid, a person
   outside the room, temperature or AGC can shift the mean profile.
3. **Posture changes the profile.** Standing, sitting, arm position and
   clothing change the reflection; a classifier trained on standing may not
   recognise sitting.
4. **The baseline is part of the claim.** With a fresh empty baseline,
   presence can be a change detection problem. Without one, the model must
   generalise across sessions and rooms - a much stronger claim.
5. **Temporal correlation makes naive validation optimistic.** Frames within
   a trial are not independent. Random frame splits leak; the unit must be
   the trial/block/session.
6. **False positives are the deliverable.** An empty room must be reported
   empty, repeatedly, across sessions. A classifier that fires on drift is
   not occupancy sensing.

Public occupancy studies show the same pattern: moving occupants are easier;
the stationary-vs-empty case is the challenging one, and many systems use
multiple antennas or links. Those studies are context, not evidence for this
hardware.

## 6. Experimental design summary

Full protocol: `docs/design/alpha003-presence-preregistration-v1.md`.

- Conditions: `empty`, `stationary` (balanced standing/sitting), `moving`.
- 12 randomised blocks per session, one of each condition per block, 30 s
  per trial, 15 s settle for room transitions; door closed during recording.
- Minimum 3 sessions on different days; target 4–5. Primary evaluation is
  **leave-one-session-out**; no frame from a test session is in training.
- Primary feature/classifier: fixed amplitude + differential-phase features,
  nearest centroid on training-only standardisation. No feature selection
  after looking at the result.
- Primary contrast: empty vs moving (H1), then empty vs stationary (H2).
  Both must be reported; H2 is the presence question.
- Confound gates: modal PHY equality, payload-rate difference ≤ 10 %,
  session/room/door metadata, RSSI-only ablation; if an RSSI-only model
  matches the full model, the result is shadowing, not multipath.
- Uncertainty: session bootstrap intervals, label-permutation null within
  sessions, per-class recall and empty false-positive rate. A single session
  is exploratory; no presence claim from it.
- Posture: standing/sitting balanced inside `stationary`; report each. A
  presence claim is posture-limited if only one posture works.
- Respiration is a separate protocol with a belt and a still subject; it is
  not part of the presence primary.

## 7. Staged plan

### Stage 0 — offline, now (no human, no radio)

- Attach raw IQ to sessions; validate phase reconstruction.
- Compute amplitude, differential-phase and RSSI features.
- Run synthetic empty/stationary/moving controls with known truth.
- Validate session-independent splits, null controls, bootstrap intervals
  and confound ablations.
- **Deliverable:** code and test suite. **Claim:** none.

### Stage 1 — empty vs moving (needs owner authorization)

- One screening session, exploratory; then an independent replication.
- Moving is the easy physical case; a PASS licenses Stage 2, not occupancy.

### Stage 2 — empty vs stationary (needs authorization)

- The hard presence question. Require an empty baseline, balanced
  standing/sitting, door control and cross-session testing.
- If uncalibrated cross-session presence fails but calibrated presence
  works, report **presence with an empty calibration**, not general
  occupancy.
- If it fails, report the bound; do not relabel hand motion as presence.

### Stage 3 — three-class

- Only after H1 and H2 have independent support. Report 3-class balanced
  accuracy and per-class recall; never replace the binary results.

### Stage 4 — respiration

- Separate controlled link/session, seated still subject, 60 s windows,
  respiratory belt on the same clock.
- Uses differential phase; current 10 Hz is adequate for 0.2–0.5 Hz but
  phase noise and link stability are the risk.
- Deliverable: rate agreement and minimum detectable displacement; no
  clinical claim.

### Stage 5 — tracking / localization

- Requires hardware not present: a second synchronized receiver or antenna
  array, RF switch, phase-coherent clock, known transmitter, and ideally
  wider bandwidth.
- One link can say "the channel changed"; it cannot say where.

## 8. Current hardware vs incoming components

| capability | now | needs |
|---|---|---|
| empty vs moving | one link + phone ping | owner authorization; no new hardware |
| empty vs stationary, controlled baseline | one link + marked room + door control | authorization; careful baseline; no new hardware |
| cross-session stationary presence | same | more sessions; measured geometry; time budget |
| phase-based micro-motion | raw IQ, offline | phase quality study; stable link; no firmware change |
| respiration | raw IQ, 10 Hz | still subject, belt/reference, controlled short link, likely longer windows |
| multi-person / occupancy count | no | multiple links/antennas; labelled multi-person data |
| angle/range/tracking | no | antenna array or multiple synchronized links; phase-coherent clock |
| through-wall claim | no | controlled wall/geometry study; not assumed from one link |

## 9. What is claimed today

**Nothing about human presence.** The only completed human evidence is the
Alpha 002-C **hand motion vs stationary** exploratory result, which is a
motion contrast at one marked spot and is pending independent replication.
It is not empty-vs-occupied evidence.

The Alpha 003 code is a test harness: synthetic data, phase reconstruction,
grouped evaluation and honest nulls. Synthetic benchmark numbers are
properties of the fixture, not measurements of a room.

## 10. References used for context

- IEEE DataPort, *CSI Dataset for WiFi Based Human Detection* (empty,
  static-person, dynamic-person occupancy scenarios; 64 subcarriers).
- *Unobtrusive occupancy and vital signs sensing for human building
  interactive systems*, PMC9846702 (stationary occupant vs empty room is
  the challenging case; single sensor in a controlled room).
- *From User Recognition to Activity Counting*, arXiv:2604.16572 (the
  “nothing”/stationary class is the hard class; static multipath rather than
  motion).
- Espressif ESP-CSI documentation (phase-coherent demonstrations use two
  chips with a shared clock buffer).
- *Commodity CSI: Capture Limits and Calibration* (CFO/SFO and packet
  boundary jitter on commodity Wi-Fi; phase needs sanitisation).

These are context for feasibility, not evidence that this board, this room
or this geometry can detect presence.
