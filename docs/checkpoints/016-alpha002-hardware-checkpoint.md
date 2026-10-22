# Checkpoint 016 — Alpha 002 hardware checkpoint

**Date:** 2026-10-22
**Branch:** `feature/alpha002-esp32-supervisor`
**Verdict:** **The firmware is verified on hardware for everything it claims to
do at this stage. Sampling adequacy is unproven.** No flash, no reset, no merge,
no change to host networking in this checkpoint.

Supersedes the subcarrier verdict in checkpoint 015. The v1 score there is
preserved unchanged and is **not comparable** to a v2 score.

---

## 1. The subcarrier defect, and the fix

The v1 check required the set of non-zero subcarrier slots to equal exactly the
52 used slots of a 20 MHz LLTF. I/Q are **int8**: a faint active subcarrier
truncates to exactly `(0, 0)`. One truncation anywhere in a frame failed the
frame, so a healthy link scored 79.7%.

Measured on the preserved capture (672 records):

| Observation | Count |
|---|---|
| Required nulls `{0} ∪ {27..37}` zero | **672 / 672** |
| Exact 52-slot set | 627 / 672 (93.3%) |
| 1–3 extra zero slots in active positions | 45 / 672 |

The 45 exceptions are scattered (slot 55 ten times, slot 39 six, most once),
which is the signature of quantisation, not of a structural change.

**v2 scoring** asserts the property that actually matters:

1. **`subcarrier nulls`** — every required null is zero, in every frame.
   Criterion 100%; a null carrying energy is a real failure.
2. **`active subcarrier coverage`** — all 52 active slots carry energy at least
   once **across the capture**, criterion ≥ 99%. Judged in aggregate so an
   individual truncated slot is not a failure.
3. Fewer than 20 frames to judge → `UNKNOWN`, not a pass.
4. A v1 observation replays as `UNKNOWN` for both lines. The tool refuses to
   infer the v2 answer from a v1 counter.

No other threshold moved: activity 5/s, gap 1.0 s, malformed 0, continuity 95%,
drops 0, drift 0.5%, RSSI −85…−15, noise floor ≤ −80.

## 2. Two further harness defects, found by re-running

1. **A parse error killed the CSI reader.** A spliced line on the native USB
   path (`CSI_DATA,…,csSPECTER_STAT,…`) raised out of `CsiParser.feed`, the
   thread died, and the run reported 0 packets. Preserved as
   `preflight-phone-station-v2-attempt1-crashed.*` — the console path had
   captured 102 KB while the CSI thread was already dead, which is exactly the
   failure mode. `feed` is now wrapped; a bad line counts as malformed and the
   capture continues.
2. **Bytes that arrived before the window were counted as data.** Opening a
   live stream starts mid-record; the backlog is also where splices live. Both
   ports now drain for 0.25 s before the measurement window begins.

## 3. Scores, separately versioned

| | v1 (preserved) | v2 (corrected) |
|---|---|---|
| `scoring_version` | absent | **2** |
| window | 60 s | 60 s |
| CSI packets | 300 | 74 |
| subcarrier nulls | exact-set 79.7% → FAIL | **74/74 clean → PASS** |
| active coverage | — (not measured separately) | **52/52 slots → PASS** |
| malformed / seq gaps / drops | 0 / 0 / 0 | 0 / 0 / 0 |
| USB↔console drift | 0.05% | 0.17% |
| activity | 5.0/s → FAIL | 1.3/s → FAIL |
| longest gap | 1.222 s → FAIL | 16.443 s → FAIL |

The two runs are **not** comparable on rate: v1 was captured while traffic was
being generated, v2 after it stopped. They are comparable on structure, and
there the corrected scoring agrees with the hardware: the IQ map is intact.

v2 is a fresh capture. The v1 run's raw bytes were never saved, so a corrected
score *of that run* cannot be derived; that gap is why `--raw-out` now exists.

## 4. Packet cadence: measured versus hypothesised

**Measured** (123 s, 676 records): median inter-packet interval 0.011 s, p95
0.956 s, 63 gaps > 0.5 s recurring roughly every 2 s, maximum 1.96 s. In the
v2 run, with the phone idle, the maximum gap reached 16.443 s.

**Not measured:** the cause. Power save with a DTIM wake schedule is the
leading hypothesis and would explain the shape, but no 802.11 frame capture was
taken, the phone's power-save state was never read, and there was no control
condition with power save known to be off. "Phone power save" is a hypothesis,
not a finding.

What follows regardless of cause: this station yields bursts separated by long
silences, so it cannot feed the 35 FPS HUD or any timing-sensitive measurement.

## 5. Verified on hardware

| Claim | Evidence |
|---|---|
| App-only write at `0x10000` is safe and sufficient | write + independent read-back verify; bootloader and partition table byte-identical before and after |
| Firmware boots and runs on this board | boot log from `0x10000`, no abort/watchdog |
| SoftAP + own DHCP come up | `SPECTER-LAB` ch 6, `192.168.4.1` |
| **CSI callback fires in SoftAP mode** | `csi_cb` rises with no station at all, and with a station attached |
| Station association and peer identification work | peer MAC stable across the whole capture |
| Channel metadata correct | `ch=6` on all 676 records, no roam |
| IQ structure intact | 128 B / 64 slots on every record; nulls zero 672/672; `first_word_invalid=0` |
| No firmware-side loss | `drop_old=0`, `drop_new=0`, `q=0` throughout |
| Both USB paths carry the same stream | drift 0.05% (v1), 0.17% (v2) |
| Rollback was unnecessary but real | verified before the write; never exercised |

## 6. Still unproven

| Question | Status |
|---|---|
| Dense, gap-free acquisition | **no** — bursts with 1–16 s holes |
| Continuity against a known offered rate | **no** — no controlled generator existed |
| Motion or vital-sign detection | **nothing measured**; no human-subject run |
| SoftAP under WPA2 | **no** — the AP is currently open |
| Correct flash-size declaration | **no** — runtime falls back to 2 MB and warns |
| Cause of the cadence | **hypothesis only** |
| Multi-station behaviour, long soak | **no** |
| Behaviour on the campus network | deliberately not tested |

## 7. Follow-ups

1. WPA2 on the SoftAP (`CONFIG_SPECTER_LAB_PASSWORD` is empty).
2. Declare 16 MB properly in the app image header.
3. A station that does not power-save — second ESP32, or a host with power
   save known to be off — before any timing-sensitive work.
4. Only then: motion, and only against the null distribution.

## 8. Evidence

`runs/alpha002_hw_validation_20261022/` (gitignored):

| File | SHA-256 (first 16) |
|---|---|
| `preflight-phone-station.json` (v1, untouched) | `e727c62b51df2f29` |
| `preflight-phone-station-v2.json` | `fbfac8ee218b6596` |
| `preflight-phone-station-v2.raw` | `ead83703030f8149` |
| `phone-station.raw` (672 records) | `f2c208488d60f975` |

Regression fixtures committed: `tests/fixtures/esp32_csi/phone_station_lltf.jsonl`
— one exact record and two real truncation cases from the capture.

Tests: **287 passed, 1 skipped.**
