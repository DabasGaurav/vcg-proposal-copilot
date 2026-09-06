"""Seed the vector KB from data/corpus/*.md.

    python scripts/seed_corpus.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from services.corpus_loader import chunk_documents, load_documents  # noqa: E402
from services.vectorstore import VectorStore  # noqa: E402


def main() -> int:
    config.ensure_dirs()
    docs = load_documents()
    if len(docs) != 10:
        print(f"WARNING: expected 10 corpus docs, found {len(docs)} "
              f"({[d.document_id for d in docs]})")
    chunks = chunk_documents(docs)
    store = VectorStore.build(chunks)
    path = store.save()

    per_doc = Counter(c.document_id for c in chunks)
    print(f"Loaded {len(docs)} documents, {len(chunks)} chunks "
          f"(embedder backend: {store.embedder.backend}, dim {store.embedder.dim})")
    for doc in docs:
        print(f"  {doc.document_id:<16} {per_doc[doc.document_id]:>2} chunks  "
              f"[{doc.metadata.get('industry')}/{doc.metadata.get('subsector')}/"
              f"{doc.metadata.get('region')}]")
    print(f"Saved vector store -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
