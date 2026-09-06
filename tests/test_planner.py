"""Phase 2 -- response planner."""
from __future__ import annotations

import config
from pipeline import extraction, intake, planning
from state.graph_state import new_state


def _plan(fixture: str):
    st = new_state(run_id="t", rfp_path=str(config.FIXTURE_DIR / fixture))
    for fn in (intake.run, extraction.run, planning.run):
        st = fn(st)
    return st


def test_plan_produces_checklist_outline_and_human_inputs():
    st = _plan("abc_bank_lending_transformation.md")
    assert len(st["checklist"]) >= 5
    assert "Executive Summary" in st["proposal_outline"]
    assert st["proposal_outline"][-1] == "Executive Summary"  # synthesised last
    assert st["human_input_requirements"]  # named team / commercial


def test_procedural_only_items_do_not_enter_evidence_checklist():
    st = _plan("pqr_bank_procurement_heavy.md")
    for item in st["checklist"]:
        assert "arial" not in item.requirement_text.lower()
