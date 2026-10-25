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


def _decision_series(target, status):
    """Keep numbering valid so a rejection must concern status, not missing IDs."""
    return "\n".join(
        f"## ADR-{number:03d} — Test decision\n**Status:** "
        f"{status if number == target else 'accepted'}\n"
        for number in range(1, target + 1)
    )


@pytest.mark.parametrize("target,valid", [(4, True), (7, False), (10, False)])
def test_legacy_status_requires_exact_adr_identity(target, valid):
    text = _decision_series(target, "accepted research policy")
    if valid:
        adrs = cb.parse_adrs(text)
        assert adrs[-1]["id"] == "ADR-004"
        assert adrs[-1]["status"] == "accepted"
        assert adrs[-1] in cb.active_decisions(adrs)
    else:
        with pytest.raises(ValueError, match=f"ADR-{target:03d}: invalid status"):
            cb.parse_adrs(text)


@pytest.mark.parametrize("status,active", [("accepted", True), ("proposed", False), ("superseded", False)])
@pytest.mark.parametrize("target", [4, 7, 10])
def test_standard_statuses_are_independent_of_legacy_identity(target, status, active):
    adrs = cb.parse_adrs(_decision_series(target, status))
    assert adrs[-1]["status"] == status
    assert (adrs[-1] in cb.active_decisions(adrs)) is active


@pytest.mark.parametrize("status", [
    "accepted_pending_owner_approval", "accepted-pending-owner-approval",
    "accepted pending owner approval", "proposed_pending_owner_approval",
    "superseded_pending_owner_approval", "accepted research policy pending",
    "accept", "acceptedness", "accepted/research policy", "", "· pending approval",
    "\naccepted",
])
def test_malformed_or_pending_statuses_block_even_legacy_adr(status):
    with pytest.raises(ValueError):
        cb.parse_adrs(_decision_series(4, status))


@pytest.mark.parametrize("target", [4, 7, 10])
def test_generator_and_checker_share_identity_scoped_validation(tmp_path, monkeypatch, target):
    decisions = tmp_path / "decisions.md"
    decisions.write_text(_decision_series(target, "accepted research policy"))
    monkeypatch.setattr(cb, "DECISIONS", decisions)
    if target == 4:
        assert check_context.check_adrs() == []
        assert "**ADR-004**" in cb.build_brief(commit="test")
    else:
        with pytest.raises(ValueError, match=f"ADR-{target:03d}: invalid status"):
            cb.build_brief(commit="test")
        assert any(f"ADR-{target:03d}: invalid status" in error
                   for error in check_context.check_adrs())


def test_status_normalization_and_informational_annotation():
    adrs = cb.parse_adrs(_decision_series(4, "  ACCEPTED RESEARCH POLICY  · historical metadata"))
    assert adrs[-1]["status"] == "accepted"
    assert cb.parse_adrs(_decision_series(7, " ACCEPTED · implementation draft under review"))[-1]["status"] == "accepted"
