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


# --- second audit round: typed quantity comparison --------------------------
# The first round fixed individual examples; these close the classes behind them.

def test_currencies_are_distinct_units():
    """USD 7 million and INR 7 million are not the same sum. Collapsing every
    currency into one "currency" bucket made them compare equal."""
    assert numeric_consistency("Saved USD 7 million", "Saved INR 7 million.") is False
    assert numeric_consistency("Saved USD 7 million", "Saved USD 7 million.") is True


def test_thousands_separators_are_not_truncated():
    """"Rs 2,500 crore" matched only the leading "2", so 2,500 and 2,900 both
    parsed as the value 2 and compared equal."""
    tok = extract_numeric_tokens("saved Rs 2,500 crore")[0]
    assert tok.value == 2500
    assert numeric_consistency("saved Rs 2,500 crore",
                               "The programme saved Rs 2,900 crore.") is False


def test_equivalent_scales_still_match():
    assert numeric_consistency("a mandate worth INR 2 crore",
                               "The mandate was worth Rs 200 lakh.") is True


def test_credential_identifiers_must_match_exactly():
    """Recognising an ISO claim as factual does not check WHICH standard."""
    assert numeric_consistency("VCG is ISO 27001 certified",
                               "VCG is ISO 9001 certified.") is False
    assert numeric_consistency("VCG is ISO 27001 certified",
                               "VCG is ISO 27001 certified.") is True
    assert numeric_consistency("holds a SOC 2 attestation",
                               "holds a SOC 1 attestation.") is False


def test_bare_counts_are_compared():
    """A headcount produced no token at all, so the rule reported "not
    applicable" and 240 passed against evidence of 24."""
    assert numeric_consistency("Employs 240 consultants",
                               "The firm employs 24 consultants.") is False
    assert numeric_consistency("Employs 240 consultants",
                               "The firm employs 240 consultants.") is True


def test_direction_matches_whole_words_only():
    """"supplier" and "group" contain "up". Substring matching saw both
    directions, returned "unknown", and skipped the check."""
    assert numeric_consistency("Reduced supplier costs by 23 percent",
                               "Increased supplier costs by 23 percent.") is False
    assert numeric_consistency("Reduced group overheads by 23 percent",
                               "Increased group overheads by 23 percent.") is False


def test_a_specific_unit_does_not_also_emit_a_bare_count():
    """Overlapping patterns would make "18 percent" yield a percent token and a
    bare count for the same digits, and the count would look unmatched."""
    toks = extract_numeric_tokens("reduced turnaround by 18 percent")
    assert [t.canonical_unit() for t in toks] == ["percent"]


def test_a_price_inserted_in_another_section_invalidates_sign_off():
    """The digest covered only commercially-titled sections, so a fee written
    into the Executive Summary escaped it entirely."""
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      persist=False)
    record_decision(st, "BID", "lead", "proceed")
    st = continue_approved_pipeline(st, persist=False)
    review.approve_price(st, "partner", "quote-001", "checked")
    assert review.commercial_approval_current(st)

    review.apply_human_edit(st, "Executive Summary",
                            "Our fee for this engagement is Rs 2 crore.")
    assert not review.commercial_approval_current(st)


def test_a_stale_sign_off_can_be_given_again():
    """The interface hid the approval control whenever a record existed, so a
    reviewer could not re-approve after an edit and release stayed blocked with
    no way forward."""
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      persist=False)
    record_decision(st, "BID", "lead", "proceed")
    st = continue_approved_pipeline(st, persist=False)
    review.approve_price(st, "partner", "quote-001", "checked")
    review.apply_human_edit(st, "Commercial", "**Fee: 2 Cr** - revised terms.")
    assert not review.commercial_approval_current(st)

    review.approve_price(st, "partner", "quote-002", "re-checked after revision")
    assert review.commercial_approval_current(st)


# --- evidence pool must not smuggle unranked passages to the drafter --------
def test_every_passage_offered_to_the_drafter_cleared_the_ranker():
    """The pool promoted each selected document's metric-bearing chunk straight
    from the index, marked it selected, and gave it a relevance score borrowed
    from a DIFFERENT chunk. "Cites only selected evidence" then held at document
    level but not at passage level."""
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      persist=False)
    record_decision(st, "BID", "lead", "proceed")
    st = continue_approved_pipeline(st, persist=False)

    for ev in st["selected_evidence"]["__pool__"]:
        assert ev.relevance_score >= config.SELECT_THRESHOLD, (
            f"{ev.evidence_id} reached the drafter with score "
            f"{ev.relevance_score:.3f}, below the selection threshold")
        assert ev.reasoning, f"{ev.evidence_id} carries no selection rationale"


def test_a_cited_passage_is_always_one_the_ranker_selected():
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      persist=False)
    record_decision(st, "BID", "lead", "proceed")
    st = continue_approved_pipeline(st, persist=False)

    ranked = {e.chunk_id for evs in st["selected_evidence"].values() for e in evs}
    for row in st["overall_traceability"]:
        if row.matched_evidence_id:
            tail = row.matched_evidence_id.split("::", 1)[-1].replace("POOL::", "")
            assert tail in ranked or any(tail in c for c in ranked), (
                f"claim cites {row.matched_evidence_id}, which the ranker never selected")


# --- unrecognised factual assertions must not be exempt from checking -------
@pytest.mark.parametrize("sentence", [
    "VCG owns proprietary clinical diagnostic software.",
    "VCG pioneered the operating-model approach used across the sector.",
    "Our platform integrates directly with every major core banking system.",
    "VCG was founded by former regulators.",
])
def test_any_assertion_about_the_firm_is_checked(sentence):
    """Verification keyed off an allow-list of achievement verbs, so an
    assertion phrased outside it was EXEMPTED rather than flagged as
    unsupported. Adding more verbs does not close that; the default has to be
    to check."""
    claims = decompose_claims("Relevant Experience & Credentials", sentence)
    assert claims and all(c["requires_verification"] for c in claims), sentence


@pytest.mark.parametrize("sentence", [
    "We have read the RFP in full and our understanding is reflected below.",
    "We propose a phased engagement reaching a measured pilot.",
    "In weeks 4 to 7 we will redesign the workflow and operating model.",
])
def test_prospective_and_framing_sentences_stay_exempt(sentence):
    """Inverting the default must not turn the proposal's own scaffolding into
    unsupported claims."""
    claims = decompose_claims("Proposed Approach & Workplan", sentence)
    assert not any(c["requires_verification"] for c in claims), sentence


def test_an_unsupported_assertion_blocks_release():
    """End to end: an invented credential inserted by amendment must stop the
    export gate, not slip through as unverifiable."""
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      persist=False)
    record_decision(st, "BID", "lead", "proceed")
    st = continue_approved_pipeline(st, persist=False)
    review.apply_human_edit(
        st, "Relevant Experience & Credentials",
        "VCG owns proprietary clinical diagnostic software.")
    assert any(r.verification_status == VerificationStatus.GAP
               and "proprietary clinical" in r.claim_text
               for r in st["overall_traceability"])
