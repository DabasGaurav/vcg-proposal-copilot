"""Load the synthetic KB, parse metadata, and chunk on Markdown headings.

SPEC Section 9 (metadata) and Section 11 (chunk on headings, ~700 chars, 100
overlap, preserve heading context + source_path).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import config

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)


@dataclass
class CorpusDoc:
    document_id: str
    path: str
    title: str
    body: str
    metadata: dict


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source_path: str
    heading_path: str
    text: str
    metadata: dict = field(default_factory=dict)


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    m = _FRONTMATTER.match(raw)
    if not m:
        return {}, raw
    meta: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if value == "none":
            value = None
        meta[key.strip()] = value
    return meta, raw[m.end():]


def load_documents(corpus_dir: Path | None = None) -> list[CorpusDoc]:
    corpus_dir = corpus_dir or config.CORPUS_DIR
    docs: list[CorpusDoc] = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        doc_id = meta.get("document_id") or path.stem
        first_heading = _HEADING.search(body)
        title = first_heading.group(2).strip() if first_heading else path.stem
        meta.setdefault("document_id", doc_id)
        docs.append(CorpusDoc(document_id=doc_id, path=str(path), title=title,
                              body=body, metadata=meta))
    return docs


def _split_on_headings(body: str) -> list[tuple[str, str]]:
    """Return (heading_path, section_text) preserving heading context."""
    matches = list(_HEADING.finditer(body))
    if not matches:
        return [("", body.strip())]
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        heading_path = " > ".join(h for _, h in stack)
        if text:
            sections.append((heading_path, text))
    return sections


def _window(text: str, target: int, overlap: int) -> list[str]:
    if len(text) <= target:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target)
        # try not to cut mid-sentence
        if end < len(text):
            nl = text.rfind(". ", start + int(target * 0.6), end)
            if nl != -1:
                end = nl + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def chunk_documents(
    docs: list[CorpusDoc] | None = None,
    *,
    target: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    docs = docs if docs is not None else load_documents()
    target = target or config.CHUNK_TARGET_CHARS
    overlap = overlap or config.CHUNK_OVERLAP_CHARS
    chunks: list[Chunk] = []
    for doc in docs:
        for s_idx, (heading_path, section_text) in enumerate(_split_on_headings(doc.body)):
            for w_idx, piece in enumerate(_window(section_text, target, overlap)):
                cid = f"{doc.document_id}::{s_idx:02d}.{w_idx:02d}"
                prefixed = f"[{doc.title} — {heading_path}]\n{piece}" if heading_path else piece
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        document_id=doc.document_id,
                        source_path=doc.path,
                        heading_path=heading_path,
                        text=piece,
                        metadata={
                            **doc.metadata,
                            "title": doc.title,
                            "heading_path": heading_path,
                            "embed_text": prefixed,
                        },
                    )
                )
    return chunks
