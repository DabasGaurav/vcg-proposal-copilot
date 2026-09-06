"""Web search providers for optional client/industry background (SPEC Section 12).

Providers: ``mock`` (default, offline), ``tavily`` (needs TAVILY_API_KEY),
``ddg`` (needs the ``duckduckgo_search`` package). All are import/So key-guarded
and degrade to an empty list rather than raising -- the core demo must run with
web disabled.

Nothing returned here ever becomes citable VCG evidence: the caller keeps it out
of the evidence pool and only uses it for context framing, after the
VCG-credential guardrail below strips anything that reads like a firm claim.
"""
from __future__ import annotations

import os

import config

_VCG_CLAIM_MARKERS = (
    "vcg ", "our experience", "we delivered", "we reduced", "our methodology",
    "our team", "our clients", "case study", "proprietary",
)


def _guardrail(results: list[dict]) -> list[dict]:
    safe = []
    for r in results:
        blob = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
        if any(m in blob for m in _VCG_CLAIM_MARKERS):
            continue                      # never let the web assert a VCG credential
        safe.append(r)
    return safe


def _mock(query: str, k: int) -> list[dict]:
    return [{
        "title": f"Sector background — {query[:60]}",
        "snippet": ("Neutral public context on the sector and typical "
                    "transformation drivers. Background only; no firm-specific "
                    "claims."),
        "url": "mock://industry-background",
        "provider": "mock",
    }]


def _tavily(query: str, k: int) -> list[dict]:  # pragma: no cover - needs key+net
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    try:
        from tavily import TavilyClient
    except ImportError:
        return []
    try:
        resp = TavilyClient(api_key=key).search(query=query, max_results=k,
                                                search_depth="basic")
        return [{"title": r.get("title", ""), "snippet": r.get("content", ""),
                 "url": r.get("url", ""), "provider": "tavily"}
                for r in resp.get("results", [])]
    except Exception:
        return []


def _ddg(query: str, k: int) -> list[dict]:  # pragma: no cover - needs pkg+net
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []
    try:
        with DDGS() as ddgs:
            return [{"title": r.get("title", ""), "snippet": r.get("body", ""),
                     "url": r.get("href", ""), "provider": "ddg"}
                    for r in list(ddgs.text(query, max_results=k))]
    except Exception:
        return []


_PROVIDERS = {"mock": _mock, "tavily": _tavily, "ddg": _ddg}


def search(query: str, *, k: int = 4, provider: str | None = None) -> list[dict]:
    provider = provider or config.WEB_SEARCH_PROVIDER
    fn = _PROVIDERS.get(provider, _mock)
    return _guardrail(fn(query, k))
