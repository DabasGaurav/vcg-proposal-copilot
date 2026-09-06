"""Phase 3 -- ranking selects with reasons, rejects with reasons, marks gaps."""
from __future__ import annotations


def test_selected_and_rejected_evidence_both_carry_reasons(abc_state):
    sel = abc_state["selected_evidence"]
    rej = abc_state["rejected_evidence"]
    assert any(evs for cid, evs in sel.items() if cid != "__pool__")
    for evs in sel.values():
        for e in evs:
            assert e.reasoning
    total_rej = 0
    for evs in rej.values():
        for e in evs:
            assert e.rejection_reason
            total_rej += 1
    assert total_rej > 0


def test_supply_chain_and_sustainability_distractors_are_rejected(abc_state):
    picked = {
        e.source_id
        for cid, evs in abc_state["selected_evidence"].items() if cid != "__pool__"
        for e in evs
    }
    assert "DISTRACTOR_001" not in picked          # office electricity 35%
    # supply-chain case should not be a primary selection for lending items
    assert "CASE_SC_001" not in picked


def test_gap_when_no_candidate_clears_threshold(abc_state):
    assert isinstance(abc_state["retrieval_gaps"], list)
    # the >30% turnaround criterion cannot be covered by the corpus
    gap_reqs = set(abc_state["retrieval_gaps"])
    assert gap_reqs  # at least one checklist item is an explicit GAP
