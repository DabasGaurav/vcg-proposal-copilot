"""Stage: optional_web_enrichment (SPEC Section 12).

Secondary and optional. Web may supply *client / industry background only* --
never a VCG credential, result, methodology, or person. Default provider is
``mock`` and the core demo runs correctly with web disabled. Web results are
recorded on the state for display/context but are deliberately kept OUT of the
citable evidence pool.
"""
from __future__ import annotations

import config
from services.web_search import search
from state.graph_state import ProposalAgentState


def run(state: ProposalAgentState) -> ProposalAgentState:
    enabled = state.get("web_search_enabled", config.WEB_SEARCH_ENABLED)
    if not enabled:
        state["web_evidence"] = []
        state["execution_log"].append(
            {"stage": "optional_web_enrichment", "status": "skipped",
             "detail": "web search disabled -- internal evidence only"}
        )
        return state

    rd = state["rfp_data"]
    query = " ".join(filter(None, [
        rd.client or "",
        (rd.problem_statement or "")[:160],
        "industry background transformation drivers",
    ]))
    results = search(query, k=4)
    state["web_evidence"] = [
        {**r, "usage": "context_only"} for r in results
    ]
    if results:
        state["warnings"].append(
            f"Web enrichment ({config.WEB_SEARCH_PROVIDER}) returned {len(results)} "
            f"background item(s); used for context framing only, never cited as VCG "
            f"evidence."
        )
    state["execution_log"].append(
        {"stage": "optional_web_enrichment", "status": "ok",
         "detail": f"{len(results)} background result(s) via "
         f"{config.WEB_SEARCH_PROVIDER}; none citable as VCG evidence"}
    )
    return state
