# Respiration and heartbeat: what could actually be validated

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** a scoping document. **No claim of vital-sign detection is
made or implied by anything in this project.** The purpose here is to say
exactly what each experiment would need, what it could prove, and what it
could not - before any of it is built.

---

## 0. The scoping rule

A radio-path measurement of a physiological motion is a claim about two
things at once: the *motion* and the *radio path*. Both have to be
controlled, and the ground truth has to be measured on the same clock as
the signal it is being compared against.

Three rules follow, and they are the reason this document is separate from
the motion work:

1. **A signal change is not a detection.** The live HUD says "RF PATH
   CHANGE". A physiological claim needs a *ground-truth instrument* and a
   *pre-registered analysis*.
2. **The ground truth has to be the right instrument.** A peripheral pulse
   sensor is not a ground truth for cardiac timing, and a camera is not a
   ground truth for a radio path. Both are wrong in ways that matter.
3. **The link must be short, stable and local.** A chest-wall displacement
   of a fraction of a millimetre cannot perturb a 30-metre campus path.
   This is not a sensitivity problem that more samples would fix; it is
   arithmetic.

---

## 1. The arithmetic

At 2.4 GHz the wavelength is **124 mm**. A path-length change of Δd
changes the phase by `2π·Δd/λ`.

| motion | typical displacement | phase change | vs. the respiration signal |
|---|---|---|---|
| breathing (chest) | 5 – 12 mm | **0.25 – 0.61 rad** | — |
| heartbeat (cardiac, at the chest wall) | 0.2 – 0.5 mm | **0.010 – 0.025 rad** | **10 – 25× smaller** |
| a person walking | 0.5 – 1 m | 25 – 50 rad | irrelevant |

And the *frequency*:

| signal | rate | period | what a 30 s window holds |
|---|---|---|---|
| breathing | 0.2 – 0.3 Hz | 3.3 – 5 s | 6 – 9 cycles |
| heartbeat | 1.0 – 1.3 Hz | 0.77 – 1.0 s | 30 – 39 cycles |

**Respiration is a large, slow, high-contrast signal. The heartbeat is a
small, fast, low-contrast one.** That single difference drives everything
below.

---

## 2. Respiration

### Feasibility: **plausible, in a controlled link, with the phase**

0.25–0.61 rad of phase change on a 20 dB link is comfortably measurable.
This is the regime where CSI-phase respiration detection is routine in the
literature. It is *not* a stretch.

### What the current pipeline does not do

**The pipeline uses the amplitude only.** `subcarrier_amplitudes()` takes
`hypot(I, Q)` and throws the phase away. But respiration is a *path
length* change: it moves the **phase**, and the amplitude of a sum of
paths often barely changes at all. A body 2 m from the receiver is a weak
reflector; its arrival *phase* shifts with distance while the *magnitude*
of the sum changes far less.

**Using the amplitude for respiration is the wrong measurement, not merely
a weak one.** The complex samples are available on the wire (128 I/Q
values per packet), and the phase has never been used.

### What the experiment needs

| | requirement | why |
|---|---|---|
| **link** | a short, local, controlled link (Option B or C of the [controlled link design](controlled-csi-link.md)) | a campus-length path swamps a 5 mm chest displacement |
| **measurement** | the **phase** of the used subcarriers, and the *differential* phase between subcarriers (or a reference subcarrier) to cancel the common-mode oscillator drift | a common phase wander of the receiver looks exactly like breathing |
| **subject** | seated or supine, still, breathing normally | a moving subject's own motion dominates |
| **sampling** | ≥ 10 Hz, and a window of ≥ 30 s per trial | 0.2 Hz needs several cycles to estimate |
| **ground truth** | a **respiratory belt** (inductance or strain), sampled at ≥ 1 Hz, logged on the **same clock** | the belt is the reference for chest displacement |
| **analysis** | pre-registered: the estimator (a band-pass around the belt-free 0.1–0.5 Hz band, or a matched filter), the agreement metric, and the exclusion rules | see below |

### What it could actually validate

* **Could**: that a 0.1–0.5 Hz component is present in the differential
  CSI phase, and that its **rate** agrees with the belt's rate within a
  stated tolerance (e.g. ±0.05 breaths/min) over N trials, with a
  measured confidence interval.
* **Could**: the **latency** between the belt and the radio path, which
  is a real number a reviewer can check.
* **Could not**: anything about a *moving* person, anything clinical, and
  nothing about disease.
* **Would need to be stated**: the link geometry, the belt type, the
  estimator, and the number of trials - all pre-registered.

### The honest risk

The failure mode is not "the algorithm is bad" but "the geometry is
wrong". A chest 2 m from the board and the board 30 m from the AP gives
a path change of `2·Δd` at best, and only if the body is in the path.
**The subject's position relative to the radio path is the experiment.**
It must be marked, measured and reported.

