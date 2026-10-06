"""Transparent bid-fit assessment and practice-lead decision gate.

The score is a screening aid, not an automatic procurement decision. Only
requirements that genuinely need evidence are scored. Template workplan items
and submission instructions remain visible elsewhere in the application.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

import config

from models.schemas import RequirementHandling
from state.graph_state import ProposalAgentState


def run(state: ProposalAgentState) -> ProposalAgentState:
    sample_dir = config.ROOT / "data" / "sample_systems"
    sample_inputs = {}
    for filename in ("crm_opportunity.json", "hr_skills.json", "rate_card.json", "time_billing.json"):
        path = sample_dir / filename
        if path.exists():
            sample_inputs[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    state["system_inputs"] = sample_inputs
    requirements = {r.requirement_id: r for r in state["rfp_data"].requirements}
    evidence_items = [
        item for item in state["checklist"]
        if item.handling in (RequirementHandling.NEEDS_EVIDENCE,
                             RequirementHandling.CAPABILITY_GAP)
    ]
    covered = [item for item in evidence_items if state["selected_evidence"].get(item.checklist_id)]
    mandatory_gaps = [
        item for item in evidence_items
        if not state["selected_evidence"].get(item.checklist_id)
        and (requirements[item.requirement_id].mandatory is True
             or item.handling == RequirementHandling.CAPABILITY_GAP)
    ]
    score = round(100 * len(covered) / len(evidence_items)) if evidence_items else None
    if mandatory_gaps:
        recommendation = "NO_BID_REVIEW"
        reason = "Mandatory evidence requirements are not covered. A practice lead must review the gaps."
    elif score is None:
        recommendation = "REVIEW"
        reason = "No evidence requirements were identified; a practice lead must assess fit."
    elif score < 60:
        recommendation = "REVIEW"
        reason = "Less than 60% of evidence requirements have selected support."
    else:
        recommendation = "BID_REVIEW"
        reason = "No mandatory evidence gap was found; a practice lead must still approve the bid."
    state["qualification"] = {
        "score": score,
        "evidence_requirements": len(evidence_items),
        "covered_requirements": len(covered),
        "mandatory_gap_ids": [item.requirement_id for item in mandatory_gaps],
        "recommendation": recommendation,
        "reason": reason,
        "crm_opportunity_id": sample_inputs.get("crm_opportunity", {}).get("opportunity_id"),
        "crm_client_match": (
            sample_inputs.get("crm_opportunity", {}).get("client", "").lower()
            in (state["rfp_data"].client or "").lower()
        ) if sample_inputs.get("crm_opportunity") and state["rfp_data"].client else None,
    }
    state["practice_lead_decision"] = None
    state["execution_log"].append({
        "stage": "qualify", "status": "needs_human_approval",
        "detail": f"fit={score if score is not None else 'unscored'}; "
                  f"{len(mandatory_gaps)} mandatory evidence gap(s); {recommendation}",
    })
    return state


def record_decision(state: ProposalAgentState, decision: str, reviewer: str,
                    reason: str) -> ProposalAgentState:
    decision = decision.upper()
    if decision not in {"BID", "NO_BID"}:
        raise ValueError("decision must be BID or NO_BID")
    if not reviewer.strip() or not reason.strip():
        raise ValueError("practice lead name and decision reason are required")
    if not state.get("qualification"):
        raise ValueError("qualification must run before a practice-lead decision")
    state["practice_lead_decision"] = {
        "decision": decision,
        "reviewer": reviewer.strip(),
        "reason": reason.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state["execution_log"].append({
        "stage": "practice_lead_approval", "status": decision,
        "detail": f"{reviewer.strip()}: {reason.strip()}",
    })
    from pipeline.graph import save_run_state
    from services.persistence import get_store
    db = get_store()
    db.log(state["run_id"], "practice_lead_approval", decision,
           actor="human", notes=f"{reviewer.strip()}: {reason.strip()}")
    save_run_state(state, db)
    return state
