"""Stage: draft_sections (SPEC Section 13).

Section-by-section (Context -> Approach -> Credentials -> Risks -> Executive
Summary last). Grounding rules are applied in the prompt AND re-checked
deterministically afterwards (verification.py) -- the prompt is never trusted
alone. Insufficient evidence => a literal ``[EVIDENCE GAP: ...]`` marker;
human-only content => ``HUMAN INPUT REQUIRED``.
"""
from __future__ import annotations

import config
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
            "metadata": dict(e.metadata),
        }
        for e in evs
    ]


def _build_section_pool(state: ProposalAgentState) -> list[EvidenceItem]:
    """Selected evidence, plus the metric-bearing chunk of each selected source --
    but only where that chunk clears the ranker on its own merits.

    The drafter needs the passage that actually carries a figure, because the
    ranker may have selected a neighbouring intro paragraph from the same
    document. Promoting it unscored was a real bypass: the chunk was marked
    selected and handed a relevance score borrowed from a DIFFERENT chunk, so
    "cites only selected evidence" held at document level and not at passage
    level. Each candidate is now scored with the same weighted formula and the
    same threshold the ranker uses, and is dropped if it does not clear them.
    """
    from pipeline.ranking import _metadata_match, _wanted_tags
    from services.text import lexical_overlap
    from services.vectorstore import VectorStore

    pool: dict[str, EvidenceItem] = {}
    selected_sources: dict[str, EvidenceItem] = {}
    queries: dict[str, str] = {}
    checklist_by_id = {c.checklist_id: c for c in state["checklist"]}
    for cid, evs in state["selected_evidence"].items():
        item = checklist_by_id.get(cid)
        for e in evs:
            pool.setdefault(e.chunk_id, e)
            if e.source_id not in selected_sources:
                selected_sources[e.source_id] = e
                if item is not None:
                    queries[e.source_id] = (f"{item.requirement_text} "
                                            f"{item.evidence_need}")

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
        if best_chunk is None or best_n <= 0 or best_chunk.chunk_id in pool:
            continue

        # Score the candidate exactly as the ranker would, against the need that
        # put its document in play.
        query = queries.get(source_id)
        if not query:
            continue
        semantic = float(store.semantic_similarity(query, best_chunk.text))
        lexical = lexical_overlap(query, best_chunk.text)
        wanted = _wanted_tags(query)
        meta_match = _metadata_match(wanted, best_chunk.metadata)
        score = (config.W_SEMANTIC * semantic
                 + config.W_LEXICAL * lexical
                 + config.W_METADATA * meta_match)
        if score < config.SELECT_THRESHOLD:
            continue                       # does not clear the bar; not admitted

        pool[best_chunk.chunk_id] = EvidenceItem(
            evidence_id=f"POOL::{best_chunk.chunk_id}",
            source_id=source_id,
            title=template.title,
            category=template.category,
            chunk_id=best_chunk.chunk_id,
            chunk_text=best_chunk.text,
            source_path=best_chunk.source_path,
            relevance_score=max(0.0, min(1.0, score)),
            semantic_score=semantic,
            lexical_score=lexical,
            metadata_match_score=meta_match,
            selected=True,
            metadata=dict(best_chunk.metadata),
            reasoning=(f"metric-bearing passage of a selected source; scored "
                       f"against the same need: semantic {semantic:.2f}, lexical "
                       f"{lexical:.2f}, metadata {meta_match:.2f} -> {score:.2f} "
                       f"(threshold {config.SELECT_THRESHOLD:.2f})"),
        )
    return list(pool.values())


def run(state: ProposalAgentState, only_section: str | None = None) -> ProposalAgentState:
    llm = get_llm("draft_sections")
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
