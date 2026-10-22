# SPECTER-X checkpoint 009 — the motion experiment ran; it did not detect an effect

**Date:** 2026-10-21
**Branch:** `feature/alpha002-esp32-supervisor`
**Status:** the **first real motion experiment** was run with a consenting
subject. The pipeline works end to end. **The result is negative, and it is
negative in an informative way**: the apparent effect in the raw CSI
amplitude is confounded with the received signal level, and once the gain is
divided out the three conditions do not separate.

**No firmware was flashed. The 16 MB backup is untouched.**

---

## 1. What was run

`tools/esp32_csi_motion.py record`, 9 trials of 30 s, three repetitions of
each condition, all inside **one** port session (opening and closing the
CDC port repeatedly is itself a stall trigger — checkpoint 008):

| | |
|---|---|
| Conditions | `stationary`, `hand` (wave one hand up and down), `walking` (a few steps back and forth) |
| Subject | the operator, consenting, moving near the board |
| Cues | spoken out loud (`--announce`) with a 6 s lead-in, so the subject follows the run without watching a screen |
| Link quality | **64 643 packets, 1 gap, 1 missing, 1 malformed** across the whole session |
| Recording | `runs/campaign/motion_live.json`, 87 MB, SHA-256 recorded in the evidence file |

The harness, the statistics and the null control were built in checkpoint
007; this is the first time a person has been in the loop.

---

## 2. The result

### The raw amplitude *looks* like it separates

| Condition | Trials | Total amplitude, mean | Spread | RSSI, mean | Spread |
|---|---|---|---|---|---|
| stationary | 3 | 560.3 | 367.7 | −67.9 | 5.8 |
| hand | 3 | 640.0 | 702.4 | −67.4 | 8.3 |
| walking | 3 | 825.8 | 247.7 | −64.3 | 2.3 |

Per trial: stationary 414 / 782 / 484, hand 520 / 1051 / 349, walking
932 / 862 / 684.

Walking does look higher. But look at the **spread** column: within a single
condition the three trials differ by 368 to 702 — *more* than the 265
between stationary and walking. The per-trial RSSI moved from −70.5 to
−62.6 dBm and back over the session, and **the total CSI amplitude tracks
the RSSI almost perfectly**: the within-trial correlation between a packet's
total amplitude and its RSSI is **0.62 – 0.93 in every single trial**.

### The gain-free features do not separate at all

The total amplitude of a CSI packet is nearly proportional to the received
power, so it is a *radio* metric wearing a motion metric's clothes. The
tool now computes features with the packet's own gain divided out, and with
the temporal behaviour that a moving body actually changes:

| Feature | stationary | hand | walking | F (2,6) | p |
|---|---|---|---|---|---|
| Shape roughness | 0.00101, 0.00076, 0.00100 | 0.00082, 0.00079, 0.00122 | 0.00072, 0.00075, 0.00087 | 0.909 | **0.452** |
| Amplitude volatility | 0.0911, 0.0836, 0.0876 | 0.0815, 0.0834, 0.0886 | 0.0881, 0.0848, 0.0849 | 0.612 | **0.573** |
| amplitude~RSSI corr. | 0.618, 0.863, 0.819 | 0.835, 0.927, 0.724 | 0.826, 0.818, 0.906 | 0.565 | 0.596 |
| *total amplitude* (confounded) | | | | 0.886 | 0.460 |
| *RSSI* (the confounder) | | | | 1.166 | 0.373 |

**Nothing reaches p < 0.05.** The per-carrier screen gives max F = 1.454
against a critical value of 5.14.

### The verdict

> **NOT separable** — no effect was detected. This is the noise floor, so
> more trials or a stronger stimulus are needed.

---

## 3. A false positive, found and fixed

The first version of the tool reported **"conditions are separable (max F
1.454)"**. That was **wrong**, and it is worth recording how.

The tool's verdict threshold was `max F > 1.0`. An F statistic of 1 is the
*minimum* possible value of the ratio and means "no better than chance";
using it as a "there is a signal" threshold turns noise into findings. The
threshold is now the actual α = 0.05 critical value from the F distribution
(5.14 for 3 conditions, 4.26 for 4), and the tool computes the p-value
properly with a pure-Python F distribution — no new dependency. The
implementation is checked against the standard critical values:

