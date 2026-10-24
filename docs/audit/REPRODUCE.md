# Reproducing the offline audit

Run from the isolated audit checkout. Use an environment with the project's CI
requirements plus pyserial. Do not operate the physical-hardware test. Python 3.11
was used; minimum-version and target-device matrices were not executed.

```sh
python -m pytest -q -p no:cacheprovider -m 'not hardware'
python tools/check_architecture.py
PYTHONPATH=. python tools/audit_legacy_probes.py
python tools/audit_inventory.py --root . --out /private/audit-inventory.json
```

The legacy probe intentionally reports known failures; its execution succeeding is
not a release pass. Inventory uses `node --check` for JS/CJS. It never imports the
application being scanned. Review `source-inventory.json` for exact hashes.

Private evidence paths used on the owner's Mac:

```sh
python tools/audit_alpha_raw.py \
  /Users/overlord/sideprojects/specter-x/runs/alpha002c_motion_v2/session.json.raw \
  /Users/overlord/sideprojects/specter-x/runs/alpha002c_motion_v2/session.json
python tools/world_verify.py \
  --source /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi \
  --outdir /private/world-audit-replay
```

The raw check is deliberately narrow to the frozen 10-pair Alpha v2 design. It is
not a general inference engine. Run Alpha tests in a separately archived `285bc2c`
snapshot with `PYTHONDONTWRITEBYTECODE=1` and cache provider disabled. Its independent
recompute CLI accepts `session.json --result result.json --out /private/recompute.json`.
Never run a recorder as part of these checks or overwrite source result files.

For browser acceptance, first create synthetic controls in a new private directory:

```sh
python tools/world_ui_fixtures.py --outdir /private/world-controls
python -m specter.world --no-browser \
  --replay /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b/phase0-short.raw.csi \
  --root /Users/overlord/sideprojects/specter-x/runs/alpha002_hw_validation_20261022b \
  --root docs/handbook --root /private/world-controls
```

Use the printed loopback port. Only explicit roots are browsable; `--replay` alone
does not authorize its parent. This verification explicitly grants read-only access
to that existing evidence directory. Browser tests switch replay sources and controls;
they do not operate hardware. Use an installed Playwright and compatible Chromium:

```sh
WORLD_URL=http://127.0.0.1:PORT \
WORLD_CHROMIUM=/absolute/path/to/chromium \
WORLD_SCREENSHOTS=/private/world-screenshots \
node tools/world_ui_verify.cjs
```

Set NODE_PATH when Playwright lives in a bundled dependency directory. The installed
Chromium path was supplied explicitly; no browser or model was downloaded for the
run. Shut down the service afterward. Preserve the delayed-response observer test.
A regression mutation may remove the **refresh** generation guards only in a copied
web-assets directory served by an isolated test process; the harness must then fail
at `Prior-session READY response never reappears`. Never mutate the working source
or suppress that failure to obtain a passing verification artifact.

Full private logs, before-fix failures, the pre-reconciliation patch, raw recompute,
mutation failure and screenshots are under this Codex task's `work/full-audit/` and
`outputs/full-audit/` directories. Original capture files remain in the research
repository. They are not copied into this branch or published by this work.
