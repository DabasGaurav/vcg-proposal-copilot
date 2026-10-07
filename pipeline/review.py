"""Stage: await_human_review / revise_section / finalize (SPEC Section 2, Section 18).

Hard authority rule: there is NO code path from draft to export that skips human
approval of every section. ``can_export`` is the only gate and every export
function calls it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from models.schemas import ReviewDecision, ReviewDecisionRecord, VerificationStatus
from pipeline import claims as claims_stage
from pipeline import drafting as drafting_stage
from pipeline import traceability as traceability_stage
from pipeline import verification as verification_stage
from services.llm import reset_usage_sink, set_usage_sink
from services.persistence import get_store
from state.graph_state import ProposalAgentState


def submit_section_decision(
    state: ProposalAgentState,
    section_id: str,
    reviewer: str,
    decision: ReviewDecision,
    comment: str | None = None,
) -> ProposalAgentState:
    draft = state["proposal_draft"]
    section = next((s for s in draft.sections if s.section_id == section_id), None)
    if section is None:
        raise KeyError(f"unknown section_id {section_id}")
    section.review_status = decision
    state["section_review_status"][section.title] = decision.value
    rec = ReviewDecisionRecord(
        decision_id=f"DEC-{len(state['reviewer_decisions']) + 1:03d}",
        run_id=state["run_id"],
        section_id=section_id,
        reviewer=reviewer,
        decision=decision,
        comment=comment,
        timestamp=datetime.now(timezone.utc),
    )
    state["reviewer_decisions"].append(rec)
    get_store().record_decision(
        state["run_id"], section_id, reviewer, decision.value, comment
    )
    get_store().log(state["run_id"], "await_human_review", decision.value,
                    actor="human", notes=f"{section.title}: {comment or ''}")
    _recompute_status(state)
    _persist(state)
    return state


def apply_human_edit(state: ProposalAgentState, section_title: str,
                     new_markdown: str, reviewer: str = "reviewer") -> ProposalAgentState:
    """A direct human edit. Preserved verbatim through later regeneration of
    *other* sections (SPEC Section 4)."""
    state.setdefault("human_edits", {})[section_title] = new_markdown
    state["draft_sections"][section_title] = new_markdown
    draft = state["proposal_draft"]
    for s in draft.sections:
        if s.title == section_title:
            s.content_markdown = new_markdown
            s.human_edited = True
            s.version += 1
            s.review_status = ReviewDecision.PENDING
    get_store().log(state["run_id"], "human_edit", "APPLIED", actor="human",
                    notes=section_title)
    # re-verify just this section so the matrix reflects the edit
    _regen_verify(state, section_title, redraft=False)
    _persist(state)
    return state


def regenerate_section(state: ProposalAgentState, section_title: str) -> ProposalAgentState:
    """Regenerate one section. Any prior human edit of THIS section is discarded
    (that is the point of regenerating it); human edits of every OTHER section
    are preserved."""
    state.get("human_edits", {}).pop(section_title, None)
    get_store().log(state["run_id"], "revise_section", "REGENERATED", notes=section_title)
    _regen_verify(state, section_title, redraft=True)
    for s in state["proposal_draft"].sections:
        if s.title == section_title:
            s.version += 1
            s.review_status = ReviewDecision.PENDING
    _persist(state)
    return state


def _regen_verify(state, section_title, *, redraft: bool) -> None:
    token = set_usage_sink(state.setdefault("model_usage", []))
    try:
        if redraft:
            drafting_stage.run(state, only_section=section_title)
        claims_stage.run(state, only_section=section_title)
        verification_stage.run(state, semantic_fn=state.get("_semantic_fn"))
        traceability_stage.run(state)
        _recompute_status(state)
    finally:
        reset_usage_sink(token)


def _persist(state) -> None:
    """Re-save the full working state so a resumed run reflects review progress."""
    try:
        from pipeline.graph import save_run_state
        save_run_state(state)
    except Exception:
        pass  # persistence is best-effort; never block a review action


def _recompute_status(state) -> None:
    draft = state["proposal_draft"]
    statuses = {s.review_status for s in draft.sections}
    if statuses == {ReviewDecision.APPROVED}:
        state["review_status"] = "ALL_APPROVED"
    elif ReviewDecision.CHANGES_REQUESTED in statuses or ReviewDecision.REJECTED in statuses:
        state["review_status"] = "CHANGES_REQUESTED"
    else:
        state["review_status"] = "PENDING"


def unresolved_gaps(state) -> list:
    return [
        e for e in state["overall_traceability"]
        if e.verification_status == VerificationStatus.GAP
        and e.reviewer_decision != ReviewDecision.APPROVED
        and state.get("gap_overrides", {}).get(e.trace_id) is None
    ]


def override_gap(state, trace_id: str, reason: str, reviewer: str = "reviewer") -> None:
    if not reason or not reason.strip():
        raise ValueError("a gap override requires a recorded reason")
    state.setdefault("gap_overrides", {})[trace_id] = {"reason": reason, "by": reviewer}
    get_store().log(state["run_id"], "gap_override", "RECORDED", actor="human",
                    notes=f"{trace_id}: {reason}")
    _persist(state)


def _commercial_digest(state) -> str:
    """Fingerprint of the content a partner is signing off.

    Sign-off has to attach to a specific version. Without this, a partner could
    approve the commercial response and someone could then rewrite the fee --
    the approval survived the edit and the export gate still opened.
    """
    import hashlib

    draft = state.get("proposal_draft")
    parts = []
    for sec in (draft.sections if draft else []):
        if "commercial" in sec.title.lower() or "fee" in sec.title.lower():
            parts.append(sec.content_markdown or "")
    parts.extend(sorted(
        f"{k}:{v}" for k, v in (state.get("human_edits") or {}).items()
        if "commercial" in k.lower()
    ))
    return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:16]


def approve_price(state, reviewer: str, commercial_reference: str,
                  note: str) -> None:
    """Record partner sign-off for the separately prepared commercial response."""
    if not reviewer.strip() or not commercial_reference.strip() or not note.strip():
        raise ValueError("partner name, commercial reference, and approval note are required")
    decision = state.get("practice_lead_decision") or {}
    if decision.get("decision") != "BID":
        raise PermissionError("Practice lead must approve the bid before price sign-off")
    state["price_approval"] = {
        "reviewer": reviewer.strip(),
        "commercial_reference": commercial_reference.strip(),
        "note": note.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commercial_digest": _commercial_digest(state),
    }
    get_store().log(state["run_id"], "price_approval", "APPROVED", actor="human",
                    notes=f"{reviewer.strip()}: {commercial_reference.strip()}")
    _persist(state)


def can_export(state) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    draft = state["proposal_draft"]
    if (state.get("practice_lead_decision") or {}).get("decision") != "BID":
        reasons.append("practice lead has not approved a BID decision")
    price = state.get("price_approval")
    if not price:
        reasons.append("partner has not approved the commercial response")
    elif price.get("commercial_digest") != _commercial_digest(state):
        reasons.append(
            "the commercial response changed after partner sign-off; it must be "
            "approved again"
        )
    not_approved = [s.title for s in draft.sections
                    if s.review_status != ReviewDecision.APPROVED]
    if not_approved:
        reasons.append(
            f"{len(not_approved)} section"
            f"{'s await' if len(not_approved) != 1 else ' awaits'} reviewer approval "
            f"({', '.join(not_approved)})"
        )
    gaps = unresolved_gaps(state)
    if gaps:
        reasons.append(
            f"{len(gaps)} unsubstantiated claim{'s' if len(gaps) != 1 else ''} "
            f"require{'' if len(gaps) != 1 else 's'} resolution or a recorded override"
        )
    return (not reasons), reasons


def finalize(state) -> ProposalAgentState:
    ok, reasons = can_export(state)
    if not ok:
        raise PermissionError("Cannot finalise: " + "; ".join(reasons))
    state["proposal_draft"].status = ReviewDecision.APPROVED
    state["review_status"] = "FINALIZED"
    get_store().log(state["run_id"], "finalize", "APPROVED", actor="human")
    _persist(state)
    return state
