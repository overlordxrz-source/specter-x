# Alpha 003 screening — execution checklist

**Status:** prepared, **NOT RUN**. No human session, no hardware flash.
**Frozen protocol:** [alpha003-screening-v1.md](alpha003-screening-v1.md)
(6 blocks × 3 conditions × 20 s, seed `20261024`, 15 s lead-in, standing only).
**Scope:** this page adds execution detail only. It does not change the
frozen endpoints, conditions, seed or analysis.

## 1. Software-only readiness check

Run before any physical setup:

```bash
.venv/bin/python -m pytest -q \
  tests/test_lab_preflight.py \
  tests/test_acquisition_windows.py \
  tests/test_alpha003_screening_readiness.py
```

The readiness test drives the real recorder through a fake serial source:
18-trial accounting, 6 blocks, balanced labels, blocking cue order, empty-trial
cue text, raw/JSONL/session files and SHA-256 preservation. It never opens a
real port.

## 2. Physical setup checklist

- [ ] Roommate absent for the whole session; confirmed at start and end.
- [ ] Door closed during every active window; door events logged.
- [ ] Phone/ESP32/laptop/speaker positions taped; no re-plug or app restart.
- [ ] Phone ping app foreground, screen on, auto-lock off, plugged in, silent.
- [ ] Non-metallic stands; phone screen faces the board; channel 6.
- [ ] Measure and record phone/board distance and heights; mark S and the
      walking path. Standing only; no chair/sitting.
- [ ] Cue speaker fixed, one voice, volume tested with the subject outside and
      the door closed.
- [ ] Pre-check passed; no other people, fans, notifications or music.

## 3. Preflight

Run the hardware preflight first (manual, no subject):

```bash
.venv/bin/python tools/esp32_lab_preflight.py \
  --seconds 60 --out runs/alpha003_screening/preflight-60s.json
```

It must return **PASS** with no circuit loss, no malformed/sequence gaps and
the expected device counters.

Then run a 10 s same-recorder pre-check immediately before the session:

```bash
.venv/bin/python tools/esp32_csi_motion.py record \
  --trial precheck:10 --lead-in 0 --guard 0.10 --max-gap 0.5 \
  --consent "Alpha 003 pre-check; no subject" \
  --port /dev/cu.usbmodem1101 \
  --raw-out runs/alpha003_screening/precheck-10s.json.raw \
  -o runs/alpha003_screening/precheck-10s.json
```

Required pre-check result:

- ~100 payload frames in 10 s; `valid=True`;
- active window ~10.0 s; boundary uncertainty ≤ 0.10 s; max gap ≤ 0.5 s;
- 0 clock resets, 0 late frames, at most the first startup torn line;
- phone stays awake and ping traffic continues.

If the preflight or pre-check fails, stop. Do not “fix it” by changing the
phone, port, channel or acquisition flags and continuing.

## 4. Screening command

```bash
.venv/bin/python tools/esp32_csi_motion.py record \
  --trial empty:20 --trial stationary:20 --trial walking:20 \
  --repeats 6 --shuffle --seed 20261024 --lead-in 15 --cue \
  --guard 0.10 --max-gap 0.5 \
  --consent "subject: <name/self>, informed: yes, authorized: <date>, local only; Alpha 003 screening" \
  --port /dev/cu.usbmodem1101 \
  --raw-out runs/alpha003_screening/session.json.raw \
  -o runs/alpha003_screening/session.json
```

The recorder builds six blocks, shuffles the three labels within each block,
and emits 18 trials. `walking` is the acquisition label for the analysis
condition `moving`. The cue explanation is blocking; `go` follows a 15 s
lead-in; `stop. relax.` is blocking.

## 5. Empty-trial procedure

1. The subject/operator leaves the room; door closes.
2. Wait 15 s; the cue names the trial.
3. During `empty`, no one enters. The laptop, board and phone stay exactly as
   in occupied trials.
4. At `stop`, remain outside until the next cue. Re-enter during the next
   15 s lead-in; close the door before the active window.
5. Check the phone/payload at the start and end of every empty trial. A drop
   invalidates the trial.

## 6. Expected accounting and duration

- 18 trials: 6 `empty`, 6 `stationary`, 6 `walking`.
- 6 blocks: each contains exactly one of each condition.
- 20 s active per trial; 15 s lead-in; 15 s room settle; seed `20261024`.
- Plan **30–40 min** on site including setup and pre-checks.

## 7. Evidence preservation

Keep even invalid/aborted sessions:

```text
runs/alpha003_screening/
  preflight-60s.json
  precheck-10s.json / .raw
  session.json / .raw / .trials.jsonl
  setup-log.md                 # room, door, roommate, geometry, notes
  SHA256SUMS
```

After the session:

```bash
cd runs/alpha003_screening
shasum -a 256 preflight-60s.json precheck-10s.json precheck-10s.json.raw \
  session.json session.json.raw session.json.trials.jsonl setup-log.md \
  > SHA256SUMS
```

Do not edit or overwrite evidence. Analysis is offline and separate from the
recording; no endpoints are changed after seeing data.

## 8. Authorization instruction

Send exactly this, filled in, before the session starts:

> I authorize the Alpha 003 one-session screening in **[room]** on **[date]**,
> under `docs/design/alpha003-screening-v1.md` and this execution checklist,
> with subject **[name/self]** and operator **[name]**. This authorizes the
> 18-trial screening only: no other human trials, no firmware flashing, and no
> merge of Alpha 003 or SPECTER-WORLD work.

No session may start without that authorization and a fresh PASS pre-check.
