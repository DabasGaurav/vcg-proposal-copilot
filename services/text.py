"""Shared deterministic text utilities.

Used by requirement source-span validation (SPEC Section 8) and by the
deterministic verifier (SPEC Section 15). Nothing here calls an LLM.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w%.\-/$ ]+")

# Common English stop-words -- kept small on purpose; lexical overlap is meant to
# reward shared *significant* tokens.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on",
    "for", "with", "by", "at", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "from", "into",
    "we", "our", "us", "their", "they", "will", "has", "have", "had", "not",
    "per", "over", "than", "which", "who", "whom", "was", "during",
}


def normalize(text: str) -> str:
    """Lowercase, strip most punctuation, collapse whitespace. Deterministic."""
    if not text:
        return ""
    t = text.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    t = _PUNCT.sub(" ", t)
    t = _WS.sub(" ", t)
    return t.strip()


def tokens(text: str) -> list[str]:
    return [w for w in normalize(text).split(" ") if w]


def significant_tokens(text: str) -> list[str]:
    return [w for w in tokens(text) if w not in STOPWORDS and len(w) > 2]


def lexical_overlap(claim_text: str, evidence_text: str) -> float:
    """Jaccard-style overlap on significant tokens, asymmetric toward the claim:
    fraction of the claim's significant tokens that also appear in the evidence.
    """
    c = set(significant_tokens(claim_text))
    e = set(significant_tokens(evidence_text))
    if not c:
        return 0.0
    return len(c & e) / len(c)


def is_locatable(quote: str, haystack: str, *, min_ratio: float = 0.82) -> bool:
    """Anti-hallucination gate (SPEC Section 8 step 3).

    True if the normalized quote is a substring of the normalized haystack, or a
    high-overlap fuzzy match (handles minor extraction paraphrase / ellipsis).
    """
    nq = normalize(quote)
    nh = normalize(haystack)
    if not nq:
        return False
    if nq in nh:
        return True
    q_tokens = nq.split(" ")
    if len(q_tokens) < 4:
        return False
    # sliding-window token overlap
    h_tokens = nh.split(" ")
    win = len(q_tokens)
    q_set = set(q_tokens)
    best = 0.0
    for i in range(0, max(1, len(h_tokens) - win + 1)):
        window = set(h_tokens[i : i + win])
        ratio = len(q_set & window) / len(q_set)
        if ratio > best:
            best = ratio
            if best >= min_ratio:
                return True
    return best >= min_ratio


# --------------------------------------------------------------------------- #
# Numeric tokens (SPEC Section 15 step 5)
# --------------------------------------------------------------------------- #
_NUM_PATTERNS = [
    re.compile(r"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|percentage points|pp)\b", re.I),
    re.compile(r"(?P<cur>[$₹€£])\s*(?P<val>\d+(?:\.\d+)?)\s*(?P<scale>k|m|bn|billion|million|thousand|crore|lakh)?", re.I),
    re.compile(r"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>weeks?|months?|days?|years?)\b", re.I),
    re.compile(r"\b(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>points?|x|percent)\b", re.I),
]


class NumericToken:
    __slots__ = ("value", "unit", "raw", "start", "end")

    def __init__(self, value: float, unit: str, raw: str, start: int, end: int):
        self.value = value
        self.unit = unit
        self.raw = raw
        self.start = start
        self.end = end

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"NumericToken({self.raw!r}, value={self.value}, unit={self.unit!r})"

    def canonical_unit(self) -> str:
        u = self.unit.lower().strip()
        if u in {"%", "percent", "percentage points", "pp", "points", "point"}:
            return "percent"
        if u.startswith("week"):
            return "weeks"
        if u.startswith("month"):
            return "months"
        if u.startswith("day"):
            return "days"
        if u.startswith("year"):
            return "years"
        if u in {"$", "₹", "€", "£"}:
            return "currency"
        return u or "number"


def extract_numeric_tokens(text: str) -> list[NumericToken]:
    out: list[NumericToken] = []
    seen: set[tuple[int, int]] = set()
    for pat in _NUM_PATTERNS:
        for m in pat.finditer(text):
            span = (m.start(), m.end())
            if span in seen:
                continue
            seen.add(span)
            try:
                val = float(m.group("val"))
            except (ValueError, IndexError):
                continue
            unit = ""
            if "unit" in m.groupdict() and m.group("unit"):
                unit = m.group("unit")
            elif "cur" in m.groupdict() and m.group("cur"):
                unit = m.group("cur")
            out.append(NumericToken(val, unit, m.group(0).strip(), m.start(), m.end()))
    out.sort(key=lambda t: t.start)
    return out


def numbers_match(claim_val: float, ev_val: float, *, abs_tol: float = 0.5) -> bool:
    """Rounding-tolerant equality (SPEC Section 15): equal after rounding to the
    claim's precision, or within a small absolute tolerance."""
    if abs(claim_val - ev_val) <= abs_tol:
        return True
    # round to the claim's decimal precision
    claim_str = repr(claim_val)
    decimals = len(claim_str.split(".")[1]) if "." in claim_str else 0
    return round(claim_val, decimals) == round(ev_val, decimals)


def context_window_tokens(text: str, center_start: int, center_end: int, window: int = 20) -> str:
    """Return the +/- ``window`` word context around a character span."""
    before = text[:center_start].split()
    after = text[center_end:].split()
    left = before[-window:]
    right = after[:window]
    center = text[center_start:center_end]
    return " ".join(left + [center] + right)


# --------------------------------------------------------------------------- #
# Lightweight entity extraction (SPEC Section 15 step 6)
# --------------------------------------------------------------------------- #
KNOWN_PEOPLE = {"ananya mehta", "rohan sen"}
ROLE_TERMS = {"partner", "principal", "manager", "associate", "director"}
SECTOR_TERMS = {"banking", "lending", "underwriting", "credit", "insurance", "actuarial",
                "supply chain"}


def extract_named_entities(text: str) -> list[str]:
    """Capitalised multi-word names + known people. Intentionally simple."""
    found: list[str] = []
    low = text.lower()
    for person in KNOWN_PEOPLE:
        if person in low:
            found.append(person.title())
    # generic "Firstname Lastname" capitalised pairs
    for m in re.finditer(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b", text):
        name = f"{m.group(1)} {m.group(2)}"
        if name.lower() not in {"executive summary", "request for", "target operating"}:
            if name not in found:
                found.append(name)
    return found


def extract_context_qualifiers(text: str) -> list[str]:
    """Keyword-extracted where/what-kind qualifiers (SPEC Section 15)."""
    low = normalize(text)
    quals: list[str] = []
    catalog = [
        "india", "indian", "southeast asia", "south asia", "europe", "us",
        "sme", "retail", "consumer", "corporate",
    ]
    for term in catalog:
        if re.search(rf"\b{re.escape(term)}\b", low):
            quals.append(term)
    return quals
