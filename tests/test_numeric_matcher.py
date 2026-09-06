"""SPEC Section 15 -- numeric matcher: rounding tolerance + context-window check."""
from __future__ import annotations

from services.text import extract_numeric_tokens, numbers_match
from pipeline.verification import numeric_consistency


def test_extracts_percentages_durations_currency():
    toks = extract_numeric_tokens("reduced TAT by 18 percent over 16 weeks, saving $2m")
    units = sorted(t.canonical_unit() for t in toks)
    assert "percent" in units and "weeks" in units and "currency" in units


def test_rounding_tolerance():
    assert numbers_match(18.0, 18.2)            # within +/-0.5
    assert numbers_match(18.0, 18.0)
    assert not numbers_match(18.0, 35.0)
    assert not numbers_match(18.0, 22.0)


def test_no_numeric_token_returns_none():
    assert numeric_consistency("VCG redesigned the lending operating model", "anything") is None


def test_matching_number_in_agreeing_context_is_true():
    ev = ("Pilot approval turnaround time was reduced by 18 percent versus the "
          "matched baseline.")
    assert numeric_consistency("VCG reduced pilot approval turnaround time by 18 percent", ev) is True


def test_contradicting_number_is_false():
    ev = "Pilot approval turnaround time was reduced by 18 percent versus the baseline."
    assert numeric_consistency("VCG reduced lending turnaround time by 35 percent", ev) is False


def test_right_number_wrong_context_is_false():
    """The DISTRACTOR case: '35 percent' exists but only about electricity."""
    ev = ("Electricity use across the measured office sites fell by 35 percent "
          "year on year after the lighting retrofit.")
    assert numeric_consistency("VCG reduced lending turnaround time by 35 percent", ev) is False


def test_close_number_same_context_tolerated():
    ev = "Turnaround time fell by 18.2 percent against the baseline cohort."
    assert numeric_consistency("VCG cut turnaround time by 18 percent", ev) is True
