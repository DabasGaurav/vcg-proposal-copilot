"""Findings from the five-new-RFP test: the verifier was sound and nothing
upstream listened to it.

Qualification scored bid fit as the share of requirements for which retrieval
returned *anything*, and the drafter asserted delivery experience from whatever
ranked first. So the stage that decides whether to spend money bidding, and the
stage that writes the prose, both disagreed with the verifier that ran after them.
"""
from __future__ import annotations

import pytest

import config
from models.schemas import AtomicClaim, EvidenceItem, VerificationStatus
from pipeline.graph import continue_approved_pipeline, run_pipeline
from pipeline.qualification import record_decision
from pipeline.verification import verify_claim
from services.mock_llm import decompose_claims
from services.substantiation import (
    asks_for_delivery_evidence,
    requirement_threshold,
    substantiation_gap,
)
from services.text import GEO_GROUPS, extract_context_qualifiers
from services.vectorstore import VectorStore


def _qualify(fixture: str) -> dict:
    config.ensure_dirs()
    VectorStore.ensure_seeded()
    state = run_pipeline(str(config.FIXTURE_DIR / fixture),
                         run_id=f"t-{fixture[:10]}", persist=False)
    return state["qualification"]


def _drafted(fixture: str):
    config.ensure_dirs()
    VectorStore.ensure_seeded()
    state = run_pipeline(str(config.FIXTURE_DIR / fixture),
                         run_id=f"d-{fixture[:10]}", persist=False)
    record_decision(state, "BID", "test", "forced through to inspect drafting")
    return continue_approved_pipeline(state, persist=False)


# --------------------------------------------------------------------------- #
# Finding 1 -- bid fit scored retrieval, not substantiation
# --------------------------------------------------------------------------- #
def test_unmeetable_thresholds_cannot_score_a_bid():
    """Scored 100/100 and BID_REVIEW while demanding 45/50/60 percent against a
    corpus recording 18/22/30 -- figures the same pipeline then contradicted."""
    q = _qualify("apex_aggressive_thresholds.md")
    assert q["score"] == 0
    assert q["recommendation"] != "BID_REVIEW"
    gaps = " ".join(q["substantiation_gaps"].values())
    for bar in ("45", "50", "60"):
        assert bar in gaps


def test_a_mandatory_requirement_is_not_covered_by_the_wrong_kind_of_document():
    """METHOD_002 says in its own text that it must not be cited as evidence of a
    delivered engagement. It was satisfying a MANDATORY delivery requirement."""
    q = _qualify("helvetia_core_platform_delivery.md")
    assert q["score"] == 0
    assert q["recommendation"] == "NO_BID_REVIEW"
    assert q["mandatory_gap_ids"], "the unmet mandatory requirement was not raised"
    assert any("not a case study" in why
               for why in q["substantiation_gaps"].values())


def test_the_gate_still_says_bid_when_the_evidence_really_clears_the_bar():
    """The anti-regression half: a gate that can only ever say no is useless.

    Same corpus, same pipeline -- a tender asking for more than 15 percent
    turnaround (the record is 18) and more than 20 percent handoffs (the record
    is 30) must qualify.
    """
    q = _qualify("control_satisfiable_lending.md")
    assert q["score"] == 100
    assert q["recommendation"] == "BID_REVIEW"
    assert not q["mandatory_gap_ids"]
    assert not q["substantiation_gaps"]


def test_substantiation_gap_names_its_reason():
    case = EvidenceItem(
        evidence_id="C::00", source_id="CASE", chunk_id="C::00", title="Case",
        chunk_text="Pilot approval turnaround time was reduced by 18 percent.",
        category="CASE_STUDY", metadata={}, source_path="d",
        relevance_score=0.9, selected=True)
    method = EvidenceItem(
        evidence_id="M::00", source_id="METHOD", chunk_id="M::00", title="Framework",
        chunk_text="A structured framework for assessing platform health.",
        category="METHODOLOGY", metadata={}, source_path="d",
        relevance_score=0.9, selected=True)

    assert substantiation_gap("Demonstrated experience redesigning lending "
                              "operations for a bank.", [case]) is None
    assert substantiation_gap("Anything at all.", []) == "no evidence was selected"
    assert "not a case study" in substantiation_gap(
        "Demonstrated prior experience delivering a core banking replacement.",
        [method])
    assert "at least 45" in substantiation_gap(
        "Evidence of at least 45 percent turnaround-time improvement.", [case])
    assert substantiation_gap(
        "Evidence of at least 15 percent turnaround-time improvement.", [case]) is None


