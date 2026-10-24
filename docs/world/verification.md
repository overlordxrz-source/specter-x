# SPECTER-WORLD verification and handoff

Verified locally on the Mac, 23 October 2026. Base `dc695c7`; branch `feature/specter-world-desktop`. This document is committed with the tested implementation; `git rev-parse HEAD` identifies the resulting local revision, recorded explicitly in the delivery handoff. No merge, push, remote deployment, physical acquisition or firmware change occurred.

## Observed checks

- **195 tests passed**, 1 hardware deselected, in the integration worktree after second-review remediation. This includes 69 new FRONTIER/WORLD cases. The earlier 442-test feature-branch run is not the integration baseline. The real DI-188 acceptance module was excluded explicitly, including collection, to avoid hardware operation.
- Browser acceptance exercised real navigation, source selection, filtering, observation inspection, scrubbing, play/pause, speed changes, evidence reading, detach/reopen, empty spatial state, viewport resizing and explicit SIMULATED/UNKNOWN/error cases. Final machine-readable checks and screenshots accompany the handoff. No browser JavaScript runtime exceptions were observed.
- The empty offline screen had no signal plot, disabled playback and truthful source states. Its shutdown button returned success and stopped that separate service instance.
- Source SHA-256 `f0323be3d79af1bd5f29fd21b483323c90eeb7be3f90c8e89c980e92d8432b2c`: **7,290 observations**, **299 non-CSI lines**, zero malformed/unsupported records and zero missing source sequence numbers. Raw source hash was unchanged after acceptance.
- An independent CSV-reader route, bypassing `CsiParser` and `CsiReplay`, counted all records. At positions **0, 3,645 and 7,289**, source sequence, native timestamp, RSSI, signal length, physical raw line and independently calculated IQ amplitudes matched WORLD's indexed envelopes. This is an independent software/data cross-check, not a new sensing experiment.
- Real source indexing took **0.585 s** in the recorded acceptance run; the largest sampled state-query duration during loading was **11.01 ms**. Index size was **15,310,848 bytes**.
- An explicitly **SIMULATED 50,000-record** stress source indexed in **4.066 s**, with largest sampled state-query duration **13.45 ms**. Index size **104,370,176 bytes**; query windows stayed at 80 rows and 160 RSSI points; the 256-record registry counted **49,744 retention evictions**. Process high-water RSS for the complete verifier was **66,584,576 bytes**, including its independent reference data. These are observations on this Mac, not latency guarantees or evidence at the one-million-record configuration ceiling.

The inherited warning is NumPy's `RuntimeWarning: invalid value encountered in scalar subtract` from Alpha's `test_pipeline_positive_control.py`. The test passed; this warning is not evidence that nonfinite scientific statistics are valid. No change was made to that experiment.

## Negative controls and defects corrected here

The tests reject duplicate/out-of-order source records, malformed framing, wrong typed CSI payloads, altered capture bytes, changing source files, unknown source origins promoted to hardware, invalid seek/speed/play values, catalog symlink escapes and unauthorized HTTP commands. They also cover lost-newline splices/torn prefixes, clean-source recovery counters, explicit-only replay roots, bounded catalog metadata/scan limits, catalog truncation, and delayed/persistent inspection/evidence responses. Missing timestamps remain unknown. Simulated canonical observations remain SIMULATED. Queue overflows, stale test ingress and disconnect/error/reconnect boundaries are exercised without devices. Concurrent replay source replacements are serialized and covered by a regression test.

Corrections during implementation: play commands previously coerced non-boolean values; a load could restore READY after detach; concurrent replacements needed a lifecycle lock; generic envelopes needed CSI-specific payload checks before rendering; global quality warnings initially used gaps only through the selected record; navigation retained a previous page's scroll position; and delayed prior-session responses could briefly expose old READY controls during a source switch. The UI now enters LOADING immediately and rejects prior-generation responses. A delayed-response browser control exercises that race. These were fixed and covered by Python or browser regression checks. A browser test's initial text selector incorrectly required a metric without its unit; that was a test-selector fault, not a data failure. A resumed tool session also required restarting the local service after the previous process ended; no old process was assumed to remain running.

