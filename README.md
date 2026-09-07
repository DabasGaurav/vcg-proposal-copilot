# Proposal Copilot Agent

**▶ Live demo: <https://rfp-proposal.streamlit.app/>** — no install, no API key.
Pick `abc_bank_lending_transformation`, press **Run pipeline**, open the
**Traceability** tab.

Turns an inbound RFP into a source-grounded, review-ready proposal with full
**Requirement → Evidence → Draft** traceability, **deterministic** (non-LLM-judged)
evidence-consistency verification, and a hard architectural gate that requires
human approval of every section before any export.

Built to the spec in [`SPEC.md`](SPEC.md) (a VCG case brief — "VCG" is a
fictional firm; the corpus and RFP fixtures are synthetic). **Core + Should-have
+ selected Stretch** are implemented: end-to-end pipeline (RFP → approved
proposal), traceability matrix, deterministic verifier, Streamlit hero screen,
section-level approval with edit preservation, SQLite audit log, conflict
detection, run resumability, real-LLM path (LiteLLM), optional web enrichment
(Tavily / DDG), Phase-0 calibration that writes thresholds to `.env`, and
Markdown / CSV / DOCX export. **70 tests, all green.**

## The hero moment

| RFP Requirement | Evidence | Draft Claim | Status |
|---|---|---|---|
| Demonstrate lending transformation experience | `CASE_BANK_001` | VCG redesigned retail lending operations for a large Indian bank | **SUPPORTED** |
| Demonstrate measurable results | `CASE_BANK_001` | Pilot approval turnaround time reduced by **18%** | **SUPPORTED** |
| Demonstrate >30% TAT improvement | *(none)* | VCG reduced lending TAT by **35%** | **GAP** |

18% passes; the unsupported 35% claim is caught before it can reach an approved
proposal. That single interaction is the demo.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Python 3.11+
pip install -r requirements.txt
python scripts/seed_corpus.py        # build the vector KB from data/corpus/*.md
python scripts/calibrate.py          # Phase 0: print real scores, propose thresholds
pytest -q                            # 58 tests, all green
streamlit run app.py                 # RFP → Requirements → Execution → Evidence → Draft → 🎯 Traceability → Review
```

Deterministic CLI demo (no API key, no network):

```bash
python scripts/run_demo.py                                  # abc_bank happy path + hero check
python scripts/run_demo.py xyz_insurer_actuarial_ai.md      # capability-gap fixture
python scripts/run_demo.py pqr_bank_procurement_heavy.md    # procedural-heavy fixture
python scripts/run_demo.py def_capital_no_rubric.md         # no eval criteria + compound-bullet split
```

## How it works

```
intake → decompose_rfp → validate_requirements (source-span gate; ungrounded → dropped)
  → plan_response → retrieve_internal → rank_evidence (select/reject w/ reasons) → detect_conflicts
  → optional_web_enrichment (off by default; background only, never a VCG credential)
  → draft_sections → extract_atomic_claims → deterministic_verify → build_traceability
  → await_human_review   ← the pipeline stops here; nothing exports without approval
```

Orchestrator is a **plain ordered function chain** (SPEC §0 fallback), each stage
mutating one `ProposalAgentState` dict and appending to `execution_log`.

**LLMs** interpret, plan, draft, and decompose claims. LLMs are **never** the
judge of whether their own output is true — that is
[`pipeline/verification.py`](pipeline/verification.py), which is extractive and
rule-based only:

* **numeric** — every number in a claim must have a rounding-tolerant match in
  the cited chunk *whose ±20-token context is topically consistent* (catches
  "35%" that only exists in an unrelated office-electricity doc);
* **attribution** — defaults valid; set invalid only on a real named-entity
  contradiction (e.g. "Rohan has 18 years" vs his CV's 12);
* **context** — a claim's geography/industry qualifier must not be contradicted
  by the matched evidence's metadata (India claim vs Southeast-Asia evidence → PARTIAL);
* decision rules A–G are lifted verbatim from SPEC §15.

Call it **evidence-consistency verification**, not "fact-checking" — it catches
every error category the demo corpus is built to surface and nothing beyond that.

## Pluggable backends (defaults are offline; switch via `.env`)

| Concern | Default | Alternative |
|---|---|---|
| Orchestrator | plain ordered function chain (§0) | — (LangGraph deliberately not used; same audit/demo value) |
| LLM (extract / plan / draft / decompose) | `LLM_PROVIDER=mock` — deterministic, fixture-aware, zero API keys | `LLM_PROVIDER=litellm` + `LLM_MODEL` → real calls via LiteLLM (`services/real_llm.py`; prompts emit the same `[[ev:]]`/`[[req:]]` citation convention the verifier needs) |
| Embeddings | `EMBEDDINGS_BACKEND=tfidf` — scikit-learn, fit on the seeded corpus, no download | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| Vector store | local numpy matrix, pickle-persisted | ChromaDB (`VECTORSTORE_BACKEND=chroma`) |
| Web enrichment | `WEB_SEARCH_PROVIDER=mock`, disabled | `tavily` (needs `TAVILY_API_KEY`) or `ddg` (needs `duckduckgo_search`); background context only, never a VCG credential |

`scripts/calibrate.py` (Phase 0) scores the §15 known-good/known-bad pairs against
the **real seeded corpus + real embedding backend** and writes
`SEM_SUPPORTED` / `SEM_PARTIAL` / `LEX_SUPPORTED` into `.env`. With the TF-IDF
backend the claim↔chunk semantic band is low, so SUPPORTED/GAP decisions lean on
the numeric / attribution / context rules (C/D/E); the similarity thresholds
(F/G) are the fallback.

## Resumability

Every stage writes a lightweight JSON snapshot **and** a full pickled working
state to SQLite (`run_state`). `pipeline.graph.load_run(run_id)` reopens a run
with a fully functional state — review, regeneration, and export all continue.
Review actions re-persist, so a resumed run reflects approval progress. The
Streamlit sidebar has a **Resume a run** selector.

## Layout

```
config.py                 all thresholds / models / paths (System-Owner-owned)
models/schemas.py         Pydantic v2 models (SPEC §7)
state/graph_state.py      ProposalAgentState (SPEC §6)
data/corpus/*.md          the 10 synthetic KB documents (SPEC §9)
fixtures/rfp/*.md          the 3 demo RFPs (SPEC §10)
services/                 corpus loader/chunker · embeddings · vector store · mock LLM · SQLite persistence · text utils
pipeline/                 one module per stage + graph.py orchestrator + review.py + export.py
services/real_llm.py      LiteLLM prompts for the 4 delegated ops (mock stays default)
services/web_search.py    mock / Tavily / DDG providers + VCG-credential guardrail
scripts/                  seed_corpus · calibrate (Phase 0, writes .env) · run_demo
tests/                    70 tests; verifier cases (SPEC §15) written first
app.py                    Streamlit hero screen
```

## Guarantees (Definition of Done, SPEC §18)

- Every extracted requirement carries a locatable source span; ungrounded ones
  are dropped, not passed downstream.
- Compound requirements split; procedural items kept in their own checklist;
  capability gaps explicit and surfaced as a go/no-go.
- Selected **and** rejected evidence both carry reasons; conflicts are surfaced,
  never silently resolved.
- ≥5 proposal sections; each cites only selected evidence; gaps written as
  `[EVIDENCE GAP: …]`, human-only content as `HUMAN INPUT REQUIRED`.
- No code path exports without every section `APPROVED`; unresolved `GAP`s block
  export unless overridden with a recorded reason.
- The system never sends or submits anything externally.
