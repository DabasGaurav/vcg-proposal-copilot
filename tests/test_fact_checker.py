"""SPEC Section 15 -- the 8 mandatory deterministic-verifier test cases.

Written against the verifier's own functions so they cannot pass by accident if
similarity thresholds shift later.
"""
from __future__ import annotations

import pytest

from models.schemas import EvidenceMatch, VerificationStatus
from pipeline.verification import (
    attribution_consistent,
    context_mismatch,
    decide,
    verify_claim,
)
from tests.conftest import make_claim, make_evidence

CB1 = ("The pilot was measured against a matched baseline. Pilot approval "
       "turnaround time was reduced by 18 percent versus the baseline. "
       "Processing effort per application fell by 22 percent. Manual handoffs "
       "per application dropped by 30 percent.")
DISTRACTOR = ("VCG office sustainability initiative. Electricity use across the "
              "measured sites fell by 35 percent year on year.")
CV1 = "Ananya Mehta is a Partner at VCG with 18 years of experience in banking and lending."
CV2 = "Rohan Sen is a Principal at VCG with 12 years of experience in SME lending."


def _index(*evs):
    idx = {}
    for e in evs:
        idx[e.evidence_id] = e
        idx[e.source_id] = e
    return idx


def test_18pct_supported(semantic_fn):
    claim = make_claim(
        claim_text="VCG reduced pilot approval turnaround time by 18 percent",
        numeric_tokens=["18 percent"], cited_evidence_ids=["CASE_BANK_001"],
        context_qualifiers=["india"],
    )
    ev = make_evidence("CASE_BANK_001", CB1,
                       metadata={"region": "India", "industry": "banking",
                                 "subsector": "retail_lending"})
    res = verify_claim(claim, _index(ev), semantic_fn)
    assert res["status"] == VerificationStatus.SUPPORTED


def test_35pct_vs_cb1_is_gap_numeric(semantic_fn):
    claim = make_claim(
        claim_text="VCG reduced lending TAT by 35 percent",
        numeric_tokens=["35 percent"], cited_evidence_ids=["CASE_BANK_001"],
    )
    ev = make_evidence("CASE_BANK_001", CB1)
    res = verify_claim(claim, _index(ev), semantic_fn)
    assert res["status"] == VerificationStatus.GAP
    assert res["match"].numeric_match is False


def test_35pct_vs_distractor_is_gap_context(semantic_fn):
    claim = make_claim(
        claim_text="VCG reduced lending TAT by 35 percent",
        numeric_tokens=["35 percent"], cited_evidence_ids=["DISTRACTOR_001"],
    )
    ev = make_evidence("DISTRACTOR_001", DISTRACTOR)
    res = verify_claim(claim, _index(ev), semantic_fn)
    assert res["status"] == VerificationStatus.GAP
    assert res["match"].numeric_match is False   # right number, wrong context


def test_attribution_mismatch_is_gap(semantic_fn):
    claim = make_claim(
        claim_text="Rohan Sen has 18 years of experience",
        claim_type=make_claim().claim_type, numeric_tokens=["18 years"],
        named_entities=["Rohan Sen"], cited_evidence_ids=["CV_001"],
    )
    ev = make_evidence("CV_001", CV1)
    res = verify_claim(claim, _index(ev), semantic_fn)
    assert res["status"] == VerificationStatus.GAP
    assert res["match"].attribution_valid is False


def test_correct_attribution_supported(semantic_fn):
    claim = make_claim(
        claim_text="Ananya Mehta has 18 years of experience",
        numeric_tokens=["18 years"], named_entities=["Ananya Mehta"],
        cited_evidence_ids=["CV_001"],
    )
    ev = make_evidence("CV_001", CV1, metadata={"region": "India", "industry": "banking"})
    res = verify_claim(claim, _index(ev), semantic_fn)
    assert res["status"] == VerificationStatus.SUPPORTED


def test_orphan_claim_is_gap(semantic_fn):
    claim = make_claim(claim_text="VCG reduced TAT by 40 percent",
                       numeric_tokens=["40 percent"], cited_evidence_ids=[])
    res = verify_claim(claim, {}, semantic_fn)
    assert res["status"] == VerificationStatus.GAP


def test_geography_mismatch_is_partial_via_context_mismatch():
    """Exercises context_mismatch() directly (SPEC Section 15)."""
    claim = make_claim(
        claim_text="VCG delivered lending improvement for Indian banks",
        claim_type=make_claim().claim_type, numeric_tokens=[],
        context_qualifiers=["indian"], cited_evidence_ids=["CASE_BANK_002"],
    )
    m = EvidenceMatch(
        claim_id=claim.claim_id, evidence_id="E::CASE_BANK_002",
        semantic_similarity=0.9, lexical_overlap=0.9,
        evidence_metadata={"region": "Southeast Asia", "industry": "banking",
                           "subsector": "sme_lending"},
    )
    assert context_mismatch(claim, m) is True
    assert decide(claim, m) == VerificationStatus.PARTIAL


def test_prospective_claim_is_forward_looking(semantic_fn):
    claim = make_claim(
        claim_text="During weeks 1 to 2 the team will map the process",
        requires_verification=False,
    )
    res = verify_claim(claim, {}, semantic_fn)
    assert res["status"] == VerificationStatus.FORWARD_LOOKING


def test_numeric_contradiction_never_overridden_by_similarity():
    claim = make_claim(claim_text="35 percent", numeric_tokens=["35 percent"],
                       cited_evidence_ids=["X"])
    m = EvidenceMatch(claim_id=claim.claim_id, evidence_id="E::X",
                      semantic_similarity=0.99, lexical_overlap=0.99,
                      numeric_match=False)
    assert decide(claim, m) == VerificationStatus.GAP


def test_attribution_default_true_when_no_entity():
    claim = make_claim(claim_text="turnaround fell 18 percent", numeric_tokens=["18 percent"])
    assert attribution_consistent(claim, "unrelated text") is True