```
P(F(2,6)  > 5.14) = 0.05006      P(F(2,9) > 4.26) = 0.04991
P(F(2,6)  > 12.59) = 0.00713     P(F(2,6) > 1.00) = 0.42187
```

A tool that says "separable" when the statistics say otherwise is worse
than no tool, because it will be believed.

---

## 4. Why it probably failed, and what to change

Three reasons, in order of how much they probably mattered:

1. **The subject was probably too far from the board.** The ESP32 captures
   the **access point's downlink** CSI — the radio path that matters is
   *AP → ESP32*. A person moving near the AP barely changes that path; a
   person moving **next to the ESP32, or between the board and the AP**,
   changes it a lot. This is the single most likely cause of a null result
   and it is a question only the subject can answer.
2. **Three repetitions per condition is too few** for a metric whose
   within-condition spread is this large. Five or six, with the order
   **randomised**, is the minimum. The order is now randomised by
   `--shuffle`, because in this run the condition was correlated with the
   session's drift, and drift is exactly what the metric cannot distinguish
   from a subject.
3. **The metric may still be the wrong one.** The features that separate
   people from a static channel in the literature are dominated by
   *short-window* subcarrier variation and by the ratio of the CSI to the
   smoothed CSI over a sub-second window, not by the total amplitude or by
   a whole-trial statistic. The next metric should be computed over ~0.5 s
   windows, not over 30 s trials.

### The recommended next run

```
python3 tools/esp32_csi_motion.py record \
  --trial stationary:60 --trial hand:60 --trial walking:60 \
  --repeats 5 --shuffle --seed 7 --announce --lead-in 6 \
  --consent "..." -o runs/campaign/motion_run2.json
```

* **6 repetitions, 60 s each, randomised order** — 15 minutes.
* The subject **adjacent to the ESP32 board**, ideally standing between the
  board and the access point, and staying in that spot for the stationary
  trials so the geometry does not change between conditions.
* A **stationary trial at the end**, as a return-to-baseline control.

---

## 5. What was changed in the tooling

| Change | Why |
|---|---|
| `--announce` and `--lead-in` | a subject can follow the run by ear, without watching a screen |
| `--repeats` and `--shuffle` (`--seed`) | the condition must not be correlated with the session's drift |
| `motion_features()` | gain-free features: normalised shape, roughness, amplitude volatility, amplitude~RSSI correlation |
| `condition_test()` | a real one-way ANOVA with p-values per feature |
| `f_sf()` / `one_way_f()` | the F distribution, implemented in pure Python and checked against the standard critical values |
| `condition_comparison()` | trials aggregated by condition, with the spread shown next to the mean |
| the verdict threshold | `max F > 1.0` → the α = 0.05 critical value, with the p-value reported |

The null carriers (26–37) remain excluded from the per-carrier statistic,
and the stationary reference profile is unchanged.

---

## 6. Limitations

1. **n = 3 per condition.** Everything here is a first look.
2. **The subject's position is unrecorded**, so the most likely cause of the
   null result cannot be checked from the data.
3. **The metric was chosen after seeing this data.** The gain-free features
   were not specified before the run, so they carry the usual multiple
   comparisons caveat. The re-run must use a metric fixed in advance.
4. **The session drifted 8 dB in RSSI**, and no drift control was built in
   beyond the randomised order.
5. **The conditions were not randomised in this run** — they were a fixed
   rotation, which is why the drift and the condition were correlated.
6. **One gap and one malformed line in 64 643 packets** — the link itself
   was healthy, so the link is not the explanation for the null result.

---

## 7. Artefacts

| Path | What |
|---|---|
| `docs/checkpoints/evidence/motion_trial_20261021.json` | the compact summary, with the full recording's SHA-256 |
| `docs/alpha002/csi_motion_trials.png` | the per-carrier profile of the nine trials |
| `tools/esp32_csi_motion.py` | the harness, with the statistical fixes |
| `runs/campaign/motion_live.json` | the full 87 MB recording (git-ignored) |
