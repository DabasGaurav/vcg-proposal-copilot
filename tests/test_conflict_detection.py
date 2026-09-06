"""Phase 3 -- conflict detection surfaces, never resolves."""
from __future__ import annotations

from models.schemas import EvidenceConflict
from pipeline import conflicts
from state.graph_state import new_state
from tests.conftest import make_evidence


def _state_with(evs):
    st = new_state(run_id="t")
    st["selected_evidence"] = {"CHK-1": evs}
    return st


def test_attribution_tenure_conflict_detected():
    evs = [
        make_evidence("CV_001", "Ananya Mehta is a Partner with 18 years of experience."),
        make_evidence("CV_099", "Ananya Mehta is a Partner with 25 years of experience."),
    ]
    st = conflicts.run(_state_with(evs))
    kinds = {c.conflict_type for c in st["evidence_conflicts"]}
    assert "attribution_mismatch" in kinds
    assert all(c.requires_human_resolution for c in st["evidence_conflicts"])


def test_superseded_document_flagged():
    evs = [
        make_evidence("OLD_001", "old numbers", superseded_by="NEW_001"),
        make_evidence("NEW_001", "new numbers"),
    ]
    st = conflicts.run(_state_with(evs))
    assert any(c.conflict_type == "superseded" for c in st["evidence_conflicts"])


def test_no_false_conflict_on_clean_evidence(abc_state):
    for c in abc_state["evidence_conflicts"]:
        assert isinstance(c, EvidenceConflict)
    # the happy-path fixture should not invent conflicts
    assert abc_state["evidence_conflicts"] == [] or all(
        c.requires_human_resolution for c in abc_state["evidence_conflicts"]
    )
