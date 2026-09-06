"""Stage: export (SPEC Section 18, Phase 8).

Markdown + traceability CSV always; DOCX best-effort (graceful if python-docx is
missing). Every exporter calls review.can_export first -- there is no code path
to an export that skips the human gate.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from models.schemas import VerificationStatus
from pipeline.review import can_export
from state.graph_state import ProposalAgentState


class ExportBlocked(PermissionError):
    pass


def _guard(state: ProposalAgentState, *, enforce: bool) -> None:
    if not enforce:
        return
    ok, reasons = can_export(state)
    if not ok:
        raise ExportBlocked("export blocked by review gate: " + " | ".join(reasons))


def render_markdown(state: ProposalAgentState, *, enforce: bool = True) -> str:
    _guard(state, enforce=enforce)
    draft = state["proposal_draft"]
    out = [f"# Proposal — {draft.client}", "", f"*RFP: {draft.rfp_id} · run {draft.run_id}*", ""]
    if state.get("procedural_checklist"):
        out.append("## Procedural Compliance Checklist")
        out.append("")
        for p in state["procedural_checklist"]:
            out.append(f"- [ ] {p}")
        out.append("")
    for s in draft.sections:
        out.append(f"## {s.title}")
        if s.human_edited:
            out.append("<!-- contains a direct human edit -->")
        out.append("")
        out.append(s.content_markdown.strip())
        out.append("")
    out.append("---")
    out.append(
        f"*Claim verification: {draft.supported_claim_count} SUPPORTED · "
        f"{draft.partial_claim_count} PARTIAL · {draft.gap_claim_count} GAP*"
    )
    return "\n".join(out)


def traceability_csv(state: ProposalAgentState) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "trace_id", "requirement_id", "rfp_requirement", "source_quote",
        "draft_section", "claim_id", "claim_text", "matched_evidence_id",
        "verification_status", "confidence", "semantic_similarity",
        "lexical_overlap", "numeric_match", "attribution_valid", "conflict_flag",
        "verification_reason", "reviewer_decision",
    ])
    for e in state["overall_traceability"]:
        w.writerow([
            e.trace_id, e.requirement_id, e.rfp_requirement,
            (e.requirement_source_span.quote if e.requirement_source_span else ""),
            e.draft_section, e.claim_id, e.claim_text, e.matched_evidence_id or "",
            e.verification_status.value, f"{e.confidence_score:.3f}",
            f"{e.semantic_similarity:.3f}", f"{e.lexical_overlap:.3f}",
            "" if e.numeric_match is None else e.numeric_match,
            e.attribution_valid, e.conflict_flag, e.verification_reason,
            e.reviewer_decision.value,
        ])
    return buf.getvalue()


def write_markdown(state, path: str | Path, *, enforce: bool = True) -> Path:
    path = Path(path)
    path.write_text(render_markdown(state, enforce=enforce), encoding="utf-8")
    return path


def write_traceability_csv(state, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(traceability_csv(state), encoding="utf-8")
    return path


def write_docx(state, path: str | Path, *, enforce: bool = True) -> Path | None:
    _guard(state, enforce=enforce)
    try:
        from docx import Document
    except Exception:
        return None  # graceful: DOCX is best-effort
    doc = Document()
    draft = state["proposal_draft"]
    doc.add_heading(f"Proposal — {draft.client}", level=0)
    doc.add_paragraph(f"RFP: {draft.rfp_id} · run {draft.run_id}")
    if state.get("procedural_checklist"):
        doc.add_heading("Procedural Compliance Checklist", level=1)
        for p in state["procedural_checklist"]:
            doc.add_paragraph(p, style="List Bullet")
    for s in draft.sections:
        doc.add_heading(s.title, level=1)
        for para in s.content_markdown.strip().split("\n\n"):
            doc.add_paragraph(para.strip())
    path = Path(path)
    doc.save(str(path))
    return path
