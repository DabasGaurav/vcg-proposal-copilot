"""Stage: build_traceability (SPEC Section 1 hero screen, Section 15 data model).

Requirement -> Evidence -> Draft Claim -> Status, as a list of TraceabilityEntry
join records. Many-to-many: one requirement can produce several rows; one claim
can substantiate several requirements. No uniqueness constraint on either side.

Also assembles the ProposalDraft (sections + claim counts) and a
requirement-summary roll-up so every requirement appears at least once.
"""
from __future__ import annotations

import uuid


def evidence_display_id(evidence_id: str | None) -> str:
    """CHK-014::CV_001::00.00 -> CV_001 ; POOL::CASE_BANK_001::02.00 -> CASE_BANK_001."""
    if not evidence_id:
        return "(none)"
    parts = evidence_id.split("::")
    for p in parts:
        if p not in ("POOL",) and not p.startswith("CHK-") and not p.replace(".", "").isdigit():
            return p
    return parts[-1]

from models.schemas import (
    ProposalDraft,
    ProposalSection,
    RequirementHandling,
    ReviewDecision,
    TraceabilityEntry,
    VerificationStatus,
)
from state.graph_state import ProposalAgentState


def _match_requirements(state, claim):
    """Associate a claim with the RFP requirement(s) it actually speaks to.

    Prospective / narrative framing (requires_verification=False) is not pinned
    to a requirement -- it gets a single '-' row. A historical claim is matched
    to the best requirement routed to its section by significant-token overlap
    (ties within 0.15 kept, capped at 2); if nothing in-section matches, we fall
    back to the best content requirement anywhere, else '-'.
    """
    from services.text import significant_tokens

    by_id = {i.checklist_id: i for i in state["checklist"]}
    # 1. exact provenance from the drafter wins
    if claim.source_checklist_id and claim.source_checklist_id in by_id:
        return [by_id[claim.source_checklist_id]]

    section_items = [i for i in state["checklist"] if i.target_section == claim.section_name]
    if not claim.requires_verification:
        return [None]
    ctoks = set(significant_tokens(claim.claim_text))
    if not ctoks:
        return section_items[:1] or [None]

    def score(item):
        itoks = set(significant_tokens(item.requirement_text))
        return len(ctoks & itoks) / max(1, len(itoks))

    pool = section_items or list(state["checklist"])
    ranked = sorted(((score(i), i) for i in pool), key=lambda t: t[0], reverse=True)
    ranked = [(s, i) for s, i in ranked if s > 0.0]
    if not ranked:
        return [None]
    best = ranked[0][0]
    return [i for s, i in ranked if best - s <= 0.15][:2]


