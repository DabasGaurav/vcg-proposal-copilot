"""Does the selected evidence actually satisfy a requirement?

One home for that question, because two stages were answering it differently.

`pipeline/qualification.py` scored bid fit as the share of evidence requirements
for which retrieval returned *anything*, and raised a mandatory gap only when it
returned *nothing*. It never asked whether what came back substantiated the
requirement. The consequences were both directions of wrong:

  * A tender demanding "at least 45 percent turnaround-time improvement" scored
    100/100 and BID_REVIEW, counted as covered by the one case study that records
    18 percent. Minutes later the same pipeline rejected every threshold claim as
    contradicted.
  * A tender whose MANDATORY criterion was a delivered core banking replacement
    scored 75/100 and BID_REVIEW, its mandatory requirement counted as covered by
    a methodology document whose own text says it "must not be cited as evidence
    that VCG has executed a past lending delivery engagement".

Nothing here calls an LLM. Both the qualification gate and the drafter use it, so
the stage that decides whether to bid and the stage that writes the prose cannot
disagree about what the evidence will support.
"""
from __future__ import annotations

import re
from typing import Any

from services.text import bound_qualifier, context_window_tokens, extract_numeric_tokens

# --------------------------------------------------------------------------- #
# Reading evidence that may arrive as a model or as a plain dict
# --------------------------------------------------------------------------- #
def _field(evidence: Any, name: str) -> str:
    if isinstance(evidence, dict):
        value = evidence.get(name, "")
    else:
        value = getattr(evidence, name, "")
    return str(getattr(value, "value", value) or "")


# --------------------------------------------------------------------------- #
# Numeric thresholds
# --------------------------------------------------------------------------- #
METRIC_WORDS: dict[str, tuple[str, ...]] = {
    "turnaround": ("turnaround", "tat", "approval time", "cycle time"),
    "effort": ("effort", "processing effort", "handling time", "cost per"),
    "handoff": ("handoff", "hand-off", "handover", "touchpoint"),
    "rework": ("rework", "error", "defect"),
    "accuracy": ("accuracy", "forecast accuracy"),
    "inventory": ("inventory", "stock", "cover"),
}


def requirement_threshold(text: str) -> tuple[float, str] | None:
    """The bar a requirement sets, as (value, unit), or None if it sets none.

    Uses the shared tokeniser, so a bar written in words counts the same as one
    written in digits, and a percentage-point bar stays distinct from a percent
    one -- a 15-point accuracy gain is not a 15 percent gain.
    """
    for tok in extract_numeric_tokens(text):
        unit = tok.canonical_unit()
        if unit not in ("percent", "percentage_points"):
            continue
        if bound_qualifier(text, tok.start) == "lower":
            return tok.value, unit
    return None


def requirement_metric_words(text: str) -> tuple[str, ...]:
    """The metric the requirement attaches its bar to."""
    low = text.lower()
    hits: list[str] = []
    for words in METRIC_WORDS.values():
        if any(w in low for w in words):
            hits.extend(words)
    return tuple(hits)


def figure_is_about(chunk: str, tok, words: tuple[str, ...]) -> bool:
    """Is this number about `words`, or merely in the same passage?

    The same line-scoped context rule the verifier applies, so the drafter cannot
    promise what verification will then refuse.
    """
    if not words:
        return True
    negated = ("no validated", "not recorded", "no turnaround", "could not be",
               "was unchanged", "no end-to-end", "not substantiated")
    line_start = chunk.rfind("\n", 0, tok.start) + 1
    line_end = chunk.find("\n", tok.end)
    line = chunk[line_start: line_end if line_end != -1 else len(chunk)].lower()
    if any(n in line for n in negated):
        return False
    return any(w in line for w in words)


def evidence_meets_threshold(evidence: list[Any], pct: float, unit: str,
                             words: tuple[str, ...]) -> bool:
    for ev in evidence:
        chunk = _field(ev, "chunk_text")
        for tok in extract_numeric_tokens(chunk):
            if (tok.canonical_unit() == unit and tok.value >= pct
                    and figure_is_about(chunk, tok, words)):
                return True
    return False


# --------------------------------------------------------------------------- #
# Delivery track record
# --------------------------------------------------------------------------- #
# A requirement asking what the firm has DONE is answerable only by a record of
# having done it. A methodology or a winning-proposal pattern describes how the
# firm works and what reviewers rewarded; neither is a delivery record.
_DELIVERY_RE = re.compile(
    r"\b(demonstrated|demonstrate|prior experience|previous experience|"
    r"track record|has delivered|have delivered|delivered|completed|"
    r"past engagement|comparable engagement|reference|evidence of a delivered|"
    r"experience delivering|experience executing|experience running)\b",
    re.I,
)
_FORWARD_SCOPE_RE = re.compile(
    r"\b(will be delivered|must be delivered|to be delivered|deliverables?:)\b", re.I)

DELIVERY_CATEGORIES = {"CASE_STUDY"}


def asks_for_delivery_evidence(text: str) -> bool:
    if _FORWARD_SCOPE_RE.search(text):
        return False
    return bool(_DELIVERY_RE.search(text))


def is_delivery_record(evidence: Any) -> bool:
    return _field(evidence, "category").upper() in DELIVERY_CATEGORIES


def has_delivery_evidence(evidence: list[Any]) -> bool:
    return any(is_delivery_record(ev) for ev in evidence)


# --------------------------------------------------------------------------- #
# The single question both stages ask
# --------------------------------------------------------------------------- #
def substantiation_gap(requirement_text: str, evidence: list[Any]) -> str | None:
    """Why the selected evidence does NOT satisfy this requirement, or None.

    Retrieval returning something is not substantiation. This is what "covered"
    has to mean for a bid decision to be worth anything.
    """
    if not evidence:
        return "no evidence was selected"

    bar = requirement_threshold(requirement_text)
    if bar is not None:
        pct, unit = bar
        words = requirement_metric_words(requirement_text)
        if not evidence_meets_threshold(evidence, pct, unit, words):
            shown = "percentage points" if unit == "percentage_points" else "percent"
            return (f"the tender asks for at least {pct:g} {shown} and no selected "
                    f"passage records a figure at that level for this metric")

    if asks_for_delivery_evidence(requirement_text) and not has_delivery_evidence(evidence):
        kinds = sorted({_field(ev, "category") or "UNKNOWN" for ev in evidence})
        return (f"the tender asks for a delivery track record and the selected "
                f"evidence is {', '.join(kinds)}, not a case study")

    return None
