"""Deterministic, fixture-aware mock for the four LLM-delegated operations.

This is not an attempt at a good LLM. It does structural parsing of the RFP and
of drafted prose, plus two *planted* behaviours so the deterministic verifier has
real errors to catch:

  * a numeric-threshold evaluation criterion the corpus cannot support
    (">30% turnaround improvement") is answered with an uncited "35%" overclaim
    -- the hero GAP row (SPEC Section 1);
  * a genuinely supported metric ("18%" from CASE_BANK_001) is drafted as a
    compound sentence so claim decomposition and per-claim verification are
    exercised.

Swapping LLM_PROVIDER=litellm routes these same four operations through a real
model instead (see services/llm.py).
"""
from __future__ import annotations

import re

from services.llm import (
    bullets,
    is_prospective,
    parse_sections,
    sentences,
    split_compound,
)
from services.text import (
    extract_context_qualifiers,
    extract_named_entities,
    extract_numeric_tokens,
)

# --------------------------------------------------------------------------- #
# 1. Requirement extraction
# --------------------------------------------------------------------------- #
_MANDATORY_MARKERS = ("must", "mandatory", "pass/fail", "required", "shall")
_CAPABILITY_GAP_HINTS = ("actuarial ai", "actuarial-ai", "machine-learning reserving",
                         "machine learning reserving", "ml reserving", "deep actuarial")
_HUMAN_INPUT_HINTS = ("named team", "named team members", "named individuals",
                      "time commitment", "staffing")
_COMMERCIAL_HINTS = ("pricing", "commercial", "fee", "price")
_COMPLIANCE_HINTS = ("declaration", "signed", "reference", "portal", "format",
                     "arial", "pages", "spacing", "english")


def _first_sentence(block: str) -> str:
    block = block.strip()
    m = re.split(r"(?<=[.!?])\s", block, maxsplit=1)
    return m[0].strip() if m else block


def _mandatory(text: str) -> bool:
    low = text.lower()
    return any(mk in low for mk in _MANDATORY_MARKERS)


def _target_section(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("turnaround", "measurable result", "percent", "%",
                              "comparable engagement", "comparable lending",
                              "demonstrated experience", "measured", "prior experience")):
        return "Relevant Experience & Credentials"
    if any(k in low for k in ("workplan", "week", "pilot", "methodology", "phased",
                              "diagnose", "redesign", "prototype", "assess", "define")):
        return "Proposed Approach & Workplan"
    if any(k in low for k in ("team", "named", "cv", "curriculum")):
        return "Team & Credentials"
    if "risk" in low:
        return "Risks & Mitigations"
    if any(k in low for k in _COMMERCIAL_HINTS):
        return "Commercial"
    return "Context & Problem Understanding"


