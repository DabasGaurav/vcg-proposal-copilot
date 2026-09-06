"""Embedding backend.

Default: scikit-learn TF-IDF, fit on the seeded corpus -- fully offline, no model
download (SPEC Section 0 known-risk mitigation). Optional:
sentence-transformers/all-MiniLM-L6-v2 if installed and a model is cached.

All vectors are returned L2-normalised so a plain dot product is cosine
similarity.
"""
from __future__ import annotations

import numpy as np

import config


class Embedder:
    def __init__(self, backend: str | None = None, model_name: str | None = None):
        self.backend = backend or config.EMBEDDINGS_BACKEND
        self.model_name = model_name or config.EMBEDDINGS_MODEL
        self._vectorizer = None          # TF-IDF
        self._st_model = None            # sentence-transformers
        self._fitted = False

        if self.backend == "sentence-transformers":
            try:  # pragma: no cover - optional path
                from sentence_transformers import SentenceTransformer

                self._st_model = SentenceTransformer(self.model_name)
                self._fitted = True
            except Exception:
                # graceful fallback -- offline or not installed
                self.backend = "tfidf"

        if self.backend == "tfidf":
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words="english",
                ngram_range=(1, 2),
                min_df=1,
                sublinear_tf=True,
            )

    # -- lifecycle -------------------------------------------------------
    def fit(self, corpus_texts: list[str]) -> "Embedder":
        if self.backend == "tfidf":
            self._vectorizer.fit(corpus_texts)
            self._fitted = True
        return self

    @property
    def fitted(self) -> bool:
        return self._fitted

    # -- encoding ------------------------------------------------------
    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Embedder used before fit(); seed the corpus first.")
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self.backend == "sentence-transformers":  # pragma: no cover - optional
            vecs = np.asarray(self._st_model.encode(texts, normalize_embeddings=True),
                              dtype=np.float32)
            return vecs
        mat = self._vectorizer.transform(texts).toarray().astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    @property
    def dim(self) -> int:
        if self.backend == "sentence-transformers":  # pragma: no cover
            return int(self._st_model.get_sentence_embedding_dimension())
        return len(self._vectorizer.vocabulary_) if self._fitted else 0

    # -- persistence ------------------------------------------------------
    def state(self) -> dict:
        return {
            "backend": self.backend,
            "model_name": self.model_name,
            "vectorizer": self._vectorizer if self.backend == "tfidf" else None,
        }

    @classmethod
    def from_state(cls, state: dict) -> "Embedder":
        emb = cls(backend=state["backend"], model_name=state["model_name"])
        if state["backend"] == "tfidf" and state.get("vectorizer") is not None:
            emb._vectorizer = state["vectorizer"]
            emb._fitted = True
        return emb


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for already-or-not-normalised vectors."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
