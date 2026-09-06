from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_storage(tmp_path_factory):
    """Point SQLite + the vector store at a throwaway dir; seed the KB once."""
    tmp = tmp_path_factory.mktemp("vcg")
    config.DATA_DIR = tmp
    config.VECTORSTORE_PATH = tmp / "vectorstore"
    config.DB_PATH = tmp / "db.sqlite"
    config.ensure_dirs()

    from services import persistence
    persistence._default = None  # force a fresh Store on the tmp path

    from services.vectorstore import VectorStore
    VectorStore.build().save(config.VECTORSTORE_PATH)
    yield


@pytest.fixture(scope="session")
def store():
    from services.vectorstore import VectorStore
    return VectorStore.load(config.VECTORSTORE_PATH)


@pytest.fixture(scope="session")
def semantic_fn(store):
    return store.semantic_similarity


@pytest.fixture
def abc_state():
    """Full pipeline run on the happy-path fixture (no web, no persistence)."""
    from pipeline.graph import run_pipeline
    return run_pipeline(
        str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
        web_search=False, persist=False,
    )


def make_claim(**kw):
    from models.schemas import AtomicClaim, ClaimType
    base = dict(
        claim_id="CLM-T-001", section_name="Relevant Experience & Credentials",
        claim_text="", claim_type=ClaimType.NUMERIC, cited_evidence_ids=[],
        numeric_tokens=[], named_entities=[], context_qualifiers=[],
        requires_verification=True,
    )
    base.update(kw)
    return AtomicClaim(**base)


def make_evidence(source_id: str, chunk_text: str, **kw):
    from models.schemas import EvidenceCategory, EvidenceItem
    base = dict(
        evidence_id=f"E::{source_id}", source_id=source_id, title=source_id,
        category=EvidenceCategory.CASE_STUDY, chunk_id=f"{source_id}::00.00",
        chunk_text=chunk_text, source_path="mem", relevance_score=0.5, selected=True,
        metadata={},
    )
    base.update(kw)
    return EvidenceItem(**base)
