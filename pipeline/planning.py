"""Stage: plan_response (SPEC Section 8.4, Section 13 outline).

Turns validated requirements into an evidence checklist + proposal outline +
the list of sections that need human-only content. Procedural items stay in
their own checklist and never become an evidence need.
"""
from __future__ import annotations

from models.schemas import EvidenceChecklistItem, RequirementCategory, RequirementHandling
from services.llm import get_llm
from state.graph_state import ProposalAgentState


def run(state: ProposalAgentState) -> ProposalAgentState:
    llm = get_llm()
    rfp_data = state["rfp_data"]
    raw = llm.plan_response(
        {
            "requirements": [
                {
                    "requirement_id": r.requirement_id,
                    "text": r.text,
                    "category": r.category.value,
                    "handling": r.handling.value,
                    "section": r.source_span.section or "Context & Problem Understanding",
                }
                for r in rfp_data.requirements
            ]
        }
    )
    checklist = [
        EvidenceChecklistItem(
            checklist_id=item["checklist_id"],
            requirement_id=item["requirement_id"],
            requirement_text=item["requirement_text"],
            evidence_need=item["evidence_need"],
            category=RequirementCategory(item["category"]),
            handling=RequirementHandling(item["handling"]),
            target_section=item["target_section"],
        )
        for item in raw["checklist"]
    ]
    state["checklist"] = checklist
    state["proposal_outline"] = raw["proposal_outline"]
    state["human_input_requirements"] = raw["human_input_requirements"]
    state["execution_log"].append(
        {
            "stage": "plan_response",
            "status": "ok",
            "detail": (
                f"{len(checklist)} evidence-checklist items, "
                f"{len(raw['human_input_requirements'])} human-input requirement(s), "
                f"{len(state['procedural_checklist'])} procedural item(s)"
            ),
        }
    )
    return state
