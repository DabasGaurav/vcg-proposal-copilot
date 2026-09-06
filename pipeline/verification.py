"""Stage: deterministic_verify -- the core of the whole system (SPEC Section 15).

NO step here asks an LLM "is this claim true". Verification is extractive and
rule-based only. This is "evidence-consistency verification", not general
factual verification (SPEC Section 15 precision note): the rules below catch
numeric contradiction, attribution mismatch, and context (geography/industry)
mismatch -- every error category the demo corpus is designed to surface -- and
nothing beyond that.
"""
from __future__ import annotations

import config
from models.schemas import (
    AtomicClaim,
    EvidenceItem,
    EvidenceMatch,
    VerificationStatus,
)
from services.text import (
    context_window_tokens,
    extract_numeric_tokens,
    lexical_overlap,
    numbers_match,
    significant_tokens,
)

# Authoritative attribution facts for the demo corpus (SPEC Section 9).
KNOWN_PERSON_TENURE = {"ananya mehta": 18, "rohan sen": 12}

# tokens that don't count as topical agreement around a number -- units, generic
# change verbs, and org/filler words that appear everywhere in the corpus.
_GENERIC_NEAR_NUM = {"percent", "reduced", "reduction", "percentage", "points",
                     "point", "fell", "rose", "improved", "cut", "increase",
                     "decrease", "year", "versus", "baseline", "vcg", "client",
                     "engagement", "initiative", "use", "across", "office"}


# --------------------------------------------------------------------------- #
# Step 9 -- numeric consistency within a +/- context window
# --------------------------------------------------------------------------- #
def _context_agrees(claim_text: str, evidence_text: str, ev_num) -> bool:
    window = context_window_tokens(
        evidence_text, ev_num.start, ev_num.end, config.NUMERIC_CONTEXT_WINDOW
    )
    win_tokens = set(significant_tokens(window)) - _GENERIC_NEAR_NUM
    claim_tokens = set(significant_tokens(claim_text)) - _GENERIC_NEAR_NUM
    return len(win_tokens & claim_tokens) >= 1


def numeric_consistency(claim_text: str, evidence_text: str) -> bool | None:
    """None  -> claim has no numeric token (check not applicable).
    True  -> every numeric token in the claim has a rounding-tolerant match in
             the evidence whose +/-20-token context is topically consistent.
    False -> at least one numeric token contradicts the evidence, or appears in
             the evidence only in an unrelated context (the DISTRACTOR case).
    """
    claim_nums = extract_numeric_tokens(claim_text)
    if not claim_nums:
        return None
    ev_nums = extract_numeric_tokens(evidence_text)
    for cn in claim_nums:
        same_unit = [en for en in ev_nums if en.canonical_unit() == cn.canonical_unit()]
        ok = any(
            numbers_match(cn.value, en.value, abs_tol=config.NUMERIC_ABS_TOLERANCE)
            and _context_agrees(claim_text, evidence_text, en)
            for en in same_unit
        )
        if not ok:
            return False
    return True


# --------------------------------------------------------------------------- #
# Step 10 -- attribution consistency (only if the claim names an entity)
# --------------------------------------------------------------------------- #
def attribution_consistent(claim: AtomicClaim, evidence_text: str) -> bool:
    """Default True. False ONLY on a real mismatch: the claim names a person and
    asserts a tenure that contradicts that person's authoritative record.
    """
    if not claim.named_entities:
        return True
    claim_years = {t.value for t in extract_numeric_tokens(claim.claim_text)
                   if t.canonical_unit() == "years"}
    if not claim_years:
        return True
    for entity in claim.named_entities:
        key = entity.strip().lower()
        truth = KNOWN_PERSON_TENURE.get(key)
        if truth is None:
            continue
        if not any(numbers_match(y, truth, abs_tol=0.0) for y in claim_years):
            return False
    return True


# --------------------------------------------------------------------------- #
# context (geography / industry) mismatch -- SPEC Section 15 Rule E
# --------------------------------------------------------------------------- #
def context_mismatch(claim: AtomicClaim, evidence_match: EvidenceMatch) -> bool:
    for qualifier in claim.context_qualifiers:
        if evidence_match.metadata_contradicts(qualifier):
            return True
    return False


# --------------------------------------------------------------------------- #
# Build the per-claim working record
# --------------------------------------------------------------------------- #
def build_match(
    claim: AtomicClaim,
    evidence: EvidenceItem | None,
    semantic_fn,
) -> EvidenceMatch:
    if evidence is None:
        return EvidenceMatch(claim_id=claim.claim_id, evidence_id=None,
                             numeric_match=None if not claim.numeric_tokens else False,
                             notes=["cited evidence did not resolve to real, selected evidence"])
    match = EvidenceMatch(
        claim_id=claim.claim_id,
        evidence_id=evidence.evidence_id,
        chunk_text=evidence.chunk_text,
        semantic_similarity=float(semantic_fn(claim.claim_text, evidence.chunk_text)),
        lexical_overlap=lexical_overlap(claim.claim_text, evidence.chunk_text),
        numeric_match=numeric_consistency(claim.claim_text, evidence.chunk_text),
        attribution_valid=attribution_consistent(claim, evidence.chunk_text),
        conflict_flag=bool(evidence.conflict_flag),
        evidence_metadata=dict(evidence.metadata),
    )
    match.context_mismatch = context_mismatch(claim, match)
    return match