# --------------------------------------------------------------------------- #
# Finding 2 -- a methodology document assertable as delivery experience
# --------------------------------------------------------------------------- #
def test_no_delivery_experience_claim_may_cite_a_non_case_study():
    state = _drafted("helvetia_core_platform_delivery.md")
    results = state["_verification_results"]
    index = {}
    for evs in state["selected_evidence"].values():
        for ev in evs:
            for key in (ev.evidence_id, ev.source_id, ev.chunk_id):
                index[key] = ev

    for claim in state["atomic_claims"]:
        if results[claim.claim_id]["status"] != VerificationStatus.SUPPORTED:
            continue
        if "delivery experience" not in claim.claim_text.lower():
            continue
        for cid in claim.cited_evidence_ids:
            ev = index.get(cid)
            if ev is not None:
                assert str(getattr(ev.category, "value", ev.category)) == "CASE_STUDY", \
                    (claim.claim_text, ev.source_id, ev.category)


def test_the_experience_section_says_why_a_methodology_is_not_a_record():
    state = _drafted("helvetia_core_platform_delivery.md")
    body = "\n".join(s.content_markdown for s in state["proposal_draft"].sections
                     if "Experience" in s.title)
    assert "EVIDENCE GAP" in body
    assert "not a delivery record" in body
    assert "VCG has relevant delivery experience" not in body


def test_delivery_wording_is_detected_but_forward_scope_is_not():
    assert asks_for_delivery_evidence("Demonstrated prior experience delivering X.")
    assert asks_for_delivery_evidence("Evidence of a delivered, stabilised platform.")
    assert not asks_for_delivery_evidence("The engagement must be delivered within 12 weeks.")


# --------------------------------------------------------------------------- #
# Finding 3 -- Rule E's geography check covered ten strings
# --------------------------------------------------------------------------- #
INDIA = EvidenceItem(
    evidence_id="IN::00", source_id="CASE_BANK_001", chunk_id="IN::00",
    title="Retail Lending Transformation", category="CASE_STUDY",
    chunk_text="Pilot approval turnaround time was reduced by 18 percent versus the baseline.",
    metadata={"region": "India", "industry": "banking", "subsector": "retail_lending"},
    source_path="d", relevance_score=0.9, selected=True)


@pytest.mark.parametrize("region", ["Middle East", "Europe", "Southeast Asia",
                                    "Africa", "Latin America", "China", "Australia"])
def test_a_false_geography_cannot_reach_supported(region):
    """Identical claims against the same Indian case study came out differently:
    Europe was caught, Middle East was returned SUPPORTED, because the extractor
    and the contradiction check were two lists that disagreed."""
    sem = VectorStore.load().semantic_similarity
    sentence = (f"In a comparable {region} engagement, VCG reduced turnaround "
                f"time by 18 percent.")
    claim = AtomicClaim(**decompose_claims("Experience",
                                           f"{sentence} [[ev:IN::00]]")[0])
    assert claim.context_qualifiers, f"{region} extracted no qualifier at all"
    result = verify_claim(claim, {"IN::00": INDIA}, sem)
    assert result["status"] != VerificationStatus.SUPPORTED, result["reason"]


def test_the_evidences_own_region_still_passes():
    sem = VectorStore.load().semantic_similarity
    sentence = ("In a comparable India engagement, VCG reduced turnaround time "
                "by 18 percent.")
    claim = AtomicClaim(**decompose_claims("Experience",
                                           f"{sentence} [[ev:IN::00]]")[0])
    assert verify_claim(claim, {"IN::00": INDIA}, sem)["status"] == \
        VerificationStatus.SUPPORTED


def test_extraction_and_contradiction_share_one_vocabulary():
    """Every geography the contradiction check knows must be extractable."""
    for group in GEO_GROUPS:
        for term in group:
            assert extract_context_qualifiers(f"work delivered in {term} last year"), \
                f"{term!r} is in GEO_GROUPS but extracts no qualifier"


# --------------------------------------------------------------------------- #
# Finding 4 -- two number parsers disagreed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("Evidence of at least 45 percent turnaround-time improvement", (45.0, "percent")),
    ("Evidence of more than 60 percent reduction in manual handoffs", (60.0, "percent")),
    ("Evidence of a turnaround-time reduction of more than twenty percent",
     (20.0, "percent")),
    ("Evidence of a forecast accuracy improvement of at least fifteen percentage points",
     (15.0, "percentage_points")),
    ("Evidence of greater than 30 percent turnaround-time improvement", (30.0, "percent")),
])
def test_thresholds_parse_however_they_are_written(text, expected):
    assert requirement_threshold(text) == expected


@pytest.mark.parametrize("text", [
    "Named team members with relevant lending operations experience",
    "The engagement must be delivered within 12 weeks",
    "Proposals must be submitted in English only",
])
def test_non_thresholds_are_not_read_as_thresholds(text):
    assert requirement_threshold(text) is None
