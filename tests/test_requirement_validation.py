"""Phase 2 -- extraction, source-span validation, procedural separation, gaps."""
from __future__ import annotations

import config
from models.schemas import RequirementHandling
from pipeline import extraction, intake
from services.llm import split_compound
from services.text import is_locatable
from state.graph_state import new_state


def _run_to_extraction(fixture: str):
    st = new_state(run_id="t", rfp_path=str(config.FIXTURE_DIR / fixture))
    st = intake.run(st)
    return extraction.run(st)


def test_every_valid_requirement_has_a_locatable_source_span():
    st = _run_to_extraction("abc_bank_lending_transformation.md")
    text = st["rfp_raw_text"]
    for req in st["rfp_data"].requirements:
        assert req.valid
        assert is_locatable(req.source_span.quote, text), req.requirement_id


def test_ungrounded_requirement_is_flagged_not_passed_downstream():
    st = _run_to_extraction("abc_bank_lending_transformation.md")
    # inject a fabricated span and re-validate
    from models.schemas import SourceSpan
    from pipeline.extraction import _to_requirement
    bad = _to_requirement(
        {"requirement_id": "REQ-BAD", "text": "invented", "category": "CONTENT",
         "handling": "NEEDS_EVIDENCE", "mandatory": False,
         "extraction_confidence": 0.9,
         "quote": "VCG guarantees a 90 percent turnaround reduction for every bank",
         "section": "Evaluation Criteria"},
        st["rfp_raw_text"],
    )
    assert bad.valid is False and bad.validation_note


def test_procedural_items_kept_in_their_own_checklist_not_as_content():
    st = _run_to_extraction("pqr_bank_procurement_heavy.md")
    assert len(st["procedural_checklist"]) >= 4
    proc_texts = " ".join(st["procedural_checklist"]).lower()
    assert "arial" in proc_texts and "e-procurement" in proc_texts or "portal" in proc_texts
    # none of the procedural bullets became a NEEDS_EVIDENCE content requirement
    for req in st["rfp_data"].requirements:
        if req.handling == RequirementHandling.NEEDS_EVIDENCE:
            assert "arial" not in req.text.lower()


def test_capability_gap_flagged_for_actuarial_ai():
    st = _run_to_extraction("xyz_insurer_actuarial_ai.md")
    handlings = {r.handling for r in st["rfp_data"].requirements}
    assert RequirementHandling.CAPABILITY_GAP in handlings
    assert any("CAPABILITY GAP" in w for w in st["warnings"])


def test_compound_split_only_on_real_enumerations():
    assert split_compound("Align credit policy and governance with the process") == \
        ["Align credit policy and governance with the process"]
    parts = split_compound(
        "Diagnose the current process; redesign the workflow; define a capacity model"
    )
    assert len(parts) == 3
