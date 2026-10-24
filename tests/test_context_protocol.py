"""Offline checks for the Persistent Context Protocol; no devices."""
import json
from pathlib import Path

import pytest

from tools import context_brief as cb
from tools import check_context


def test_repository_context_check_passes():
    result = check_context.check()
    assert result["status"] == "PASS", result["errors"]
    assert result["accepted_decisions"] >= 9
    assert result["source_count"] >= 10


def test_generated_brief_contains_accepted_compute_and_world_truths():
    brief = cb.build_brief(commit="test")
    for phrase in (
        "central command",
        "AR headset-style interface",
        "not a complete self-contained",
        "SPECTER-WORLD is an evidence-grounded",
        "ADR-007",
        "ADR-008",
        "ADR-009",
        "measured, inferred, predicted, simulated, unverified and unknown",
    ):
        assert phrase in brief


def test_adr_sequence_gap_is_rejected():
    sample = """## ADR-001 — One
**Status:** accepted · date

## ADR-003 — Three
**Status:** accepted · date
"""
    with pytest.raises(ValueError, match="sequential"):
        cb.parse_adrs(sample)


def test_malformed_adr_heading_is_rejected():
    sample = "## ADR-7 — Bad number\n**Status:** accepted · date\n"
    with pytest.raises(ValueError, match="malformed ADR heading"):
        cb.parse_adrs(sample)


def test_missing_local_link_is_detected(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("[missing](not-there.md)\n", encoding="utf-8")
    errors = check_context.local_link_errors(tmp_path, [doc])
    assert any("missing link target" in error for error in errors)


def test_missing_local_anchor_is_detected(tmp_path):
    target = tmp_path / "target.md"
    target.write_text("# Present heading\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("[bad](target.md#absent-heading)\n", encoding="utf-8")
    errors = check_context.local_link_errors(tmp_path, [doc])
    assert any("missing anchor" in error for error in errors)


def test_protected_document_mismatch_is_detected(tmp_path, monkeypatch):
    manifest = tmp_path / "protected.json"
    files = {path: cb.sha256_file(cb.ROOT / path) for path in cb.PROTECTED_PATHS}
    files["AGENTS.md"] = "0" * 64
    manifest.write_text(json.dumps({"schema": "test", "files": files}), encoding="utf-8")
    monkeypatch.setattr(cb, "PROTECTED", manifest)
    errors = check_context.check_protected()
    assert any("AGENTS.md" in error and "changed" in error for error in errors)


def test_protected_manifest_covers_every_protected_path():
    data = json.loads(cb.PROTECTED.read_text(encoding="utf-8"))
    assert set(data["files"]) == set(cb.PROTECTED_PATHS)
