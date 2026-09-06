"""Stage: draft_sections (SPEC Section 13).

Section-by-section (Context -> Approach -> Credentials -> Risks -> Executive
Summary last). Grounding rules are applied in the prompt AND re-checked
deterministically afterwards (verification.py) -- the prompt is never trusted
alone. Insufficient evidence => a literal ``[EVIDENCE GAP: ...]`` marker;
human-only content => ``HUMAN INPUT REQUIRED``.
"""
from __future__ import annotations

from models.schemas import EvidenceItem
from services.llm import get_llm
from services.text import extract_numeric_tokens
from state.graph_state import ProposalAgentState


def _evidence_payload(evs) -> list[dict]:
    return [
        {
            "evidence_id": e.evidence_id,
            "source_id": e.source_id,
            "title": e.title,
            "category": e.category.value,
            "chunk_text": e.chunk_text,
            "relevance_score": e.relevance_score,
        }
        for e in evs
    ]


def _build_section_pool(state: ProposalAgentState) -> list[EvidenceItem]:
    """Union of all selected evidence, plus -- for every selected source document
    -- that document's most metric-dense chunk fetched straight from the KB.

    This is what lets the drafter cite the *exact* chunk that carries a metric
    (e.g. CASE_BANK_001's "18 percent" results chunk) so the deterministic
    verifier checks the claim against the chunk it was actually drawn from, not a
    neighbouring intro paragraph.
    """
    from services.vectorstore import VectorStore

    pool: dict[str, EvidenceItem] = {}
    selected_sources: dict[str, EvidenceItem] = {}
    for evs in state["selected_evidence"].values():
        for e in evs:
            pool.setdefault(e.chunk_id, e)
            selected_sources.setdefault(e.source_id, e)

    try:
        store = VectorStore.load()
    except FileNotFoundError:
        return list(pool.values())

    for source_id, template in selected_sources.items():
        best_chunk = None
        best_n = -1
        for ch in store.chunks:
            if ch.document_id != source_id:
                continue
            n = len(extract_numeric_tokens(ch.text))   # %, durations, tenure, ...
            if n > best_n:
                best_n = n
                best_chunk = ch
        if best_chunk is not None and best_n > 0 and best_chunk.chunk_id not in pool:
            pool[best_chunk.chunk_id] = EvidenceItem(
                evidence_id=f"POOL::{best_chunk.chunk_id}",
                source_id=source_id,
                title=template.title,
                category=template.category,
                chunk_id=best_chunk.chunk_id,
                chunk_text=best_chunk.text,
                source_path=best_chunk.source_path,
                relevance_score=template.relevance_score,
                selected=True,
                metadata=dict(best_chunk.metadata),
                reasoning="section evidence pool: metric-bearing chunk of a selected source",
            )
    return list(pool.values())


def run(state: ProposalAgentState, only_section: str | None = None) -> ProposalAgentState:
    llm = get_llm()
    rfp_data = state["rfp_data"]
    rfp_payload = {
        "client": rfp_data.client,
        "problem_statement": rfp_data.problem_statement,
        "timeline": rfp_data.timeline,
    }

    by_section: dict[str, list] = {}
    for item in state["checklist"]:
        by_section.setdefault(item.target_section, []).append(item)

    pool = _build_section_pool(state)
    state["selected_evidence"]["__pool__"] = pool  # visible to verifier + UI
    pool_payload = _evidence_payload(pool)

    evidence_by_checklist = {
        cid: _evidence_payload(evs)
        for cid, evs in state["selected_evidence"].items()
        if cid != "__pool__"
    }
    supported_ids = sorted({e.source_id for e in pool})

    outline = state["proposal_outline"]
    sections = [only_section] if only_section else outline
    drafts = dict(state.get("draft_sections", {}))

    for title in sections:
        section_checklist = [
            {
                "checklist_id": i.checklist_id,
                "requirement_text": i.requirement_text,
                "evidence_need": i.evidence_need,
                "handling": i.handling.value,
            }
            for i in by_section.get(title, [])
        ]
        md = llm.draft_section(
            title, rfp_payload, section_checklist, evidence_by_checklist,
            all_supported_evidence_ids=supported_ids,
            section_evidence_pool=pool_payload,
        )
        # preserve a prior direct human edit of THIS section (SPEC Section 4)
        if title in state.get("human_edits", {}):
            md = state["human_edits"][title]
        drafts[title] = md

    state["draft_sections"] = drafts
    state["execution_log"].append(
        {
            "stage": "draft_sections" + (f" ({only_section})" if only_section else ""),
            "status": "ok",
            "detail": f"{len(sections)} section(s) drafted; "
            f"{sum('[EVIDENCE GAP' in d for d in drafts.values())} contain gap markers",
        }
    )
    return state
