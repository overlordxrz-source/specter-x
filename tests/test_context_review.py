"""Independent PR11 regressions, software-only; no approval inferred."""
import pytest
from tools import context_brief as cb
from tools import check_context


@pytest.mark.parametrize("status", ["accepted_pending_owner_approval", "acceptedness", "proposedness", "supersededness"])
def test_adr_status_negative_control(status):
    with pytest.raises(ValueError, match="invalid status"):
        cb.parse_adrs(f"## ADR-001 — Test\n**Status:** {status} · date\n")


def test_proposed_is_not_active_accepted():
    adrs = cb.parse_adrs("## ADR-001 — Draft\n**Status:** proposed · awaiting owner review\n")
    assert cb.active_decisions(adrs) == []


def test_protected_source_coverage_negative_control():
    paths = {s["path"] for s in cb.load_sources()}
    assert set(cb.PROTECTED_PATHS) <= paths


def test_missing_governance_source_negative_control(monkeypatch):
    sources = [s for s in cb.load_sources() if s["path"] != "docs/context/DECISION_CHANGE.md"]
    monkeypatch.setattr(cb, "load_sources", lambda: sources)
    errors = check_context.check_sources()
    assert any("DECISION_CHANGE.md" in error and "source" in error for error in errors)


def test_brief_keeps_decision_intent_and_draft_maturity_distinct():
    brief = cb.build_brief(commit="test")
    accepted = brief.split("## Active accepted decisions", 1)[1].split("## Current milestone", 1)[0]
    assert "owner-directed design intent; implementation draft under review" in accepted
