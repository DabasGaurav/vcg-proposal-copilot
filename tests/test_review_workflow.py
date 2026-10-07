"""Phase 6 -- section approval, edit preservation, export gate."""
from __future__ import annotations

import pytest

from models.schemas import ReviewDecision
from pipeline import export, qualification, review


def _approve_all(state):
    for s in state["proposal_draft"].sections:
        review.submit_section_decision(state, s.section_id, "partner",
                                       ReviewDecision.APPROVED)


def test_no_export_before_every_section_approved(abc_state):
    ok, reasons = review.can_export(abc_state)
    assert not ok
    with pytest.raises(export.ExportBlocked):
        export.render_markdown(abc_state, enforce=True)


def test_gap_blocks_export_until_overridden_with_reason(abc_state):
    qualification.record_decision(abc_state, "BID", "practice lead", "Pursue with review of gaps")
    review.approve_price(abc_state, "partner", "rate-card-2026", "Commercial response approved")
    _approve_all(abc_state)
    ok, reasons = review.can_export(abc_state)
    assert not ok  # unresolved GAP rows remain
    for row in review.unresolved_gaps(abc_state):
        review.override_gap(abc_state, row.trace_id, "no comparable >30% engagement; will not claim")
    ok, reasons = review.can_export(abc_state)
    assert ok, reasons
    md = export.render_markdown(abc_state, enforce=True)
    assert "## Executive Summary" in md


def test_override_requires_a_reason(abc_state):
    with pytest.raises(ValueError):
        review.override_gap(abc_state, "TRC-x", "")


def test_commercial_signoff_is_separate_from_section_approval(abc_state):
    qualification.record_decision(abc_state, "BID", "practice lead", "Pursue")
    _approve_all(abc_state)
    for row in review.unresolved_gaps(abc_state):
        review.override_gap(abc_state, row.trace_id, "Withdraw unsupported claim")
    ok, reasons = review.can_export(abc_state)
    assert not ok and any("commercial response" in reason for reason in reasons)
    review.approve_price(abc_state, "partner", "quote-001", "Price checked")
    assert review.can_export(abc_state)[0]


def test_human_edit_survives_regeneration_of_other_section(abc_state):
    marker = "EDITED BY PARTNER — bespoke context paragraph."
    review.apply_human_edit(abc_state, "Context & Problem Understanding", marker)
    review.regenerate_section(abc_state, "Risks & Mitigations")
    ctx = next(s for s in abc_state["proposal_draft"].sections
               if s.title == "Context & Problem Understanding")
    assert ctx.human_edited and marker in ctx.content_markdown
    assert abc_state["draft_sections"]["Context & Problem Understanding"] == marker


def test_regenerating_the_edited_section_discards_its_edit(abc_state):
    review.apply_human_edit(abc_state, "Risks & Mitigations", "temp edit")
    review.regenerate_section(abc_state, "Risks & Mitigations")
    assert abc_state["draft_sections"]["Risks & Mitigations"] != "temp edit"


def test_system_never_sends_anything_externally():
    import pipeline.export as ex
    src = (ex.__file__)
    text = open(src).read()
    for banned in ("requests.post", "smtplib", "urllib.request.urlopen", "httpx"):
        assert banned not in text


def test_price_signoff_requires_a_bid_decision_first(abc_state):
    """Qualification gates the whole pipeline, commercial sign-off included."""
    from pipeline.graph import run_pipeline

    import config
    from pipeline import review

    unqualified = run_pipeline(
        str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
        run_id="test-no-bid", persist=False,
    )
    assert not (unqualified.get("practice_lead_decision") or {}).get("decision")
    with pytest.raises(PermissionError):
        review.approve_price(unqualified, "Partner", "REF-1", "looks fine")


@pytest.mark.parametrize("reviewer,reference,note", [
    ("", "REF-1", "reviewed"),
    ("   ", "REF-1", "reviewed"),
    ("Partner", "", "reviewed"),
    ("Partner", "REF-1", ""),
])
def test_price_signoff_rejects_blank_attribution(abc_state, reviewer, reference, note):
    """An unattributed sign-off is not a sign-off."""
    from pipeline import review

    with pytest.raises(ValueError):
        review.approve_price(abc_state, reviewer, reference, note)
