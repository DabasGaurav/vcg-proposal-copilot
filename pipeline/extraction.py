"""Stages: decompose_rfp + validate_requirements (SPEC Section 8).

Source-span validation is the anti-hallucination gate: a requirement whose quote
cannot be located in the normalised RFP text is flagged and NOT passed
downstream. Validation retries are capped (config.MAX_VALIDATION_RETRIES); the
mock extractor is deterministic so a retry just re-runs, but the retry/flag
control flow is real and exercised by tests with an injected bad span.
"""
from __future__ import annotations

import config
from models.schemas import (
    RequirementCategory,
    RequirementHandling,
    RFPRequirement,
    RFPRequirements,
    SourceSpan,
)
from services.llm import get_llm
from services.text import is_locatable
from state.graph_state import ProposalAgentState


def _to_requirement(raw: dict, rfp_text: str) -> RFPRequirement:
    quote = raw["quote"]
    locatable = is_locatable(quote, rfp_text)
    start = end = None
    norm_hit = rfp_text.lower().find(quote.lower()[:60])
    if norm_hit != -1:
        start, end = norm_hit, norm_hit + len(quote)
    return RFPRequirement(
        requirement_id=raw["requirement_id"],
        text=raw["text"],
        category=RequirementCategory(raw["category"]),
        handling=RequirementHandling(raw["handling"]),
        mandatory=raw["mandatory"],
        extraction_confidence=raw["extraction_confidence"],
        source_span=SourceSpan(section=raw["section"], quote=quote,
                               start_char=start, end_char=end),
        valid=locatable,
        validation_note=None if locatable else "source quote not locatable in RFP text",
    )


def run(state: ProposalAgentState) -> ProposalAgentState:
    llm = get_llm()
    rfp_text = state["rfp_raw_text"]

    attempt = 0
    while True:
        raw = llm.extract_requirements(rfp_text, state.get("rfp_filename", ""))
        requirements = [_to_requirement(r, rfp_text) for r in raw["requirements"]]
        invalid = [r for r in requirements if not r.valid]
        attempt += 1
        if not invalid or attempt > config.MAX_VALIDATION_RETRIES:
            break

    errors = [
        f"{r.requirement_id}: {r.validation_note} -- quote={r.source_span.quote!r}"
        for r in requirements
        if not r.valid
    ]
    valid_reqs = [r for r in requirements if r.valid]

    # capability gaps are a human go/no-go signal -- keep them visible even though
    # they are not "valid evidence" requirements.
    cap_gaps = [r for r in valid_reqs if r.handling == RequirementHandling.CAPABILITY_GAP]

    rfp_data = RFPRequirements(
        client=raw["client"],
        problem_statement=raw["problem_statement"],
        timeline=raw["timeline"],
        scope_items=raw["scope_items"],
        deliverables=raw["deliverables"],
        evaluation_criteria=raw["evaluation_criteria"],
        requirements=valid_reqs,
        procedural_checklist=raw["procedural_checklist"],
        warnings=list(raw["warnings"]),
    )
    if cap_gaps:
        rfp_data.warnings.append(
            "CAPABILITY GAP (go/no-go for a human): "
            + "; ".join(r.text for r in cap_gaps)
        )

    state["rfp_data"] = rfp_data
    state["requirement_validation_errors"] = errors
    state["procedural_checklist"] = list(raw["procedural_checklist"])
    state["warnings"].extend(rfp_data.warnings)
    state["execution_log"].append(
        {
            "stage": "decompose_rfp + validate_requirements",
            "status": "ok" if not errors else "flagged",
            "detail": (
                f"{len(valid_reqs)} valid requirements, {len(errors)} ungrounded "
                f"(dropped), {len(cap_gaps)} capability gap(s), "
                f"{len(raw['procedural_checklist'])} procedural items"
            ),
        }
    )
    return state
