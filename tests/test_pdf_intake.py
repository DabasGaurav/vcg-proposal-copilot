"""Phase 1 -- PDF RFP intake against a real generated PDF.

Scanned-PDF (no text layer) must raise a clear error, never guess (SPEC Section 3).
"""
from __future__ import annotations

import textwrap

import pytest

import config
from pipeline import extraction, intake
from state.graph_state import new_state

fpdf = pytest.importorskip("fpdf")


def _make_pdf(path, text: str) -> None:
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_font("Helvetica", size=11)
    for raw in text.encode("ascii", "replace").decode().splitlines():
        for line in (textwrap.wrap(raw, 80, break_long_words=True) or [" "]):
            pdf.multi_cell(w=170, h=6, text=line)
    pdf.output(str(path))


def _make_imageonly_pdf(path) -> None:
    pdf = fpdf.FPDF()
    pdf.add_page()  # blank page, no text objects
    pdf.output(str(path))


def test_reads_a_real_text_pdf(tmp_path):
    src = (config.FIXTURE_DIR / "abc_bank_lending_transformation.md").read_text()
    pdf_path = tmp_path / "abc.pdf"
    _make_pdf(pdf_path, src)

    st = new_state(run_id="t", rfp_path=str(pdf_path))
    st = intake.run(st)
    assert "Evaluation Criteria" in st["rfp_raw_text"]
    assert st["rfp_filename"] == "abc.pdf"

    st = extraction.run(st)
    assert st["rfp_data"].requirements
    assert any("turnaround" in r.text.lower() for r in st["rfp_data"].requirements)


def test_scanned_pdf_raises_clear_error(tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    _make_imageonly_pdf(pdf_path)
    st = new_state(run_id="t", rfp_path=str(pdf_path))
    with pytest.raises(ValueError, match="scanned"):
        intake.run(st)