---

## 3. Heartbeat

### Feasibility: **a research project, not a validation**

0.010–0.025 rad of phase change, against a respiration signal of
0.25–0.61 rad and a receiver's own phase noise. The heartbeat is 10–25×
below the respiration signal in the same measurement.

What would have to be true, all at once:

* the subject is **supine and completely still**, with the radio path
  **coupled to the chest** - the cardiac component at the chest wall is
  a few millimetres of *internal* motion, which is not the same as the
  whole body moving;
* the receiver's **common-mode phase drift is cancelled** (a reference
  subcarrier or a differential phase);
* the link has a **high SNR and a stable short path**;
* the signal is **averaged over many cycles** - 30–60 s per trial, and
  several trials.

Those are not impossible conditions; they are the conditions under which
the published CSI-heartbeat demonstrations are made. They are also a
**different experiment from the motion one**, and they need a different
link, a different subject posture, and a different instrument.

### The ground truth, and why the obvious one is wrong

| instrument | what it measures | usable as ground truth? |
|---|---|---|
| **3-lead ECG** | the cardiac electrical activity, with a clear R-peak | **yes** - the reference for cardiac timing |
| pulse oximeter (SpO2) | the *peripheral* pulse, at the fingertip | **not directly** - it is delayed from the cardiac motion by the pulse transit time, typically 150–250 ms and variable. It can be used *with a stated delay model*, and that delay must be measured, not assumed. |
| a mechanical chest sensor | the chest wall's motion | partial - it measures the same thing the radio is measuring, so it cannot be independent |
| a video of the chest | the chest's surface displacement | partial - it is the *surface*, not the cardiac component, and it has its own latency |
| a microphone | the breath sound | no - it measures airflow, not the radio path |

**A single-lead ECG is a hard prerequisite.** Without it there is no
claim to evaluate: the response would be "a 1.2 Hz component appeared",
which is not evidence of a heartbeat - it is evidence of *something* at
1.2 Hz, and a laptop fan or a music track would also do that.

### What it could actually validate

* **Could**: that a 1.0–1.3 Hz component is present in the differential
  phase in a **coupled, static** geometry, and that its rate agrees with
  the ECG.
* **Could**: the **minimum detectable cardiac displacement** - a real
  number, obtained by attenuating the coupling until the detection fails.
  This is the scientifically valuable result, because it is the one that
  transfers to a real room.
* **Could not**: a claim about a real person's heartbeat from a
  room-scale Wi-Fi link. The published demonstrations use a short,
  coupled, static path for a reason.
* **Could not**: anything clinical, and nothing about a moving subject.

### The scoping verdict

**The heartbeat experiment is a research project, and it should be scoped
as one, with the ECG as a prerequisite and the minimum-detectable-
displacement as the deliverable.** It is not a validation of this
project's sensing claim, and it should not be presented as one.

---

## 4. The required instruments

| experiment | ground truth | minimum specification | why |
|---|---|---|---|
| respiration | respiratory belt (inductance or strain) | ≥ 1 Hz, logged on the host's monotonic clock | the belt is the reference for chest displacement; a camera measures the surface and the timing is not the same |
| heartbeat | 3-lead ECG | ≥ 250 Hz, R-peaks timestamped on the **same clock** | the ECG is the only reference for cardiac timing; a peripheral pulse is delayed by the pulse transit time |
| both | a shared clock | the host's `time.monotonic()`, and the instrument logged against it | without a shared clock the lag can only be guessed, and the lag is the thing being measured |
| both | a controlled link | Option B or C of the [controlled link design](controlled-csi-link.md) | a chest-wall displacement of 0.2–0.5 mm cannot perturb a 30 m campus path |

**On the current campus link, neither experiment is physically plausible.**
That is not a sensitivity problem and more data will not change it.

---

## 5. The order of work

1. **The controlled link** (Option B of the controlled-link design). Until
   the transmitter is local and the geometry is marked, no physiological
   experiment is worth running.
2. **The phase.** Extend the pipeline to keep the complex samples and
   compute the differential phase per subcarrier. This is host-side only,
   needs no firmware, and is a prerequisite for respiration.
3. **Respiration**, with a belt, on the controlled link, with a
   pre-registered estimator.
4. **Heartbeat** only if and only if the respiration rig works and the
   minimum detectable displacement is reported. With an ECG. As a
   research question with a stated negative result as a valid outcome.

---

## 6. What is claimed today

**Nothing.** The live HUD says "RF PATH CHANGE, NOT A HUMAN DETECTION".
The motion experiment has no verified detection (checkpoint 009). This
document is a scoping of what *could* be validated and what would be
needed - not a claim that any of it works.