## Reproduce Python and data acceptance

From the isolated worktree:

```sh
cd "$SPECTER_WORLD_WORKTREE"
PYTHONDONTWRITEBYTECODE=1 "$SPECTER_X_PYTHON" -m pytest -q -p no:cacheprovider --ignore=tests/test_alpha001_acceptance_real.py
PYTHONDONTWRITEBYTECODE=1 "$SPECTER_X_PYTHON" tools/world_verify.py --source "$SPECTER_CAPTURE" --outdir /absolute/path/to/new/private-world-verification
```

The verifier requires a new directory. Its synthetic stress capture is explicitly labeled and removed after verification; it writes a summary JSON. Original recordings are never modified. The complete private capture is not copied into the branch or delivery patch. The source's signal-length distribution includes several lengths besides 28 and 138 bytes; WORLD preserves these actual categories instead of rewriting them as a binary experimental label.

## Reproduce browser checks

Playwright is a development-only test dependency, not an application dependency. The recorded run used Playwright 1.62.1 with an existing Chromium 149.0.7827.55 executable on the Mac. The runtime bundle's default expected browser was absent; the existing browser path was supplied explicitly. No browser download was needed. Safari and the user's actual MacBook window workflow remain unverified; tests cover Chromium running locally at device scale factor 2, including 1512×982, 1280×800, 1920×1080 and 900×700 CSS viewports. These screenshots were produced by the running app and visually inspected, not design mockups.

```sh
python tools/world_ui_fixtures.py --outdir /absolute/path/to/new/world-ui-controls
python -m specter.world --replay /absolute/path/to/phase0-short.raw.csi --root docs/checkpoints --root /absolute/path/to/new/world-ui-controls --no-browser
# In another terminal, use the actual URL printed by that process:
WORLD_URL=http://127.0.0.1:PORT WORLD_SCREENSHOTS=/absolute/path/to/screenshots node tools/world_ui_verify.cjs
```

Install/configure Playwright in the test environment first; `NODE_PATH` can point to its existing package directory. If needed, set `WORLD_CHROMIUM` to a compatible existing Chromium executable. The harness opens the named real Phase 0 source and exercises fault controls when the generated controls directory is supplied. Without those controls, it does not claim those optional browser cases ran. CI automatically runs the WORLD Python cases and JS syntax checks; browser verification is a separate local acceptance command and no remote CI execution is claimed.

## Explicit limits and next integration

Live acquisition is **UNVERIFIED**. `Ingress` is an offline-tested envelope queue, not a dispatcher-to-device implementation. It does not open serial ports, verify physical transport ownership, create raw device captures or make test input LIVE. A future approved transport worker must integrate the existing dispatcher, preserve framing and raw evidence, document clocks, perform exclusive-device checks and supply hardware acceptance before any LIVE UI state can exist.

DI-188 is OFFLINE and thermal UNAVAILABLE. The spatial layer is a truthful empty state: calibrated observations, geometry and synchronization are absent. Native app bundling, physical Newhaven output/touch, Safari, persistent world models, calibrated fusion and authenticated remote nodes remain outstanding. Experimental result/protocol text remains source evidence; WORLD does not rerun Alpha statistics or establish detection. SQLite/source/record limits are guardrails with documented transaction overhead, not a hard operating-system memory sandbox.

OpenCode can review and later reuse `WorldStore`, the API and `Ingress` without changing the frozen Alpha analysis or firmware. Its checkout advanced independently while this branch remained based on FRONTIER; no automatic reconciliation was attempted. Any future integration requires a deliberate review. Keep Alpha recordings and scientific claims immutable.

**Splice limitation:** a splice exactly between a record's metadata and its IQ tail cannot be detected by this checksum-free wire format; it may mix one frame's metadata with another's spectrum. Resilient recovery handles lost newlines and torn prefixes but cannot make that boundary detectable. A checksummed format is separate work.
