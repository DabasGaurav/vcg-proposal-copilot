"""Bypasses found by adversarial stress testing.

Every case here is a FALSE claim that reached SUPPORTED, or a stale document that
was used in silence. The only outcome this product cannot have is a false claim
presented as substantiated, so each one is pinned.
"""
from __future__ import annotations

import config
from models.schemas import AtomicClaim, EvidenceItem, VerificationStatus
from pipeline import conflicts
from pipeline.verification import numeric_consistency, verify_claim
from services.mock_llm import decompose_claims
from services.text import extract_numeric_tokens, significant_tokens
from services.vectorstore import VectorStore

# The real passage every numeric case is checked against.
TAT = (
    "The pilot was measured against a matched baseline of comparable branches over\n"
    "the preceding two quarters.\n\n"
    "- Pilot approval turnaround time was reduced by 18 percent versus the baseline.\n"
    "- Processing effort per application fell by 22 percent.\n"
    "- Manual handoffs per application dropped by 30 percent, from ten steps to seven.\n"
    "- Credit loss rate in the pilot cohort was unchanged within measurement error.\n"
)


# --------------------------------------------------------------------------- #
# Tokenisation: a sentence-final period rode along on the token, so "percent."
# never matched the generic-near-number set and became the single shared token
# that satisfied the distractor guard on its own.
# --------------------------------------------------------------------------- #
def test_sentence_punctuation_does_not_survive_tokenisation():
    assert significant_tokens("reduced by 18 percent versus the baseline.") == [
        "reduced", "percent", "versus", "baseline"]


def test_decimals_and_hyphenated_compounds_still_tokenise():
    assert "18.2" in significant_tokens("fell 18.2 percent")
    assert set(significant_tokens("a turnaround-time improvement")) >= {
        "turnaround", "time", "improvement"}


def test_a_figure_quoted_from_a_different_metric_is_rejected():
    """The passage reports 18 percent for TURNAROUND, and says the credit loss
    rate was unchanged. A claim of 18 percent about default rates passed because
    "percent." was the one token the two had in common."""
    assert numeric_consistency(
        "VCG reduced loan default rates by 18 percent.", TAT) is False
    assert numeric_consistency(
        "VCG reduced pilot approval turnaround time by 18 percent.", TAT) is True


# --------------------------------------------------------------------------- #
# A figure written in words produced no numeric token at all, so the numeric
# rule reported "not applicable" and the claim was judged on similarity alone.
# --------------------------------------------------------------------------- #
def test_numbers_written_in_words_are_tokenised():
    assert [t.value for t in extract_numeric_tokens("reduced by thirty-five percent")] == [35.0]
    assert [t.value for t in extract_numeric_tokens("reduced by eighteen percent")] == [18.0]
    assert [t.value for t in extract_numeric_tokens("a forty percent gain")] == [40.0]


def test_a_contradicted_figure_written_in_words_is_rejected():
    assert numeric_consistency(
        "VCG reduced turnaround time by thirty-five percent.", TAT) is False


def test_digitising_words_preserves_offsets_for_the_context_rule():
    """The context window and direction checks index into the original string."""
    text = "turnaround time was reduced by thirty-five percent versus baseline"
    tok = extract_numeric_tokens(text)[0]
    assert text[tok.start:tok.end].strip().endswith("percent")


# --------------------------------------------------------------------------- #
# Percentage points are not percent.
# --------------------------------------------------------------------------- #
def test_percentage_points_are_a_distinct_unit():
    pp = extract_numeric_tokens("a gain of 18 percentage points")[0]
    pct = extract_numeric_tokens("a gain of 18 percent")[0]
    assert pp.canonical_unit() == "percentage_points"
    assert pct.canonical_unit() == "percent"
    assert pp.canonical_unit() != pct.canonical_unit()


def test_a_percentage_point_claim_is_not_supported_by_a_percent_result():
    assert numeric_consistency(
        "VCG reduced turnaround time by 18 percentage points.", TAT) is False


# --------------------------------------------------------------------------- #
# A comparative qualifier makes the claim strictly stronger than the evidence.
# --------------------------------------------------------------------------- #
def test_more_than_is_not_established_by_exactly():
    for text in ("VCG reduced turnaround time by more than 18 percent.",
                 "VCG reduced turnaround time by over 18 percent.",
                 "VCG reduced turnaround time by at least 18 percent."):
        assert numeric_consistency(text, TAT) is False, text


def test_an_unqualified_claim_against_bounded_evidence_is_fine():
    ev = "Turnaround time was reduced by at least 18 percent versus the baseline."
    assert numeric_consistency(
        "VCG reduced turnaround time by 18 percent.", ev) is True


# --------------------------------------------------------------------------- #
# One passage cannot establish a property of every engagement.
# --------------------------------------------------------------------------- #
def _claim(sentence: str, evidence_id: str) -> AtomicClaim:
    raw = decompose_claims("Relevant Experience & Credentials",
                           f"{sentence} [[ev:{evidence_id}]]")
    assert len(raw) == 1, [r["claim_text"] for r in raw]
    return AtomicClaim(**raw[0])


def test_a_universal_quantifier_cannot_reach_supported():
    ev = EvidenceItem(
        evidence_id="CASE::00", source_id="CASE", chunk_id="CASE::00",
        title="CASE", chunk_text=TAT, category="CASE_STUDY", metadata={},
        source_path="data/corpus/CASE.md", relevance_score=0.9, selected=True,
    )
    store = VectorStore.ensure_seeded()
    sem = VectorStore.load().semantic_similarity

    true_one = _claim("VCG reduced pilot approval turnaround time by 18 percent.",
                      "CASE::00")
    assert verify_claim(true_one, {"CASE::00": ev}, sem)["status"] == \
        VerificationStatus.SUPPORTED

    generalised = _claim(
        "VCG has reduced pilot approval turnaround time by 18 percent for every "
        "lending client.", "CASE::00")
    result = verify_claim(generalised, {"CASE::00": ev}, sem)
    assert result["status"] == VerificationStatus.PARTIAL
    assert "generalises" in result["reason"]


# --------------------------------------------------------------------------- #
# A document that declares itself superseded was only flagged when its
# replacement happened to be retrieved too -- which top-k retrieval rarely does.
# --------------------------------------------------------------------------- #
def _ev(eid, src, text, **kw):
    return EvidenceItem(evidence_id=eid, source_id=src, chunk_id=eid, title=src,
                        chunk_text=text, category="CASE_STUDY", metadata={},
                        source_path=f"data/corpus/{src}.md",
                        relevance_score=0.9, selected=True, **kw)


def test_a_superseded_document_is_flagged_even_if_its_successor_is_absent():
    stale = _ev("OLD::00", "CASE_OLD", "Turnaround time was reduced by 40 percent.",
                superseded_by="CASE_NEW")
    state = {"selected_evidence": {"CHK-001": [stale]}, "errors": [],
             "warnings": [], "execution_log": []}
    found = conflicts.run(state)["evidence_conflicts"]
    assert [c.conflict_type for c in found] == ["superseded"]
    assert "NOT retrieved" in found[0].description


def test_a_document_marked_none_is_not_flagged():
    fine = _ev("OK::00", "CASE_OK", "Turnaround time fell 18 percent.",
               superseded_by="none")
    state = {"selected_evidence": {"CHK-001": [fine]}, "errors": [],
             "warnings": [], "execution_log": []}
    assert conflicts.run(state)["evidence_conflicts"] == []
