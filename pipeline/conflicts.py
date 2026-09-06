"""Stage: detect_conflicts (SPEC Section 11).

Runs before drafting. Surfaces -- never resolves -- three conflict types:
  * numeric_mismatch  -- same metric family, same-ish context, different numbers
  * attribution_mismatch -- same named person, different tenure
  * superseded  -- a document flagged superseded_by another that is also present

Any conflict => EvidenceConflict(requires_human_resolution=True). A conflicting
claim can never auto-resolve to SUPPORTED (enforced in verification.py).
"""
from __future__ import annotations

import re

from models.schemas import EvidenceConflict
from services.text import extract_numeric_tokens
from state.graph_state import ProposalAgentState

_TENURE_RE = re.compile(r"(\d+)\s*years?", re.I)
_METRIC_KEYWORDS = ("turnaround", "tat", "handoff", "processing effort", "rework",
                     "forecast accuracy", "electricity")


def _all_selected(state: ProposalAgentState) -> list:
    out = []
    seen = set()
    for evs in state["selected_evidence"].values():
        for ev in evs:
            key = ev.chunk_id
            if key not in seen:
                seen.add(key)
                out.append(ev)
    return out


def run(state: ProposalAgentState) -> ProposalAgentState:
    evs = _all_selected(state)
    conflicts: list[EvidenceConflict] = []
    cid = 0

    # superseded
    present_docs = {e.source_id for e in evs}
    for e in evs:
        if e.superseded_by and e.superseded_by in present_docs:
            cid += 1
            conflicts.append(EvidenceConflict(
                conflict_id=f"CONF-{cid:03d}",
                evidence_ids=[e.evidence_id],
                conflict_type="superseded",
                description=f"{e.source_id} is superseded by {e.superseded_by}, "
                            f"which is also in the evidence set.",
            ))

    # attribution: same person, different tenure
    by_person: dict[str, set[str]] = {}
    for e in evs:
        for m in re.finditer(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", e.chunk_text):
            person = m.group(1)
            for t in _TENURE_RE.findall(e.chunk_text):
                by_person.setdefault(person, set()).add(t)
    for person, tenures in by_person.items():
        if len(tenures) > 1:
            cid += 1
            conflicts.append(EvidenceConflict(
                conflict_id=f"CONF-{cid:03d}",
                evidence_ids=[e.evidence_id for e in evs
                              if person in e.chunk_text],
                conflict_type="attribution_mismatch",
                description=f"{person} appears with differing tenure values: "
                            f"{sorted(tenures)} years.",
            ))

    # numeric: same metric keyword, same engagement/doc-pair, differing numbers
    for i in range(len(evs)):
        for j in range(i + 1, len(evs)):
            a, b = evs[i], evs[j]
            if a.source_id == b.source_id:
                continue
            for kw in _METRIC_KEYWORDS:
                if kw in a.chunk_text.lower() and kw in b.chunk_text.lower():
                    na = {t.value for t in extract_numeric_tokens(a.chunk_text)
                          if t.canonical_unit() == "percent"}
                    nb = {t.value for t in extract_numeric_tokens(b.chunk_text)
                          if t.canonical_unit() == "percent"}
                    if na and nb and na.isdisjoint(nb) and (
                        a.metadata.get("subsector") == b.metadata.get("subsector")
                    ):
                        cid += 1
                        conflicts.append(EvidenceConflict(
                            conflict_id=f"CONF-{cid:03d}",
                            evidence_ids=[a.evidence_id, b.evidence_id],
                            conflict_type="numeric_mismatch",
                            description=f"'{kw}': {a.source_id} reports {sorted(na)}%, "
                                        f"{b.source_id} reports {sorted(nb)}%.",
                        ))
                        break

    for ev in evs:
        if any(ev.evidence_id in c.evidence_ids for c in conflicts):
            ev.conflict_flag = True

    state["evidence_conflicts"] = conflicts
    state["execution_log"].append(
        {"stage": "detect_conflicts", "status": "ok",
         "detail": f"{len(conflicts)} conflict(s) surfaced for human resolution"}
    )
    return state
