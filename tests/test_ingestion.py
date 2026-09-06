"""Phase 1 -- corpus + chunking + seeding."""
from __future__ import annotations

import config
from services.corpus_loader import chunk_documents, load_documents


def test_exactly_ten_corpus_documents():
    docs = load_documents()
    ids = sorted(d.document_id for d in docs)
    assert len(ids) == 10
    assert set(ids) == {
        "CASE_BANK_001", "CASE_BANK_002", "CASE_SC_001", "METHOD_001", "METHOD_002",
        "CV_001", "CV_002", "PROP_001", "PROP_002", "DISTRACTOR_001",
    }


def test_every_document_carries_required_metadata():
    required = {"document_id", "category", "industry", "subsector", "region",
                "year", "freshness_date", "usage_restriction"}
    for doc in load_documents():
        assert required <= set(doc.metadata), doc.document_id


def test_case_bank_001_never_mentions_35():
    doc = next(d for d in load_documents() if d.document_id == "CASE_BANK_001")
    assert "35" not in doc.body


def test_chunks_preserve_source_path_and_heading():
    chunks = chunk_documents()
    assert chunks
    for c in chunks[:5]:
        assert c.source_path.endswith(".md")
        assert "heading_path" in c.metadata


def test_required_rfp_fixtures_exist():
    fixtures = {p.name for p in config.FIXTURE_DIR.glob("*.md")}
    required = {
        "abc_bank_lending_transformation.md",   # happy path + hero moment
        "xyz_insurer_actuarial_ai.md",          # capability gap
        "pqr_bank_procurement_heavy.md",        # procedural heavy
    }
    assert required <= fixtures
