"""Stage: intake. Read an RFP (Markdown / text / PDF) into raw text.

Scanned PDFs (no extractable text layer) produce a clear error, never a guess
(SPEC Section 3 non-goal: no OCR in v1).
"""
from __future__ import annotations

from pathlib import Path

from state.graph_state import ProposalAgentState


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"pypdf not available to read {path.name}: {exc}") from exc
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if len(text.strip()) < 40:
        raise ValueError(
            f"{path.name} has no extractable text layer -- looks like a scanned "
            f"PDF. OCR is out of scope for v1; supply a text or Markdown RFP."
        )
    return text


def run(state: ProposalAgentState) -> ProposalAgentState:
    path = Path(state["rfp_path"])
    if not path.exists():
        raise FileNotFoundError(f"RFP not found: {path}")
    state["rfp_filename"] = path.name
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        state["rfp_raw_text"] = path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        state["rfp_raw_text"] = _read_pdf(path)
    else:
        raise ValueError(f"Unsupported RFP type: {suffix} (use .md, .txt, or .pdf)")
    state["language"] = "en"
    state["execution_log"].append(
        {"stage": "intake", "status": "ok",
         "detail": f"{path.name}: {len(state['rfp_raw_text'])} chars"}
    )
    return state
