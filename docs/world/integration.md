# FRONTIER / WORLD integration review

23 October 2026. Base `main` / `origin/main`: `7ca4a8a` (latest canonical handoff merged into this remediation branch; the original integration base was `1edabbc`). Branch `integrate/frontier-world-main`, isolated worktree `$SPECTER_WORLD_WORKTREE`. Source milestones: FRONTIER-001 `dc695c7` and SPECTER-WORLD `9520377`. This is a draft integration for review, not a merge or hardware release.

## Canonical main and conflict decisions

Read main's documentation hub, North Star, research ideas, architectural decisions, experiment ledger and agent handoff before applying either milestone. Main's current Alpha 002-C status is exploratory positive with independent replication pending; Alpha 003 is prepared but not authorized. This platform integration supplies no new sensing evidence and changes neither status.

FRONTIER conflicts: `.github/workflows/pytest.yml`; `docs/README.md`; handbook architecture, backlog, handoff, hardware-inventory, north-star, research-program, roadmap and verification-baseline; deleted `docs/inventory.md`. WORLD conflicts: pytest workflow and documentation hub.

Resolution: retain main's entire workflows, CI dependencies and handbook byte-for-byte. Preserve the automatic `pytest -m "not hardware"` job, its triggers/concurrency, the hardware marker and the separate manual hardware workflow. The new tests are collected by this existing automatic job. No old workflow replaces it. Add only new links to the hub; preserve its complete existing content. Honor main's deletion of `docs/inventory.md`; link to the new readiness dossier/JSON instead. Add platform/WORLD documentation in their own directories. Keep the canonical project-memory files unchanged.

Main does not contain the ESP32 parser package that FRONTIER previously depended on. Import `dispatcher.py`, `protocol.py` and the committed three-row hardware fixture from the exact `9520377` snapshot, with a minimal package initializer. Do not import the Alpha supervisor driver, acquisition tools, statistical analysis, experimental tests, checkpoint rewrites or firmware. Existing Measurement and scientific code on main remain unchanged. The app change is eleven added CLI/dispatch lines; the remaining implementation is isolated in platform/WORLD packages.

## Unauthorized edit investigation and coverage

The working copy removed nineteen lines from the browser harness after WORLD commit `9520377`, at filesystem mtime **2026-10-23 18:41:38.862923 UTC**. The saved deletion patch hashes to `f4740d97ecc04dcbdca7f89ab6aae3c583f27a81e398ab26e06159ab4839f856`. Exact before/after files, patch and metadata were preserved in private task artifacts before restoration. The original feature working copy was restored only after its hash still matched that preserved copy.

**Origin remains UNATTRIBUTED.** Filesystem metadata does not identify a writer. The current Codex transcript contains the addition, commit and later discovery, but no removal command in the edit interval. The searched local OpenCode database contained no matching tool record; the read-only bridge inventory does not supply a writer audit for that file. These searches do not exclude other processes or stores. No agent or person is accused, and no author was inferred from timing alone.

The committed delayed-response block is retained. An additional observation now checks that the previous session's READY state never reappears after the delayed response arrives. **31 browser checks pass.** On a separate temporary frontend with the generation guards disabled, the browser harness fails specifically at `Prior-session READY response never reappears`. No production file was mutated for that negative control. This proves that the guard-specific check can fail; it does not establish correctness for every possible race.

## Verification on this integration

[Machine-readable results](integration-verification.json) record exact results and protection count. Main baseline: **126 passed, 1 hardware deselected**. Integration: **195 passed, 1 hardware deselected**; all **69 new** FRONTIER/WORLD cases are retained. There are no test failures or new Python warnings. The older 442-test feature-branch result included Alpha code/tests that main does not contain; importing those experiments just to reproduce a count would be an incorrect integration.

The local environment has no `pip` module; `uv pip check --python "$SPECTER_X_PYTHON"` verified all eight installed packages compatible. Runtime imports, CLI startup, JS syntax and launcher syntax passed. Browser verification used existing Playwright 1.62.1 and Chromium 149.0.7827.55 on the Mac. No missing application runtime dependencies remained. Main's existing CI installs its own dependency set; its remote result is reported separately on the draft PR.

The integration service launched and indexed the original, read-only **7,290-record** CSI source, preserving its hash and native timestamps. Independent raw-CSV checks matched source count and sampled amplitudes/RSSI/signal length/raw lines. The **50,000-record simulated** stress run completed in 3.971 s; largest sampled query time during loading was 11.61 ms. These are local observations, not real-time guarantees or human-sensing evidence. No serial/camera connection was opened. Screenshots are actual app output.

## Reproduce and hand off

```sh
cd "$SPECTER_WORLD_WORKTREE"
PYTHONDONTWRITEBYTECODE=1 "$SPECTER_X_PYTHON" -m pytest -q -p no:cacheprovider -m 'not hardware'
./SPECTER-WORLD.command
```

The launcher includes main's current handbook among the explicit evidence roots. `--replay` loads its one initial source but no longer authorizes the capture parent. Browser acceptance commands and fault controls are in [verification](verification.md); use this worktree and a fresh output directory. Run `tools/world_ui_verify.cjs` with both the preserved Phase 0 capture and generated fault controls available. The delayed-response block must not be removed to make a run pass.

Main's project memory, firmware and frozen Alpha records stay intact. The separate Alpha feature checkout is not modified. The draft PR contains no private raw recordings, temporary indexes, browser dependencies or local audit transcripts. A push and draft PR are owner-authorized; merging, flashing, deployment and new physical/human experiments are not.

## Review remediation (23 October 2026)

Addressed the independent review against `daaf081`:

- `CsiReplay` now uses the canonical `feed_resilient` parser, recovers records from lost-newline splices and torn prefixes, preserves the physical raw-line reference and adds `spliced_line`/`torn_line` quality flags plus `spliced_lines`/`recovered_records` counters. Regression tests cover both cases.
- `--replay FILE` no longer adds the capture's parent to approved roots. Browsing requires an explicit `--root`; sibling and symlink escape tests remain fail-closed.
- `inspect()` and evidence responses now use the same request-generation guard as refresh; delayed inspection/evidence controls are in the browser harness.
- `catalog()` uses a bounded per-directory heap and a separate `SCAN_LIMIT`; it stops at `CATALOG_LIMIT`, exposes `truncated`/`limit`/`scan_limit` metadata, and the UI states that a partial catalog is not complete. Tests cover the 512-item cap and scan exhaustion.
- Integration docs use portable environment placeholders and no longer describe a review branch as canonical. The launcher keeps its existing fallback and accepts `SPECTER_X_PYTHON`/`SPECTER_WORLD_CAPTURE` overrides.

Re-run after the second review: **195 Python tests passed, 1 hardware deselected; 31 browser checks passed.** The source capture remained read-only and its SHA-256 was unchanged.
