"""Stage: retrieve_internal (SPEC Section 11).

2-4 queries per checklist item, top-k per query from the vector KB, dedupe by
chunk_id. Retrieval refinement is capped at config.MAX_RETRIEVAL_PASSES.
"""
from __future__ import annotations

import re

import config
from models.schemas import EvidenceCategory, EvidenceItem
from services.text import significant_tokens
from services.vectorstore import VectorStore
from state.graph_state import ProposalAgentState

_CATEGORY_MAP = {
    "CASE_STUDY": EvidenceCategory.CASE_STUDY,
    "METHODOLOGY": EvidenceCategory.METHODOLOGY,
    "TEAM_CV": EvidenceCategory.TEAM_CV,
    "WINNING_PROPOSAL": EvidenceCategory.WINNING_PROPOSAL,
    "MARKET_RESEARCH": EvidenceCategory.MARKET_RESEARCH,
}


def _queries(requirement_text: str, evidence_need: str, expand: bool) -> list[str]:
    base = [requirement_text.strip(), evidence_need.strip()]
    toks = significant_tokens(requirement_text)
    if toks:
        base.append(" ".join(toks[:8]))
    if expand:
        # widen with domain synonyms on a second pass
        widened = requirement_text.lower()
        widened = re.sub(r"turnaround|tat", "turnaround approval cycle time", widened)
        widened = re.sub(r"lending", "lending credit underwriting", widened)
        base.append(widened)
    seen, out = set(), []
    for q in base:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:4]


def _hit_to_evidence(hit, checklist_id: str, q_rank: int) -> EvidenceItem:
    meta = hit.metadata
    cat = _CATEGORY_MAP.get(str(meta.get("category", "")).upper(), EvidenceCategory.OTHER)
    return EvidenceItem(
        evidence_id=f"{checklist_id}::{hit.chunk_id}",   # unique per chunk, not per doc
        source_id=hit.document_id,
        title=str(meta.get("title", hit.document_id)),
        category=cat,
        chunk_id=hit.chunk_id,
        chunk_text=hit.text,
        source_path=hit.source_path,
        relevance_score=max(0.0, min(1.0, hit.semantic_score)),
        semantic_score=hit.semantic_score,
        lexical_score=hit.lexical_score,
        usage_restriction=str(meta.get("usage_restriction", "internal_only")),
        freshness_date=meta.get("freshness_date"),
        superseded_by=meta.get("superseded_by"),
        metadata=dict(meta),
        reasoning=f"retrieved for {checklist_id} (query rank {q_rank})",
    )


def run(state: ProposalAgentState, store: VectorStore | None = None) -> ProposalAgentState:
    store = store or VectorStore.load()
    retrieval_queries: dict[str, list[str]] = {}
    retrieved: dict[str, list[EvidenceItem]] = {}

    for item in state["checklist"]:
        best: dict[str, EvidenceItem] = {}
        for pass_no in range(config.MAX_RETRIEVAL_PASSES):
            qs = _queries(item.requirement_text, item.evidence_need, expand=pass_no > 0)
            retrieval_queries[item.checklist_id] = qs
            for q_rank, q in enumerate(qs):
                for hit in store.search(q, config.RETRIEVAL_TOP_K):
                    ev = _hit_to_evidence(hit, item.checklist_id, q_rank)
                    prev = best.get(ev.chunk_id)
                    if prev is None or ev.semantic_score > prev.semantic_score:
                        best[ev.chunk_id] = ev
            if any(e.semantic_score >= config.PARTIAL_THRESHOLD for e in best.values()):
                break  # good enough, no refinement pass needed
        retrieved[item.checklist_id] = sorted(
            best.values(), key=lambda e: e.semantic_score, reverse=True
        )[: config.RETRIEVAL_TOP_K]

    state["retrieval_queries"] = retrieval_queries
    state["retrieved_evidence"] = retrieved
    state["execution_log"].append(
        {
            "stage": "retrieve_internal",
            "status": "ok",
            "detail": f"{sum(len(v) for v in retrieved.values())} candidate chunks "
            f"across {len(retrieved)} checklist items",
        }
    )
    return state