def run(state: ProposalAgentState) -> ProposalAgentState:
    results = state["_verification_results"]
    claims_by_id = {c.claim_id: c for c in state["atomic_claims"]}
    req_by_id = {r.requirement_id: r for r in state["rfp_data"].requirements}

    entries: list[TraceabilityEntry] = []
    covered_reqs: set[str] = set()

    for claim in state["atomic_claims"]:
        res = results[claim.claim_id]
        match = res["match"]
        for item in _match_requirements(state, claim):
            req_id = item.requirement_id if item else "-"
            req_text = item.requirement_text if item else f"({claim.section_name} narrative)"
            src_span = (
                req_by_id[req_id].source_span
                if item and req_id in req_by_id else None
            )
            entries.append(TraceabilityEntry(
                trace_id=f"TRC-{uuid.uuid4().hex[:8]}",
                requirement_id=req_id,
                rfp_requirement=req_text,
                requirement_source_span=src_span,
                matched_evidence_id=(match.evidence_id if match else None),
                matched_chunk_text=(match.chunk_text if match else None),
                draft_section=claim.section_name,
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                verification_status=res["status"],
                confidence_score=res["confidence"],
                lexical_overlap=(match.lexical_overlap if match else 0.0),
                semantic_similarity=(match.semantic_similarity if match else 0.0),
                numeric_match=(match.numeric_match if match else None),
                attribution_valid=(match.attribution_valid if match else True),
                conflict_flag=(match.conflict_flag if match else False),
                verification_reason=res["reason"],
            ))
            if item:
                covered_reqs.add(req_id)

    # requirements with no claim at all -> explicit rows so nothing hides
    for req in state["rfp_data"].requirements:
        if req.requirement_id in covered_reqs:
            continue
        if req.handling in (RequirementHandling.PROCEDURAL_ONLY,):
            continue
        if req.handling == RequirementHandling.CAPABILITY_GAP:
            status, section, reason = (
                VerificationStatus.GAP, "(capability gap)",
                "CAPABILITY GAP: corpus has zero coverage -- human go/no-go decision.",
            )
        elif req.handling in (RequirementHandling.TEMPLATE_SATISFIABLE,
                              RequirementHandling.PROCEDURAL_ONLY):
            status, section, reason = (
                VerificationStatus.PARTIAL, "Proposed Approach & Workplan",
                "TEMPLATE/NARRATIVE-SATISFIABLE: addressed in the approach/workplan "
                "narrative; no evidence citation required.",
            )
        elif req.handling == RequirementHandling.NEEDS_HUMAN_INPUT:
            status, section, reason = (
                VerificationStatus.PARTIAL, "(human input)",
                "HUMAN INPUT REQUIRED: content supplied by the engagement partner, "
                "not drafted or verified by the agent.",
            )
        else:
            status, section, reason = (
                VerificationStatus.GAP, "(unaddressed)",
                "GAP: no evidence selected and no claim drafted for this requirement.",
            )
        entries.append(TraceabilityEntry(
            trace_id=f"TRC-{uuid.uuid4().hex[:8]}",
            requirement_id=req.requirement_id,
            rfp_requirement=req.text,
            requirement_source_span=req.source_span,
            matched_evidence_id=None,
            matched_chunk_text=None,
            draft_section=section,
            claim_id="(none)",
            claim_text="(no drafted claim)",
            verification_status=status,
            confidence_score=0.0,
            verification_reason=reason,
        ))

    # ProposalDraft assembly
    sections: list[ProposalSection] = []
    human_edits = state.get("human_edits", {})
    for idx, title in enumerate(state["proposal_outline"]):
        content = human_edits.get(title, state["draft_sections"].get(title, ""))
        sec_claims = [c for c in state["atomic_claims"] if c.section_name == title]
        sec_ev = sorted({
            results[c.claim_id]["match"].evidence_id
            for c in sec_claims
            if results[c.claim_id]["match"] and results[c.claim_id]["match"].evidence_id
        })
        has_gap = "[EVIDENCE GAP" in content or any(
            results[c.claim_id]["status"] == VerificationStatus.GAP for c in sec_claims
        )
        prior = next((s for s in (state.get("proposal_draft").sections
                                  if state.get("proposal_draft") else []) if s.title == title), None)
        sections.append(ProposalSection(
            section_id=f"SEC-{idx:02d}",
            title=title,
            content_markdown=content,
            version=(prior.version if prior else 1),
            evidence_ids=sec_ev,
            claim_ids=[c.claim_id for c in sec_claims],
            has_gaps=has_gap,
            review_status=(prior.review_status if prior else ReviewDecision.PENDING),
            human_edited=title in human_edits,
        ))

    def _count(st):
        return sum(1 for e in entries if e.verification_status == st and e.claim_id != "(none)")

    draft = ProposalDraft(
        proposal_id=f"PROP-{state['run_id'][:8]}",
        client=state["rfp_data"].client or "Unknown",
        rfp_id=state.get("rfp_filename", "rfp"),
        run_id=state["run_id"],
        sections=sections,
        overall_traceability=entries,
        supported_claim_count=_count(VerificationStatus.SUPPORTED),
        partial_claim_count=_count(VerificationStatus.PARTIAL),
        gap_claim_count=_count(VerificationStatus.GAP),
    )

    # requirement-summary roll-up: every requirement appears at least once
    summary = []
    for req in state["rfp_data"].requirements:
        rows = [e for e in entries if e.requirement_id == req.requirement_id]
        statuses = [e.verification_status for e in rows]
        if VerificationStatus.SUPPORTED in statuses:
            roll = "SUPPORTED"
        elif VerificationStatus.PARTIAL in statuses:
            roll = "PARTIAL"
        elif statuses:
            roll = statuses[0].value
        else:
            roll = "NO_ROW"
        summary.append({
            "requirement_id": req.requirement_id,
            "requirement": req.text,
            "handling": req.handling.value,
            "mandatory": req.mandatory,
            "rollup_status": roll,
            "row_count": len(rows),
            "source_quote": req.source_span.quote,
        })

    state["proposal_draft"] = draft
    state["overall_traceability"] = entries
    state["requirement_summary"] = summary
    state["execution_log"].append({
        "stage": "build_traceability",
        "status": "ok",
        "detail": (
            f"{len(entries)} traceability rows; "
            f"SUPPORTED={draft.supported_claim_count} "
            f"PARTIAL={draft.partial_claim_count} GAP={draft.gap_claim_count}"
        ),
    })
    return state
