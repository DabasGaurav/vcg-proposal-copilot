"""Pipeline state (SPEC.md Section 6).

Whether the orchestrator is LangGraph or the plain function chain (SPEC Section 0
fallback -- this build uses the plain chain), every stage reads and writes this
one dict and appends to ``execution_log``.
"""
from __future__ import annotations

from typing import TypedDict

from models.schemas import (
    AtomicClaim,
    EvidenceChecklistItem,
    EvidenceConflict,
    EvidenceItem,
    ProposalDraft,
    RFPRequirements,
    ReviewDecisionRecord,
    TraceabilityEntry,
)


class ProposalAgentState(TypedDict, total=False):
    run_id: str
    version: int

    rfp_path: str
    rfp_raw_text: str
    rfp_filename: str
    language: str

    rfp_data: RFPRequirements
    requirement_validation_errors: list[str]

    checklist: list[EvidenceChecklistItem]
    proposal_outline: list[str]
    procedural_checklist: list[str]
    human_input_requirements: list[str]

    retrieval_queries: dict[str, list[str]]
    retrieved_evidence: dict[str, list[EvidenceItem]]
    selected_evidence: dict[str, list[EvidenceItem]]
    rejected_evidence: dict[str, list[EvidenceItem]]
    retrieval_gaps: list[str]
    evidence_conflicts: list[EvidenceConflict]

    web_evidence: list[EvidenceItem]
    web_search_enabled: bool

    draft_sections: dict[str, str]
    proposal_draft: ProposalDraft

    atomic_claims: list[AtomicClaim]
    overall_traceability: list[TraceabilityEntry]

    review_status: str
    section_review_status: dict[str, str]
    reviewer_decisions: list[ReviewDecisionRecord]
    human_edits: dict[str, str]

    warnings: list[str]
    errors: list[str]
    retry_count: dict[str, int]
    execution_log: list[dict]


def new_state(**kwargs) -> ProposalAgentState:
    base: ProposalAgentState = {
        "version": 1,
        "language": "en",
        "requirement_validation_errors": [],
        "checklist": [],
        "proposal_outline": [],
        "procedural_checklist": [],
        "human_input_requirements": [],
        "retrieval_queries": {},
        "retrieved_evidence": {},
        "selected_evidence": {},
        "rejected_evidence": {},
        "retrieval_gaps": [],
        "evidence_conflicts": [],
        "web_evidence": [],
        "web_search_enabled": False,
        "draft_sections": {},
        "atomic_claims": [],
        "overall_traceability": [],
        "review_status": "PENDING",
        "section_review_status": {},
        "reviewer_decisions": [],
        "human_edits": {},
        "warnings": [],
        "errors": [],
        "retry_count": {},
        "execution_log": [],
    }
    base.update(kwargs)
    return base
