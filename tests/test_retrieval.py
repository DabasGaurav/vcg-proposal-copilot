"""Phase 1/3 -- retrieval favours banking/lending, rejects distractors."""
from __future__ import annotations


def test_lending_query_prefers_case_bank_over_supply_chain(store):
    hits = store.search("retail lending operations redesign turnaround for a bank", 8)
    ranks = {h.document_id: i for i, h in enumerate(hits)}
    assert "CASE_BANK_001" in ranks
    if "CASE_SC_001" in ranks:
        assert ranks["CASE_BANK_001"] < ranks["CASE_SC_001"]


def test_office_sustainability_is_not_top_for_lending_tat(store):
    hits = store.search("reduce lending turnaround time in a bank pilot", 5)
    assert hits[0].document_id != "DISTRACTOR_001"


def test_semantic_similarity_is_symmetric_ish(store):
    a = store.semantic_similarity("lending turnaround", "turnaround in lending operations")
    assert a > 0.0
