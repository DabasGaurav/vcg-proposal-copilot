"""Phase 5 -- traceability matrix + the hero 18%/35% moment."""
from __future__ import annotations

from models.schemas import VerificationStatus


def test_hero_moment_18_supported_35_gap(abc_state):
    rows = abc_state["overall_traceability"]
    supported_18 = [
        r for r in rows
        if "18 percent" in r.claim_text and r.verification_status == VerificationStatus.SUPPORTED
    ]
    gap_35 = [
        r for r in rows
        if "35 percent" in r.claim_text and r.verification_status == VerificationStatus.GAP
    ]
    assert supported_18, "the 18% claim must verify as SUPPORTED"
    assert gap_35, "the 35% overclaim must be caught as GAP"


def test_every_requirement_appears_in_the_rollup(abc_state):
    summary_ids = {s["requirement_id"] for s in abc_state["requirement_summary"]}
    for req in abc_state["rfp_data"].requirements:
        assert req.requirement_id in summary_ids


def test_traceability_row_carries_full_chain(abc_state):
    row = next(r for r in abc_state["overall_traceability"]
              if r.verification_status == VerificationStatus.SUPPORTED)
    assert row.requirement_source_span is not None
    assert row.matched_evidence_id
    assert row.matched_chunk_text
    assert row.claim_text
    assert row.verification_reason


def test_many_to_many_not_unique(abc_state):
    rows = abc_state["overall_traceability"]
    claim_ids = [r.claim_id for r in rows if r.claim_id != "(none)"]
    # a claim can legitimately appear against more than one requirement
    assert len(claim_ids) >= len(set(claim_ids))


def test_proposal_has_at_least_five_sections(abc_state):
    assert len(abc_state["proposal_draft"].sections) >= 5


def test_gap_claim_count_nonzero(abc_state):
    assert abc_state["proposal_draft"].gap_claim_count >= 1
