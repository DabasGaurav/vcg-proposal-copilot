"""Bid/no-bid must be reviewed before the interactive app drafts."""
from __future__ import annotations

import pytest

from pipeline import qualification
from pipeline.graph import continue_approved_pipeline, run_pipeline


def test_qualification_stops_before_drafting_and_requires_approval():
    import config
    state = run_pipeline(
        str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
        persist=False,
    )
    assert state["qualification"]["evidence_requirements"] >= 1
    assert "proposal_draft" not in state
    with pytest.raises(PermissionError):
        continue_approved_pipeline(state, persist=False)
    qualification.record_decision(state, "BID", "practice lead", "Pursue after reviewing gaps")
    continued = continue_approved_pipeline(state, persist=False)
    assert continued["proposal_draft"].sections


def test_no_bid_cannot_draft():
    import config
    state = run_pipeline(
        str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
        persist=False,
    )
    qualification.record_decision(state, "NO_BID", "practice lead", "Evidence gap")
    with pytest.raises(PermissionError):
        continue_approved_pipeline(state, persist=False)
