"""Stage: extract_atomic_claims (SPEC Section 14).

LLM step -- decomposition only, never verification. Compound sentences are split;
recognizably prospective statements are marked requires_verification=False.
"""
from __future__ import annotations

from models.schemas import AtomicClaim, ClaimType
from services.llm import get_llm
from state.graph_state import ProposalAgentState


def run(state: ProposalAgentState, only_section: str | None = None) -> ProposalAgentState:
    llm = get_llm()
    kept = [
        c for c in state.get("atomic_claims", [])
        if only_section and c.section_name != only_section
    ] if only_section else []

    targets = (
        {only_section: state["draft_sections"][only_section]}
        if only_section else state["draft_sections"]
    )
    claims: list[AtomicClaim] = list(kept)
    for title, md in targets.items():
        for raw in llm.decompose_claims(title, md):
            claims.append(
                AtomicClaim(
                    claim_id=raw["claim_id"],
                    section_name=raw["section_name"],
                    claim_text=raw["claim_text"],
                    claim_type=ClaimType(raw["claim_type"]),
                    source_checklist_id=raw.get("source_checklist_id"),
                    cited_evidence_ids=raw["cited_evidence_ids"],
                    numeric_tokens=raw["numeric_tokens"],
                    named_entities=raw["named_entities"],
                    context_qualifiers=raw["context_qualifiers"],
                    requires_verification=raw["requires_verification"],
                )
            )
    state["atomic_claims"] = claims
    state["execution_log"].append(
        {
            "stage": "extract_atomic_claims" + (f" ({only_section})" if only_section else ""),
            "status": "ok",
            "detail": f"{len(claims)} atomic claim(s); "
            f"{sum(c.requires_verification for c in claims)} require verification",
        }
    )
    return state
