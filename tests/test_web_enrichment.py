"""SPEC Section 12 -- web enrichment: optional, background-only, never a VCG credential."""
from __future__ import annotations

import config
from pipeline import web_enrichment
from services import web_search


def test_disabled_by_default(abc_state):
    # abc_state runs with web_search=False
    assert abc_state["web_evidence"] == []
    assert any(s["stage"] == "optional_web_enrichment" and s["status"] == "skipped"
              for s in abc_state["execution_log"])


def test_guardrail_strips_vcg_credential_claims():
    raw = [
        {"title": "Retail banking outlook 2026", "snippet": "Sector margins compress."},
        {"title": "VCG case study: 40% TAT cut", "snippet": "Our team delivered..."},
    ]
    kept = web_search._guardrail(raw)
    assert len(kept) == 1 and "VCG" not in kept[0]["title"]


def test_enabled_run_records_context_only(monkeypatch, tmp_path):
    monkeypatch.setattr(web_enrichment, "search",
                        lambda q, k=4, provider=None: [
                            {"title": "Industry note", "snippet": "neutral background",
                             "url": "x", "provider": "mock"}])
    from pipeline.graph import run_pipeline
    st = run_pipeline(str(config.FIXTURE_DIR / "abc_bank_lending_transformation.md"),
                      web_search=True, persist=False)
    assert st["web_evidence"] and st["web_evidence"][0]["usage"] == "context_only"
    # web items never enter the citable evidence pool
    for k, evs in st["selected_evidence"].items():
        for e in evs:
            assert not e.source_path.startswith("http")


def test_unknown_provider_falls_back_to_mock():
    res = web_search.search("banking", provider="does-not-exist")
    assert res and res[0]["provider"] == "mock"
