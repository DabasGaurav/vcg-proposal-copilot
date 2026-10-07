"""Regressions for defects found by an independent audit of commit 7713bda.

Each test here corresponds to a verification bypass that was confirmed by
reproduction before being fixed. The first is the most serious: it falsified the
product's central claim that a contradicted figure cannot pass.
"""
from __future__ import annotations

import pytest

import config
from models.schemas import ReviewDecision, VerificationStatus
from pipeline import review
from pipeline.graph import continue_approved_pipeline, run_pipeline
from pipeline.qualification import record_decision
from pipeline.verification import numeric_consistency, verify_claim
from services.llm import bullets
from services.mock_llm import decompose_claims
from services.text import extract_numeric_tokens
from tests.conftest import make_claim, make_evidence

CB1 = "Pilot approval turnaround time was reduced by 18 percent versus the baseline."


# --- 1. a figure written with the % SYMBOL bypassed the numeric rule entirely --
def test_percent_symbol_is_tokenised():
    """A trailing \\b after the alternation dropped every symbol-written figure,
    so "35%" produced no numeric token and the rule reported "not applicable"."""
    assert [t.raw for t in extract_numeric_tokens("reduced TAT by 35%")] == ["35%"]
    assert [t.raw for t in extract_numeric_tokens("a 35%.")] == ["35%"]


def test_contradicted_figure_written_with_a_symbol_is_caught():
    assert numeric_consistency("VCG reduced turnaround time by 35%", CB1) is False
    assert numeric_consistency("VCG reduced turnaround time by 18%", CB1) is True


def test_symbol_written_overclaim_cannot_verify(semantic_fn):
    claim = make_claim(claim_text="VCG reduced pilot approval turnaround time by 35%",
                       numeric_tokens=["35%"], cited_evidence_ids=["CASE_BANK_001"])
    ev = make_evidence("CASE_BANK_001", CB1)
    res = verify_claim(claim, {"CASE_BANK_001": ev, ev.evidence_id: ev}, semantic_fn)
    assert res["status"] == VerificationStatus.GAP


# --- 2. currency scale was ignored: 5 crore compared equal to 5 lakh ----------
def test_currency_scale_is_compared():
    assert numeric_consistency("a mandate worth Rs 5 crore",
                               "The mandate was worth Rs 5 lakh in fees.") is False
    assert numeric_consistency("a mandate worth Rs 5 crore",
                               "The mandate was worth Rs 5 crore in fees.") is True


def test_scale_words_are_normalised():
    tok = extract_numeric_tokens("worth Rs 5 crore")[0]
    assert tok.value == 5 and tok.scaled_value == 5e7


# --- 3. direction was never checked: "reduced" matched "increased" -----------
def test_opposite_direction_is_not_corroboration():
    assert numeric_consistency(
        "VCG reduced turnaround time by 18 percent",
        "Turnaround time increased by 18 percent versus the baseline.") is False


def test_same_direction_still_matches():
    assert numeric_consistency("VCG cut turnaround time by 18 percent", CB1) is True


# --- 4. credential assertions escaped verification altogether ----------------
@pytest.mark.parametrize("sentence", [
    "VCG is ISO 27001 certified.",
    "VCG holds a SOC 2 Type II attestation.",
    "VCG operates in 40 countries.",
])
def test_firm_credential_claims_require_verification(sentence):
    claims = decompose_claims("Relevant Experience & Credentials", sentence)
    assert claims and all(c["requires_verification"] for c in claims), sentence


def test_framing_sentences_still_do_not_require_verification():
    claims = decompose_claims(
        "Context & Problem Understanding",
        "We have read the RFP in full and our understanding is reflected below.")
    assert not any(c["requires_verification"] for c in claims)


# --- 5. numbered and lettered tender lists extracted nothing -----------------
def test_numbered_and_lettered_lists_are_extracted():
    assert bullets("1. Demonstrated experience.\n2. Evidence of improvement.\n") == [
        "Demonstrated experience.", "Evidence of improvement."]
    assert bullets("a) Signed declaration.\nb) Two references.\n") == [
        "Signed declaration.", "Two references."]
    assert bullets("- Demonstrated experience.\n") == ["Demonstrated experience."]


# --- 6. commercial sign-off survived an edit to the commercial text ----------
def test_commercial_approval_is_invalidated_by_a_later_edit():
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      persist=False)
    record_decision(st, "BID", "lead", "proceed")
    st = continue_approved_pipeline(st, persist=False)
    for sec in st["proposal_draft"].sections:
        review.submit_section_decision(st, sec.section_id, "p", ReviewDecision.APPROVED)
    for g in review.unresolved_gaps(st):
        review.override_gap(st, g.trace_id, "withdrawing unsupported claim")
    review.approve_price(st, "partner", "quote-001", "checked")
    assert review.can_export(st)[0]

    review.apply_human_edit(st, "Commercial", "**Fee: 2 Cr** - materially different.")
    ok, reasons = review.can_export(st)
    assert not ok
    assert any("changed after partner sign-off" in r for r in reasons)
