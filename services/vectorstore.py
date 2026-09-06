"""Local persistent vector store over the chunked KB.

Default backend is a numpy matrix persisted with pickle -- no external service,
works offline (SPEC Section 0). A ChromaDB backend can be swapped in via
VECTORSTORE_BACKEND=chroma without touching callers.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import config
from services.corpus_loader import Chunk, chunk_documents
from services.embeddings import Embedder
from services.text import lexical_overlap


@dataclass
class Hit:
    chunk_id: str
    document_id: str
    text: str
    source_path: str
    metadata: dict
    semantic_score: float
    lexical_score: float


class VectorStore:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self._ids: list[str] = []
        self._chunks: list[Chunk] = []
        self._matrix: np.ndarray | None = None

    # -- build / persist --------------------------------------------------
    @classmethod
    def build(cls, chunks: list[Chunk] | None = None) -> "VectorStore":
        chunks = chunks if chunks is not None else chunk_documents()
        corpus_texts = [c.metadata.get("embed_text", c.text) for c in chunks]
        embedder = Embedder().fit(corpus_texts)
        store = cls(embedder)
        store._chunks = list(chunks)
        store._ids = [c.chunk_id for c in chunks]
        store._matrix = embedder.encode(corpus_texts)
        return store

    def save(self, path: Path | None = None) -> Path:
        path = Path(path or config.VECTORSTORE_PATH) / "store.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(
                {
                    "ids": self._ids,
                    "chunks": self._chunks,
                    "matrix": self._matrix,
                    "embedder_state": self.embedder.state(),
                },
                fh,
            )
        return path

    @classmethod
    def ensure_seeded(cls, path: Path | None = None) -> "VectorStore":
        """Load the vector store, building + persisting it first if absent.

        Lets a zero-setup host (Streamlit Community Cloud) come up without a
        manual `python scripts/seed_corpus.py` step.
        """
        path = Path(path or config.VECTORSTORE_PATH)
        if not (path / "store.pkl").exists():
            config.ensure_dirs()
            cls.build().save(path)
        return cls.load(path)

    @classmethod
    def load(cls, path: Path | None = None) -> "VectorStore":
        path = Path(path or config.VECTORSTORE_PATH) / "store.pkl"
        if not path.exists():
            raise FileNotFoundError(
                f"No vector store at {path}. Run: python scripts/seed_corpus.py"
            )
        with open(path, "rb") as fh:
            data = pickle.load(fh)
        store = cls(Embedder.from_state(data["embedder_state"]))
        store._ids = data["ids"]
        store._chunks = data["chunks"]
        store._matrix = data["matrix"]
        return store

    # -- query ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._ids)

    @property
    def chunks(self) -> list[Chunk]:
        return self._chunks

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        try:
            return self._chunks[self._ids.index(chunk_id)]
        except ValueError:
            return None

    def search(self, query: str, k: int | None = None) -> list[Hit]:
        k = k or config.RETRIEVAL_TOP_K
        if self._matrix is None or len(self._ids) == 0:
            return []
        qv = self.embedder.encode_one(query)
        sims = self._matrix @ qv
        order = np.argsort(-sims)[: max(k * 3, k)]
        hits: list[Hit] = []
        for idx in order:
            chunk = self._chunks[idx]
            hits.append(
                Hit(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    source_path=chunk.source_path,
                    metadata=chunk.metadata,
                    semantic_score=float(sims[idx]),
                    lexical_score=lexical_overlap(query, chunk.text),
                )
            )
        hits.sort(key=lambda h: h.semantic_score, reverse=True)
        return hits[:k]

    def semantic_similarity(self, text_a: str, text_b: str) -> float:
        va, vb = self.embedder.encode([text_a, text_b])
        return float(np.dot(va, vb))