def extract_requirements(rfp_text: str, filename: str = "") -> dict:
    sec = parse_sections(rfp_text)
    warnings: list[str] = []
    requirements: list[dict] = []
    procedural: list[str] = []
    rid = 0

    def add(text: str, category: str, handling: str, quote: str, section: str,
            conf: float, mandatory: bool | None):
        nonlocal rid
        rid += 1
        requirements.append(
            {
                "requirement_id": f"REQ-{rid:03d}",
                "text": text.strip(),
                "category": category,
                "handling": handling,
                "mandatory": mandatory,
                "extraction_confidence": conf,
                "quote": quote.strip(),
                "section": section,
            }
        )

    client = _first_sentence(sec.get("client", "")) or None
    problem = sec.get("background", "").strip() or None
    timeline = _first_sentence(sec.get("timeline", "")) or None

    if timeline:
        add(timeline, "CONTENT", "NEEDS_EVIDENCE", timeline, "Proposed Approach & Workplan",
            0.82, _mandatory(timeline))

    scope_items = bullets(sec.get("scope of work", "")) or bullets(sec.get("scope", ""))
    for item in scope_items:
        for frag in split_compound(item):
            add(frag, "CONTENT", "TEMPLATE_SATISFIABLE", item,
                "Proposed Approach & Workplan",
                0.9 if frag == item else 0.75, _mandatory(item))

    deliverables = bullets(sec.get("deliverables", ""))
    for item in deliverables:
        add(item, "CONTENT", "TEMPLATE_SATISFIABLE", item, "Proposed Approach & Workplan",
            0.88, _mandatory(item))

    eval_block = sec.get("evaluation criteria", "")
    if not eval_block.strip():
        warnings.append(
            "RFP contains no explicit evaluation criteria section -- not inventing a rubric."
        )
    for item in bullets(eval_block):
        low = item.lower()
        for frag in split_compound(item):
            flow = frag.lower()
            if any(h in flow or h in low for h in _CAPABILITY_GAP_HINTS):
                handling = "CAPABILITY_GAP"
            elif any(h in flow for h in _HUMAN_INPUT_HINTS):
                handling = "NEEDS_HUMAN_INPUT"
            elif "risk" in flow:
                handling = "TEMPLATE_SATISFIABLE"
            else:
                handling = "NEEDS_EVIDENCE"
            add(frag, "CONTENT", handling, item, _target_section(frag),
                0.9 if frag == item else 0.75,
                True if item.lower().startswith("mandatory") else _mandatory(item))

    proc_block = next(
        (sec[k] for k in ("procedural requirements", "submission notes",
                          "submission requirements", "administrative requirements",
                          "compliance requirements") if sec.get(k)),
        "",
    )
    for item in bullets(proc_block):
        procedural.append(item)
        low = item.lower()
        if any(h in low for h in _COMMERCIAL_HINTS):
            category, handling = "COMMERCIAL", "NEEDS_HUMAN_INPUT"
        elif any(h in low for h in _COMPLIANCE_HINTS):
            category, handling = "COMPLIANCE", "PROCEDURAL_ONLY"
        else:
            category, handling = "PROCEDURAL", "PROCEDURAL_ONLY"
        add(item, category, handling, item, "Assumptions & Ways of Working", 0.92, True)

    return {
        "client": client,
        "problem_statement": problem,
        "timeline": timeline,
        "scope_items": scope_items,
        "deliverables": deliverables,
        "evaluation_criteria": bullets(eval_block),
        "requirements": requirements,
        "procedural_checklist": procedural,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# 2. Response planning
# --------------------------------------------------------------------------- #
STANDARD_OUTLINE = [
    "Context & Problem Understanding",
    "Proposed Approach & Workplan",
    "Team & Credentials",
    "Relevant Experience & Credentials",
    "Risks & Mitigations",
    "Commercial",
    "Executive Summary",
]


def plan_response(rfp_data: dict) -> dict:
    checklist: list[dict] = []
    human_input: list[str] = []
    cid = 0
    for req in rfp_data["requirements"]:
        handling = req["handling"]
        if handling == "PROCEDURAL_ONLY":
            continue  # stays in the procedural checklist only -- never evidence prose
        if handling == "NEEDS_HUMAN_INPUT":
            human_input.append(req["text"])
        cid += 1
        need = f"Evidence that VCG can satisfy: {req['text'].rstrip('.').lower()}."
        checklist.append(
            {
                "checklist_id": f"CHK-{cid:03d}",
                "requirement_id": req["requirement_id"],
                "requirement_text": req["text"],
                "evidence_need": need,
                "category": req["category"],
                "handling": handling,
                "target_section": req["section"],
                "status": "PENDING",
            }
        )
    return {
        "checklist": checklist,
        "proposal_outline": STANDARD_OUTLINE,
        "human_input_requirements": human_input,
    }


# --------------------------------------------------------------------------- #
# 3. Drafting
# --------------------------------------------------------------------------- #
_THRESHOLD_RE = re.compile(
    r"(?:greater than|more than|over|at least|exceed(?:ing)?|>)\s*(\d+(?:\.\d+)?)\s*(?:percent|%)",
    re.I,
)


def _threshold_pct(text: str) -> float | None:
    m = _THRESHOLD_RE.search(text)
    return float(m.group(1)) if m else None


def _evidence_supports_threshold(evidence: list[dict], pct: float) -> bool:
    for ev in evidence:
        for tok in extract_numeric_tokens(ev["chunk_text"]):
            if tok.canonical_unit() == "percent" and tok.value >= pct:
                lowered = ev["chunk_text"].lower()
                if any(k in lowered for k in ("turnaround", "tat", "approval time",
                                              "cycle time")):
                    return True
    return False


def _pool_by_source(pool: list[dict], source_id: str, keyword: str | None = None) -> dict | None:
    matches = [e for e in pool if e["source_id"] == source_id]
    if keyword:
        kw = keyword.lower()
        for e in matches:
            if kw in e["chunk_text"].lower():
                return e
    return matches[0] if matches else None


def _pool_metric_case(pool: list[dict]) -> dict | None:
    """A CASE_STUDY pool chunk that carries a turnaround/handoff percentage."""
    for e in pool:
        if e.get("category") != "CASE_STUDY":
            continue
        low = e["chunk_text"].lower()
        has_pct = any(t.canonical_unit() == "percent"
                      for t in extract_numeric_tokens(e["chunk_text"]))
        if has_pct and any(k in low for k in ("turnaround", "handoff", "processing effort")):
            return e
    return None


def draft_section(
    section_title: str,
    rfp_data: dict,
    section_checklist: list[dict],
    evidence_by_checklist: dict[str, list[dict]],
    *,
    all_supported_evidence_ids: list[str] | None = None,
    section_evidence_pool: list[dict] | None = None,
) -> str:
    client = rfp_data.get("client") or "The client"
    pool = section_evidence_pool or []
    para: list[str] = []

    if section_title == "Context & Problem Understanding":
        para.append(f"{client}")
        if rfp_data.get("problem_statement"):
            para.append(
                "As described in the RFP, "
                + rfp_data["problem_statement"].split("\n")[0].strip()
            )
        if rfp_data.get("timeline"):
            para.append(f"The engagement is time-boxed: {rfp_data['timeline'].rstrip('.')}.")
        para.append(
            "We have read the RFP in full and our understanding of the objectives "
            "is reflected in the sections that follow."
        )

    elif section_title == "Proposed Approach & Workplan":
        para.append(
            "We propose a phased engagement structured as Diagnose, Design, Pilot, "
            "and Scale, reaching a measured pilot within the stated timeline. [[ev:METHOD_001]]"
        )
        para.append(
            "During weeks 1 to 3 the team will map the end-to-end process, quantify "
            "delay at each step, and establish a matched baseline."
        )
        para.append(
            "In weeks 4 to 7 we will redesign the workflow and operating model; in "
            "weeks 8 to 11 we will run the controlled pilot; in week 12 we will "
            "produce a scale recommendation."
        )
        for item in section_checklist:
            if item["handling"] in ("NEEDS_EVIDENCE", "TEMPLATE_SATISFIABLE"):
                continue

    elif section_title == "Team & Credentials":
        if any(i["handling"] == "NEEDS_HUMAN_INPUT" for i in section_checklist):
            para.append(
                "**HUMAN INPUT REQUIRED:** the named team and individual time "
                "commitments are confirmed by the engagement partner and are not "
                "drafted by the agent."
            )
        team_rid = ""
        for it in section_checklist:
            if "team" in it["requirement_text"].lower() or "named" in it["requirement_text"].lower():
                team_rid = f" [[req:{it['checklist_id']}]]"
                break
        cv1 = _pool_by_source(pool, "CV_001", keyword="18 years")
        cv2 = _pool_by_source(pool, "CV_002", keyword="12 years")
        if cv1:
            para.append(
                "Ananya Mehta, Partner, has 18 years of experience in banking and "
                f"lending operations. [[ev:{cv1['evidence_id']}]]{team_rid}"
            )
        if cv2:
            para.append(
                "Rohan Sen, Principal, has 12 years of experience in SME lending "
                f"and underwriting. [[ev:{cv2['evidence_id']}]]{team_rid}"
            )
        if not (cv1 or cv2):
            para.append("[EVIDENCE GAP: no team CVs selected as evidence]")

    elif section_title == "Relevant Experience & Credentials":
        metric_case = _pool_metric_case(pool)
        emitted_grounded = False
        for item in section_checklist:
            rid = f" [[req:{item['checklist_id']}]]"
            ev = evidence_by_checklist.get(item["checklist_id"], [])
            pool_ev = ev + [e for e in pool if e["source_id"] in {x["source_id"] for x in ev}]
            pct = _threshold_pct(item["requirement_text"])
            if pct is not None and not _evidence_supports_threshold(pool_ev, pct):
                # PLANTED OVERCLAIM -- no citation, corpus cannot support >30% TAT.
                # This is the hero GAP row (SPEC Section 1).
                para.append(
                    "In a comparable lending engagement, VCG reduced lending "
                    f"turnaround time by 35 percent.{rid}"
                )
                continue
            if metric_case is not None and not emitted_grounded and (
                "experience" in item["requirement_text"].lower()
                or "measurable" in item["requirement_text"].lower()
                or "results" in item["requirement_text"].lower()
            ):
                # grounded compound claim -> decomposed + each part verified vs
                # the exact cited chunk.
                para.append(
                    "In a retail lending operations redesign for a large Indian "
                    "bank, VCG reduced pilot approval turnaround time by 18 percent "
                    "and reduced manual handoffs by 30 percent. "
                    f"[[ev:{metric_case['evidence_id']}]]{rid}"
                )
                emitted_grounded = True
                continue
            if ev:
                top = ev[0]
                para.append(
                    f"VCG has relevant delivery experience: {top['title']}. "
                    f"[[ev:{top['evidence_id']}]]{rid}"
                )
            else:
                para.append(f"[EVIDENCE GAP: {item['evidence_need']}]")

    elif section_title == "Risks & Mitigations":
        para.append(
            "We propose to manage three delivery risks: data availability for "
            "baselining, branch change fatigue during the pilot, and credit-risk "
            "appetite for auto-decisioning."
        )
        para.append(
            "For each, mitigations are agreed with the client at mobilisation and "
            "tracked weekly."
        )

    elif section_title == "Commercial":
        para.append(
            "**HUMAN INPUT REQUIRED:** commercial terms, fees, and the payment "
            "schedule are set by the engagement partner and are never drafted by "
            "the agent."
        )

    elif section_title == "Executive Summary":
        para.append(
            f"{client} has asked for a partner to deliver the transformation "
            "described in the RFP within the stated timeline."
        )
        para.append(
            "We propose a phased approach that reaches a measured pilot within the "
            "timeline, staffed by an experienced team."
        )
        case = _pool_by_source(pool, "CASE_BANK_001") or _pool_metric_case(pool)
        if case:
            para.append(
                "VCG has delivered comparable retail lending redesigns, including a "
                f"measured branch pilot for a large Indian bank. [[ev:{case['evidence_id']}]]"
            )

    body = "\n\n".join(p if p.endswith((".", ":", "]")) else p + "." for p in para if p)
    return body or "[EVIDENCE GAP: no content generated for this section]"


# --------------------------------------------------------------------------- #
# 4. Claim decomposition
# --------------------------------------------------------------------------- #
_CITE_RE = re.compile(r"\[\[ev:([A-Za-z0-9_\-:.]+)\]\]")
_REQ_RE = re.compile(r"\[\[req:([A-Za-z0-9_\-]+)\]\]")
_TAG_RE = re.compile(r"\[\[(?:ev|req):[A-Za-z0-9_\-:.]+\]\]")
# past-tense VCG achievement verbs -- only these (plus a number or a named person)
# make a sentence a historical claim that must be verified. Framing sentences
# ("we have read the RFP", "we propose...") are not historical claims.
_ACHIEVEMENT_RE = re.compile(
    r"\b(reduced|redesigned|delivered|led|cut|improved|achieved|built|advised|"
    r"has\s+\d+\s+years|reducing|redesigning)\b",
    re.I,
)


def _claim_type(frag: str, prospective: bool, numeric: list[str], entities: list[str]) -> str:
    if prospective:
        return "PROPOSED_ACTION"
    if numeric:
        return "NUMERIC"
    low = frag.lower()
    if any(k in low for k in ("experience", "has delivered", "delivered", "redesigned",
                              "has 1", "years of")):
        return "EXPERIENCE"
    if any(k in low for k in ("methodology", "phased", "framework")):
        return "METHODOLOGY"
    if entities:
        return "FACTUAL"
    return "FACTUAL"


def decompose_claims(section_title: str, section_markdown: str) -> list[dict]:
    out: list[dict] = []
    n = 0
    for sent in sentences(section_markdown):
        if sent.lstrip().startswith("[EVIDENCE GAP") or "HUMAN INPUT REQUIRED" in sent:
            continue
        cites = _CITE_RE.findall(sent)
        req_ids = _REQ_RE.findall(sent)
        clean_sent = _TAG_RE.sub("", sent).strip()
        for frag in split_compound(clean_sent):
            frag = frag.strip()
            if len(frag) < 8:
                continue
            n += 1
            prospective = is_prospective(frag)
            numeric = [t.raw for t in extract_numeric_tokens(frag)]
            entities = extract_named_entities(frag)
            quals = extract_context_qualifiers(frag)
            low = frag.lower()
            achievement = bool(_ACHIEVEMENT_RE.search(frag))
            # a historical (verifiable) claim = a VCG/person achievement, or a
            # named person tied to a number. A bare number that just restates the
            # RFP ("delivered within 12 weeks") is framing, not a claim.
            historical = (
                (achievement and ("vcg" in low or numeric or entities))
                or (bool(entities) and bool(numeric))
            )
            requires_verification = bool(historical and not prospective)
            out.append(
                {
                    "claim_id": f"CLM-{section_title[:3].upper()}-{n:03d}",
                    "section_name": section_title,
                    "claim_text": frag,
                    "claim_type": _claim_type(frag, prospective, numeric, entities),
                    "source_checklist_id": req_ids[0] if req_ids else None,
                    "cited_evidence_ids": list(dict.fromkeys(cites)),
                    "numeric_tokens": numeric,
                    "named_entities": entities,
                    "context_qualifiers": quals,
                    "requires_verification": requires_verification,
                }
            )
    return out
