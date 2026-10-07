"""Shared deterministic text utilities.

Used by requirement source-span validation (SPEC Section 8) and by the
deterministic verifier (SPEC Section 15). Nothing here calls an LLM.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w%.\-/$ ]+")
# A "." is kept so decimals survive ("18.2"), but a sentence-final period was
# kept too, and it rode along on the token: "percent." never matched the
# stop-word or generic-near-number sets, and "baseline." never matched
# "baseline". That understated lexical overlap in both directions and -- worse --
# left "percent." as a shared token that satisfied the distractor guard on its
# own, so a figure quoted from an unrelated metric passed the context rule. A
# period only survives between two digits. The same applied to a hyphen:
# "turnaround-time" shared nothing with "turnaround time".
_DOT_NOT_DECIMAL = re.compile(r"(?<!\d)\.|\.(?!\d)")
_HYPHEN_IN_WORD = re.compile(r"(?<=[a-z])-(?=[a-z])")

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
    t = _DOT_NOT_DECIMAL.sub(" ", t)
    t = _HYPHEN_IN_WORD.sub(" ", t)
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
# NOTE on the percent pattern: a trailing \b after the alternation silently
# dropped every figure written with the SYMBOL. "%" is a non-word character, so
# \b required a word character after it, which "35%" at a clause end never has.
# The consequence was severe: a claim of "35%" produced NO numeric token, so the
# numeric rule reported "not applicable" and a contradicted figure passed
# verification. The symbol alternative therefore carries no \b.
# A number may be written with thousands separators ("2,500"); matching only
# \d+ truncated it to the leading group, so Rs 2,500 crore and Rs 2,900 crore
# both parsed as the value 2 and compared equal.
_NUMBER = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"

# A figure written in words produced NO numeric token, so the numeric rule
# reported "not applicable" and the claim was judged on similarity alone --
# "reduced turnaround time by thirty-five percent" passed against evidence of
# 18 percent. Same failure as the "%" symbol bug, different spelling.
_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_NUM = re.compile(
    r"\b(?:(?P<tens>" + "|".join(_TENS) + r")(?:[-\s](?P<ones>"
    + "|".join(_ONES) + r"))?|(?P<single>" + "|".join(_ONES) + r"))\b", re.I)


def _word_value(m: re.Match) -> float:
    gd = m.groupdict()
    if gd.get("single"):
        return float(_ONES[gd["single"].lower()])
    total = _TENS[gd["tens"].lower()]
    if gd.get("ones"):
        total += _ONES[gd["ones"].lower()]
    return float(total)


def _digitise_words(text: str) -> str:
    """Rewrite word-numbers as digits, preserving character offsets so the
    context-window rule still points at the right span."""
    out = list(text)
    for m in _WORD_NUM.finditer(text):
        digits = f"{_word_value(m):g}"
        span = m.end() - m.start()
        if len(digits) > span:          # cannot fit; leave it alone
            continue
        repl = digits.rjust(span)       # pad left so end offset is unchanged
        out[m.start():m.end()] = repl
    return "".join(out)

_NUM_PATTERNS = [
    re.compile(rf"(?P<val>{_NUMBER})\s*(?P<unit>percentage points?|percent|pp\b|%)", re.I),
    re.compile(rf"(?P<cur>[$₹€£]|\b(?:rs|inr|usd|eur|gbp)\.?)\s*(?P<val>{_NUMBER})\s*"
               r"(?P<scale>k\b|m\b|bn\b|billion|million|thousand|crore|lakh|lac)?", re.I),
    re.compile(rf"(?P<val>{_NUMBER})\s*(?P<unit>weeks?|months?|days?|years?)\b", re.I),
    re.compile(rf"\b(?P<val>{_NUMBER})\s*(?P<unit>points?|x)\b", re.I),
    # A credential identifier is a number that must match exactly: ISO 27001 and
    # ISO 9001 are different certifications, not a rounding difference.
    re.compile(rf"\b(?P<unit>iso|iec|soc|pci dss|sae|as|en)\s*(?P<val>{_NUMBER})\b", re.I),
    # Bare cardinals. Without these a claim of "240 consultants" against evidence
    # of "24 consultants" produced no token at all, so the numeric rule reported
    # "not applicable" and the claim passed.
    re.compile(rf"\b(?P<val>{_NUMBER})\b"),
]

# Currencies are distinct units, not one "currency" bucket: USD 7 million and
# INR 7 million are not the same amount.
_CUR_CODE = {"$": "usd", "₹": "inr", "€": "eur", "£": "gbp",
             "rs": "inr", "inr": "inr", "usd": "usd", "eur": "eur", "gbp": "gbp"}

# Indian and international scale words, normalised so 5 crore and 5 lakh are not
# treated as the same amount.
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "lakh": 1e5,
          "lac": 1e5, "crore": 1e7, "bn": 1e9, "billion": 1e9}


class NumericToken:
    __slots__ = ("value", "unit", "raw", "start", "end", "scale")

    def __init__(self, value: float, unit: str, raw: str, start: int, end: int,
                 scale: str | None = None):
        self.value = value            # the magnitude as written
        self.unit = unit
        self.raw = raw
        self.start = start
        self.end = end
        self.scale = (scale or "").lower().strip() or None

    @property
    def scaled_value(self) -> float:
        """Magnitude with its scale word applied, so 5 crore != 5 lakh."""
        return self.value * _SCALE.get(self.scale, 1.0)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"NumericToken({self.raw!r}, value={self.value}, unit={self.unit!r})"

    def canonical_unit(self) -> str:
        u = self.unit.lower().strip()
        # "18 percentage points" is not "18 percent": on a 40 percent base one is
        # a 45 percent relative change and the other is 18. Conflating them let a
        # claim of 18 percentage points verify against evidence of 18 percent.
        if u in {"percentage points", "percentage point", "pp", "points", "point"}:
            return "percentage_points"
        if u in {"%", "percent", "percentage"}:
            return "percent"
        if u.startswith("week"):
            return "weeks"
        if u.startswith("month"):
            return "months"
        if u.startswith("day"):
            return "days"
        if u.startswith("year"):
            return "years"
        code = _CUR_CODE.get(u.rstrip("."))
        if code:
            return f"currency:{code}"          # distinct per currency
        if u in {"iso", "iec", "soc", "pci dss", "sae", "as", "en"}:
            return f"credential:{u}"           # must match exactly
        return u or "count"


def extract_numeric_tokens(text: str) -> list[NumericToken]:
    out: list[NumericToken] = []
    claimed: list[tuple[int, int]] = []
    # Offsets are preserved by _digitise_words, so spans still index into ``text``
    # for the context-window and direction checks.
    text = _digitise_words(text)

    def _overlaps(a: int, b: int) -> bool:
        return any(a < end and start < b for start, end in claimed)

    # Patterns run most-specific first; the bare-cardinal pattern at the end must
    # not re-emit digits a richer pattern already consumed, or "18 percent" would
    # yield a percent token AND a bare count for the same figure and the count
    # would then look unmatched.
    for pat in _NUM_PATTERNS:
        for m in pat.finditer(text):
            if _overlaps(m.start(), m.end()):
                continue
            claimed.append((m.start(), m.end()))
            try:
                val = float(m.group("val").replace(",", ""))
            except (ValueError, IndexError):
                continue
            unit = ""
            gd = m.groupdict()
            if gd.get("unit"):
                unit = m.group("unit")
            elif gd.get("cur"):
                unit = m.group("cur")
            scale = gd.get("scale") if "scale" in gd else None
            out.append(NumericToken(val, unit, m.group(0).strip(), m.start(), m.end(),
                                    scale=scale))
    out.sort(key=lambda t: t.start)
    return out


# A comparative qualifier changes what a figure asserts. "more than 18 percent"
# is not established by evidence of exactly 18 percent -- it is a strictly
# stronger claim -- but the matcher compared bare magnitudes and called it
# consistent, which is the single easiest way to inflate a real result.
_LOWER_BOUND = ("more than", "greater than", "over", "at least", "in excess of",
                "upwards of", "exceeding", "above", "north of", "better than")
_UPPER_BOUND = ("up to", "less than", "fewer than", "under", "below", "at most",
                "no more than", "within")


def bound_qualifier(text: str, start: int) -> str | None:
    """'lower', 'upper' or None for the qualifier attached to the figure at
    ``start``. Looks only at the few words immediately before it."""
    prefix = text[:start].lower()
    tail = " ".join(prefix.split()[-4:])
    for phrase in _LOWER_BOUND:
        if tail.endswith(phrase) or tail.endswith(phrase + " a") or f"{phrase} " in tail[-len(phrase) - 8:]:
            return "lower"
    for phrase in _UPPER_BOUND:
        if tail.endswith(phrase) or tail.endswith(phrase + " a") or f"{phrase} " in tail[-len(phrase) - 8:]:
            return "upper"
    return None


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
