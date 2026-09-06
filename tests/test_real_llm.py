"""Real-provider (LiteLLM) path -- exercised with a stubbed transport so it runs
offline. Proves the prompt plumbing + parsing + the citation-tag convention that
the deterministic verifier depends on."""
from __future__ import annotations

import json

import pytest

from services import real_llm
from services.llm import LLM

RFP = """# RFP

## Client
ABC Bank, a retail bank in India.

## Evaluation Criteria
- Demonstrated experience redesigning retail lending operations for a bank.
- Evidence of greater than 30 percent turnaround-time improvement.

## Procedural Requirements
- Proposals must be submitted in English only.
"""

EXTRACT_JSON = json.dumps({
    "client": "ABC Bank, a retail bank in India.",
    "problem_statement": "slow approvals", "timeline": "12 weeks",
    "scope_items": [], "deliverables": [], "evaluation_criteria": [
        "Demonstrated experience redesigning retail lending operations for a bank."],
    "requirements": [
        {"text": "Demonstrated experience redesigning retail lending operations for a bank.",
         "category": "CONTENT", "handling": "NEEDS_EVIDENCE", "mandatory": True,
         "extraction_confidence": 0.9,
         "quote": "Demonstrated experience redesigning retail lending operations for a bank.",
         "section": "Relevant Experience & Credentials"},
    ],
    "procedural_checklist": ["Proposals must be submitted in English only."],
    "warnings": [],
})


def test_extract_parses_and_ids_requirements():
    data = real_llm.extract_requirements(RFP, complete=lambda s, u: EXTRACT_JSON)
    assert data["client"].startswith("ABC Bank")
    assert data["requirements"][0]["requirement_id"] == "REQ-001"
    assert data["procedural_checklist"]


def test_extract_rejects_non_json():
    with pytest.raises(RuntimeError):
        real_llm.extract_requirements(RFP, complete=lambda s, u: "sorry, I cannot")


def test_decompose_preserves_tags_and_runs_deterministic_extraction():
    md = ("In a redesign for a large Indian bank, VCG reduced turnaround time by "
          "18 percent. [[ev:CHK-014::CASE_BANK_001::02.00]][[req:CHK-014]]\n\n"
          "We propose a phased approach.")
    atoms = json.dumps([
        "In a redesign for a large Indian bank, VCG reduced turnaround time by 18 percent. "
        "[[ev:CHK-014::CASE_BANK_001::02.00]][[req:CHK-014]]",
        "We propose a phased approach.",
    ])
    claims = real_llm.decompose_claims("Relevant Experience & Credentials", md,
                                       complete=lambda s, u: atoms)
    hist = [c for c in claims if c["requires_verification"]]
    assert hist and hist[0]["cited_evidence_ids"] == ["CHK-014::CASE_BANK_001::02.00"]
    assert hist[0]["source_checklist_id"] == "CHK-014"
    assert "18 percent" in hist[0]["numeric_tokens"]
    assert any(c["claim_type"] == "PROPOSED_ACTION" for c in claims)  # the prospective one


def test_decompose_falls_back_when_model_output_unusable():
    md = "VCG reduced turnaround time by 18 percent. [[ev:X]][[req:CHK-1]]"
    claims = real_llm.decompose_claims("Executive Summary", md,
                                       complete=lambda s, u: "not json at all")
    assert claims and "18 percent" in claims[0]["numeric_tokens"]


def test_full_pipeline_runs_on_stubbed_litellm(monkeypatch, tmp_path):
    """LLM_PROVIDER=litellm end to end, transport stubbed -- the hero GAP must
    still be caught deterministically."""
    import config
    from pipeline.graph import run_pipeline

    def fake_complete(self, system, user):
        if "extract structured requirements" in system:
            return EXTRACT_JSON
        if "proposal plan" in system:
            return json.dumps({
                "checklist": [{"requirement_id": "REQ-001",
                               "evidence_need": "evidence of lending redesign",
                               "target_section": "Relevant Experience & Credentials"}],
                "human_input_requirements": [],
            })
        if "draft ONE section" in system:
            if "Relevant Experience" in user:
                return ("VCG reduced lending turnaround time by 35 percent. [[req:CHK-001]]")
            return "We propose a phased approach that reaches a measured pilot."
        if "Split the given proposal section" in system:
            # echo each line as an atom
            return json.dumps([l for l in user.splitlines() if l.strip()])
        return "{}"

    monkeypatch.setattr(LLM, "complete", fake_complete)
    monkeypatch.setattr(config, "LLM_PROVIDER", "litellm")

    rfp = tmp_path / "r.md"
    rfp.write_text(RFP)
    st = run_pipeline(str(rfp), persist=False)
    from models.schemas import VerificationStatus
    assert any(r.verification_status == VerificationStatus.GAP
               and "35 percent" in r.claim_text
               for r in st["overall_traceability"])
