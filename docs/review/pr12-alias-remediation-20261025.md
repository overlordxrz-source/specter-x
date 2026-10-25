# PR12 identity-scoped legacy status remediation

Owner request: correct OpenCode's remaining P2 finding against
`e30c1e58e93a27f55a99fa3857aac354693a5463`, without changing architectural intent,
merging, starting automation, accessing hardware or modifying frozen evidence.

## Reproduction and fix

The previous global string alias let any ADR use `accepted research policy`.
New sequentially numbered fixtures independently reproduced acceptance of that
status for ADR-007 and synthetic ADR-010, both through the parser and through
generator/checker entry points: **4 failed, 31 passed** before the fix. The
regressions were committed first at `a662a8d`.

Fix `5b4b120ad0f14c5afa788bdaccf00d15b65863fa` changes the alias key to the explicit
pair `(ADR-004, accepted research policy)`. No other ADR matches. Standard
accepted/proposed/superseded status handling remains unchanged. The tests also
caught a malformed empty status line consuming `accepted` from the following
line (1 failed, 35 passed after the identity fix but before this grammar fix).
Horizontal whitespace parsing now rejects that case too.

The exact governing grammar is documented in
[DECISION_CHANGE](../context/DECISION_CHANGE.md#adr-status-grammar). It trims and
lowercases the first field before the first middle dot, then requires an exact
standard status or the single ADR-004 exception. Same-line metadata remains
informational and cannot authenticate owner consent. No existing ADR or accepted
architectural decision was edited.

Both generation (`build_brief`) and checking (`check_adrs`, references and Brief
freshness) call `context_brief.parse_adrs`; there is no parallel permissive
normalizer. Tests exercise both entry points with the same identity fixtures.
The protected process-document hash was refreshed, then the source change was
committed before generating the derived Brief at
`4dd2c3d4299f88ba4f2b19b1c557d09c421dde01`. Its recorded source is `5b4b120…`.

## Verification

- All context tests: **46 passed**.
- Full offline suite: **291 passed, 1 hardware test deselected**.
- Architecture: PASS.
- Context/provenance/freshness: PASS, 23 sources, 18 protected documents,
  9 accepted decisions. The recorded source commit exists and its source hashes
  match; the derived Brief is current.
- Twelve disposable mutation cases rerun against both the old head and fixed
  checkpoint. Missing-source, hash tamper, stale state, invalid ADR reference,
  protected hash mismatch, omitted-governance freshness and pending-prefix
  negative controls remain rejected. Baseline remains valid.

| Legacy alias case | Old generator/checker exit | Fixed generator/checker exit |
|---|---|---|
| ADR-004 | 0 / 0 | 0 / 0 |
| ADR-007 | 0 / 0 (bug) | 1 / 1 |
| Synthetic ADR-010 | 0 / 0 (bug) | 1 / 1 |

The deliberately unauthorized but fully refreshed mutation still passes. This
is the existing documented manual-consent limitation, not a claimed new machine
approval mechanism. Architecture, evidence labels and owner-approval intent
are unchanged. The historical 322-test PR10 integration rehearsal is separate;
PR10 code is not incorporated and its integration was not rerun for this fix.

## Reproduce

From this correction checkout with CI dependencies installed, use new output
directories. The script changes only disposable clones:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests/test_context_protocol.py tests/test_context_review.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -m 'not hardware'
PYTHONDONTWRITEBYTECODE=1 python tools/check_context.py
PYTHONDONTWRITEBYTECODE=1 python tools/check_architecture.py
python tools/review_context_probes.py --ref e30c1e58e93a27f55a99fa3857aac354693a5463 --out /tmp/pr12-alias-before
python tools/review_context_probes.py --ref 4dd2c3d4299f88ba4f2b19b1c557d09c421dde01 --out /tmp/pr12-alias-after
```

Inspect each result's `exit_code` and `generation_exit`; the mutation driver does
not return an aggregate assertion. [Saved machine-readable results and failing
controls](pr12-alias-evidence-20261025.json) preserve the exact outcomes. Original
local logs are in the task's `outputs/pr12-alias-remediation/` directory.

Independent re-review requested at the published final SHA in PR12's update.
Hosted CI is reported in that update after observing its terminal outcome; local
results here are not represented as hosted CI results. No merge or acquisition
is authorized by a passing test.
