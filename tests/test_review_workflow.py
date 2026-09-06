"""Phase 6 -- section approval, edit preservation, export gate."""
from __future__ import annotations

import pytest

from models.schemas import ReviewDecision
from pipeline import export, review


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
