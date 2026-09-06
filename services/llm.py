"""LLM access.

Two providers:

* ``mock`` (default) -- deterministic, fixture-aware. Lets the whole pipeline,
  the demo, and the tests run fully offline. The mock is intentionally *not*
  smart: it does structural parsing and a couple of planted behaviours (notably
  the >30%% -> "35%%" overclaim) so the deterministic verifier has something real
  to catch.
* ``litellm`` -- routes real calls through LiteLLM using LLM_MODEL from .env.
  Import-guarded; only used when explicitly configured.

Only these four operations are ever delegated to an LLM (SPEC Section 5 design
principle): interpret/extract, plan, draft, decompose-claims. The LLM is never
asked "is this claim true".
"""
from __future__ import annotations

import re

import config

_BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$", re.M)
_H2 = re.compile(r"^##\s+(.*)$", re.M)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

PROSPECTIVE_MARKERS = (
    "we propose", "we will", "the team will", "in weeks", "during weeks",
    "week 1", "weeks 1", "our approach will", "we intend", "we would",
    "must be", "must submit", "is time-boxed", "will be delivered",
)


# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #
class LLM:
    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.LLM_MODEL

    # -- delegated operations (SPEC Section 5) --------------------------
    # interpret/extract, plan, draft, decompose-claims. Never "is this true?".
    def extract_requirements(self, rfp_text: str, filename: str = "") -> dict:
        if self.provider == "mock":
            from services import mock_llm
            return mock_llm.extract_requirements(rfp_text, filename)
        from services import real_llm
        return real_llm.extract_requirements(rfp_text, filename, complete=self.complete)

    def plan_response(self, rfp_data: dict) -> dict:
        if self.provider == "mock":
            from services import mock_llm
            return mock_llm.plan_response(rfp_data)
        from services import real_llm
        return real_llm.plan_response(rfp_data, complete=self.complete)

    def draft_section(self, section_title: str, rfp_data: dict,
                      section_checklist: list[dict],
                      evidence_by_checklist: dict[str, list[dict]],
                      *, all_supported_evidence_ids: list[str] | None = None,
                      section_evidence_pool: list[dict] | None = None) -> str:
        if self.provider == "mock":
            from services import mock_llm
            return mock_llm.draft_section(
                section_title, rfp_data, section_checklist, evidence_by_checklist,
                all_supported_evidence_ids=all_supported_evidence_ids,
                section_evidence_pool=section_evidence_pool or [],
            )
        from services import real_llm
        return real_llm.draft_section(
            section_title, rfp_data, section_checklist, evidence_by_checklist,
            all_supported_evidence_ids=all_supported_evidence_ids,
            section_evidence_pool=section_evidence_pool or [], complete=self.complete,
        )

    def decompose_claims(self, section_title: str, section_markdown: str) -> list[dict]:
        if self.provider == "mock":
            from services import mock_llm
            return mock_llm.decompose_claims(section_title, section_markdown)
        from services import real_llm
        return real_llm.decompose_claims(section_title, section_markdown, complete=self.complete)

    # -- generic completion transport (real provider) ------------------
    def complete(self, system: str, user: str) -> str:
        if self.provider != "litellm":
            raise RuntimeError(
                "LLM.complete() requires LLM_PROVIDER=litellm; the mock provider "
                "uses the structured helpers instead."
            )
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "LLM_PROVIDER=litellm but the 'litellm' package is not installed "
                "(pip install litellm)."
            ) from exc
        resp = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return resp["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------- #
# Structural parsing helpers (shared by mock + used to pre-parse for real LLM)
# --------------------------------------------------------------------------- #
def parse_sections(md: str) -> dict[str, str]:
    out: dict[str, str] = {}
    matches = list(_H2.finditer(md))
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        out[name.lower()] = md[start:end].strip()
    return out


def bullets(block: str) -> list[str]:
    return [b.strip() for b in _BULLET.findall(block)]


_LEADING_VERB = re.compile(
    r"^(?:to\s+)?(demonstrat\w*|provid\w*|redesign\w*|diagnos\w*|defin\w*|produc\w*|"
    r"quantif\w*|deliver\w*|reduc\w*|built|build|led|advis\w*|improv\w*|align\w*|"
    r"recommend\w*|assess\w*|prototyp\w*|design\w*|run|establish\w*|map)\b",
    re.I,
)


def split_compound(text: str) -> list[str]:
    """SPEC Section 8.2 / Section 14 -- split a compound requirement/claim.

    Deliberately conservative: only split a real enumeration -- clauses joined by
    ';' or by ', and '/', ' -- where each fragment begins with its own action
    verb or carries its own number. Never split a bare 'X and Y' noun pair such
    as 'credit policy and governance'.
    """
    parts = re.split(r"\s*;\s+|\s*,\s+and\s+|\s*,\s+(?=[a-z])", text.strip())
    parts = [p.strip(" .") for p in parts if p.strip(" .")]
    if len(parts) < 2:
        return [text.strip()]

    def standalone(frag: str) -> bool:
        f = frag.strip()
        if len(f) < 15:
            return False
        return bool(_LEADING_VERB.match(f)) or bool(re.search(r"\d", f))

    if all(standalone(p) for p in parts):
        return [p if p.endswith(".") else p + "." for p in parts]
    return [text.strip()]


def is_prospective(text: str) -> bool:
    low = text.lower()
    return any(mk in low for mk in PROSPECTIVE_MARKERS)


def sentences(text: str) -> list[str]:
    clean = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.M)  # drop headings
    out: list[str] = []
    for chunk in clean.split("\n"):
        chunk = chunk.strip().lstrip("-*").strip()
        if not chunk:
            continue
        out.extend(s.strip() for s in _SENT_SPLIT.split(chunk) if s.strip())
    return out


def get_llm() -> LLM:
    return LLM()