# --------------------------------------------------------------------------- #
# Decision rules -- verbatim from SPEC Section 15
# --------------------------------------------------------------------------- #
def decide(claim: AtomicClaim, m: EvidenceMatch) -> VerificationStatus:
    if not claim.cited_evidence_ids:
        return VerificationStatus.GAP                       # Rule A
    if m is None or m.evidence_id is None:
        return VerificationStatus.GAP                       # Rule B
    if claim.numeric_tokens and m.numeric_match is False:
        return VerificationStatus.GAP                       # Rule C (never overridable)
    if claim.named_entities and not m.attribution_valid:
        return VerificationStatus.GAP                       # Rule D
    if context_mismatch(claim, m):
        return VerificationStatus.PARTIAL                   # Rule E
    if (m.semantic_similarity >= config.SEM_SUPPORTED
            and m.lexical_overlap >= config.LEX_SUPPORTED
            and m.numeric_match is not False):
        return VerificationStatus.SUPPORTED                 # Rule F
    if m.semantic_similarity >= config.SEM_PARTIAL and m.numeric_match is not False:
        return VerificationStatus.PARTIAL                   # Rule G
    return VerificationStatus.GAP


def confidence(m: EvidenceMatch) -> float:
    if m is None or m.evidence_id is None:
        return 0.0
    numeric_component = (
        1.0 if m.numeric_match is True else 0.5 if m.numeric_match is None else 0.0
    )
    attribution_component = 1.0 if m.attribution_valid else 0.0
    c = (0.50 * m.semantic_similarity
         + 0.25 * m.lexical_overlap
         + 0.15 * numeric_component
         + 0.10 * attribution_component)
    return round(max(0.0, min(1.0, c)), 4)


def reason_string(claim: AtomicClaim, m: EvidenceMatch, status: VerificationStatus) -> str:
    if not claim.cited_evidence_ids:
        return "GAP: claim cites no evidence (orphan claim)."
    if m is None or m.evidence_id is None:
        return "GAP: cited evidence id does not resolve to real, selected evidence."
    bits = [
        f"evidence={m.evidence_id}",
        f"semantic={m.semantic_similarity:.2f} (>= {config.SEM_SUPPORTED} to support)",
        f"lexical={m.lexical_overlap:.2f} (>= {config.LEX_SUPPORTED} to support)",
    ]
    if claim.numeric_tokens:
        bits.append(
            "numeric="
            + {True: "consistent", False: "CONTRADICTED in context window", None: "n/a"}[m.numeric_match]
        )
    if claim.named_entities:
        bits.append("attribution=" + ("valid" if m.attribution_valid else "MISMATCH"))
    if m.context_mismatch:
        bits.append("context=geography/industry qualifier contradicted by evidence metadata")
    if m.conflict_flag:
        bits.append("conflict=evidence flagged; cannot auto-resolve to SUPPORTED")
    return f"{status.value}: " + "; ".join(bits)


# --------------------------------------------------------------------------- #
# Full-claim verification
# --------------------------------------------------------------------------- #
def verify_claim(claim: AtomicClaim, evidence_index: dict, semantic_fn) -> dict:
    if not claim.requires_verification:
        return {
            "status": VerificationStatus.FORWARD_LOOKING,
            "match": None,
            "confidence": 1.0,
            "reason": "FORWARD_LOOKING: prospective statement, not a historical claim.",
        }

    # Step 1-2: citation exists, and cited ids are real + were selected
    resolved: EvidenceItem | None = None
    for cid in claim.cited_evidence_ids:
        resolved = evidence_index.get(cid)
        if resolved is not None:
            break

    match = build_match(claim, resolved, semantic_fn)
    status = decide(claim, match)

    # a conflicting claim can never auto-resolve to SUPPORTED (SPEC Section 11)
    if match and match.conflict_flag and status == VerificationStatus.SUPPORTED:
        status = VerificationStatus.PARTIAL
        match.notes.append("downgraded from SUPPORTED: evidence under unresolved conflict")

    return {
        "status": status,
        "match": match,
        "confidence": confidence(match),
        "reason": reason_string(claim, match, status),
    }


def build_evidence_index(state) -> dict:
    """Map every selected evidence item by BOTH its evidence_id and its source_id
    so a claim can cite either form. Keeps the best-scoring chunk per key.
    """
    index: dict[str, EvidenceItem] = {}
    for evs in state["selected_evidence"].values():
        for ev in evs:
            for key in (ev.evidence_id, ev.source_id, ev.chunk_id):
                cur = index.get(key)
                if cur is None or ev.relevance_score > cur.relevance_score:
                    index[key] = ev
    return index


def run(state, semantic_fn=None):
    from services.vectorstore import VectorStore

    if semantic_fn is None:
        store = VectorStore.load()
        semantic_fn = store.semantic_similarity

    index = build_evidence_index(state)
    results = {}
    for claim in state["atomic_claims"]:
        results[claim.claim_id] = verify_claim(claim, index, semantic_fn)

    state["_verification_results"] = results  # consumed by traceability.py
    counts: dict[str, int] = {}
    for r in results.values():
        counts[r["status"].value] = counts.get(r["status"].value, 0) + 1
    state["execution_log"].append(
        {"stage": "deterministic_verify", "status": "ok",
         "detail": ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))}
    )
    return state
