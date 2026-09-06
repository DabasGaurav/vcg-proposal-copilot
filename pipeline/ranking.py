"""Stage: rank_evidence (SPEC Section 11).

final_score = 0.65*semantic + 0.20*lexical + 0.15*metadata_match.
Select >= SELECT_THRESHOLD; PARTIAL >= PARTIAL_THRESHOLD; otherwise REJECT with an
explicit reason. No candidate clears -> the checklist item is a GAP, never a
forced weak match. A mandatory NEEDS_EVIDENCE item with no viable candidate is
upgraded to CAPABILITY_GAP (go/no-go for a human).
"""
from __future__ import annotations

import config
from models.schemas import RequirementHandling
from services.text import normalize, significant_tokens
from state.graph_state import ProposalAgentState

_DOMAIN_TAGS = ("banking", "lending", "credit", "underwriting", "sme", "retail",
                "india", "indian", "southeast asia", "methodology", "team",
                "insurance", "actuarial", "supply chain")


def _wanted_tags(text: str) -> set[str]:
    low = normalize(text)
    return {t for t in _DOMAIN_TAGS if t in low}


def _metadata_match(wanted: set[str], meta: dict) -> float:
    if not wanted:
        return 0.0
    hay = normalize(" ".join(str(meta.get(k, "")) for k in
                             ("industry", "subsector", "region", "title", "category")))
    hits = sum(1 for t in wanted if t in hay)
    return hits / len(wanted)


def _reject_reason(ev, final: float, wanted: set[str]) -> str:
    if ev.usage_restriction == "nda_restricted":
        return "nda_restricted: may inform internal judgment, not citable in client-facing text"
    if ev.semantic_score < config.PARTIAL_THRESHOLD:
        return (f"semantic similarity {ev.semantic_score:.2f} below floor "
                f"{config.PARTIAL_THRESHOLD:.2f} -- topically off-target")
    md = _metadata_match(wanted, ev.metadata)
    if md == 0.0 and wanted:
        return (f"metadata mismatch: needs {sorted(wanted)}, evidence is "
                f"{ev.metadata.get('industry')}/{ev.metadata.get('subsector')}/"
                f"{ev.metadata.get('region')}")
    return (f"combined score {final:.2f} below selection threshold "
            f"{config.SELECT_THRESHOLD:.2f}")


def run(state: ProposalAgentState) -> ProposalAgentState:
    selected: dict[str, list] = {}
    rejected: dict[str, list] = {}
    gaps: list[str] = []
    checklist_by_id = {c.checklist_id: c for c in state["checklist"]}
    req_by_id = {r.requirement_id: r for r in state["rfp_data"].requirements}
    req_handling_override: dict[str, RequirementHandling] = {}

    for cid, candidates in state["retrieved_evidence"].items():
        item = checklist_by_id[cid]
        wanted = _wanted_tags(item.requirement_text + " " + item.evidence_need)
        sel, rej = [], []
        for ev in candidates:
            ev.metadata_match_score = _metadata_match(wanted, ev.metadata)
            final = (
                config.W_SEMANTIC * ev.semantic_score
                + config.W_LEXICAL * ev.lexical_score
                + config.W_METADATA * ev.metadata_match_score
            )
            ev.relevance_score = max(0.0, min(1.0, final))
            citable = ev.usage_restriction != "nda_restricted"
            if final >= config.SELECT_THRESHOLD and citable:
                ev.selected = True
                ev.reasoning = (
                    f"selected: semantic {ev.semantic_score:.2f}, lexical "
                    f"{ev.lexical_score:.2f}, metadata {ev.metadata_match_score:.2f} "
                    f"-> {final:.2f}"
                )
                sel.append(ev)
            else:
                ev.selected = False
                ev.rejection_reason = _reject_reason(ev, final, wanted)
                rej.append(ev)

        sel.sort(key=lambda e: e.relevance_score, reverse=True)
        selected[cid] = sel
        rejected[cid] = rej

        if sel:
            item.status = "COVERED"
        else:
            item.status = "GAP"
            gaps.append(item.requirement_id)
            req = req_by_id.get(item.requirement_id)
            no_partial = not [e for e in candidates
                              if e.semantic_score >= config.PARTIAL_THRESHOLD]
            # only a MANDATORY needs-evidence requirement with zero corpus coverage
            # is a capability gap (a go/no-go signal). Non-mandatory content
            # requirements just stay an ordinary checklist GAP.
            if (item.handling == RequirementHandling.NEEDS_EVIDENCE and no_partial
                    and req is not None and req.mandatory):
                req_handling_override[item.requirement_id] = RequirementHandling.CAPABILITY_GAP
                item.handling = RequirementHandling.CAPABILITY_GAP

    for req in state["rfp_data"].requirements:
        if req.requirement_id in req_handling_override:
            req.handling = RequirementHandling.CAPABILITY_GAP
            req.validation_note = "no corpus evidence -- capability gap (go/no-go)"

    state["selected_evidence"] = selected
    state["rejected_evidence"] = rejected
    state["retrieval_gaps"] = gaps
    if req_handling_override:
        state["warnings"].append(
            "Upgraded to CAPABILITY_GAP after retrieval found nothing: "
            + ", ".join(req_handling_override)
        )
    state["execution_log"].append(
        {
            "stage": "rank_evidence",
            "status": "ok",
            "detail": (
                f"{sum(len(v) for v in selected.values())} selected, "
                f"{sum(len(v) for v in rejected.values())} rejected (with reasons), "
                f"{len(gaps)} checklist gap(s)"
            ),
        }
    )
    return state
