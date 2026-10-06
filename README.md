# Proposal Copilot Agent

**▶ Public simulation: <https://rfp-proposal.streamlit.app/>** — hosted URL for
the deterministic fixture workflow. It is not a live AI demonstration and may
still be running an earlier repository version until this branch is deployed.
For live, fully offline generative AI, run the app locally with Ollama as below.

Turns an inbound RFP into a source-grounded, review-ready proposal with full
**Requirement → Evidence → Draft** traceability and deterministic evidence
consistency checks. A practice lead must approve the bid before drafting;
reviewers approve sections and a partner approves the commercial reference
before export.

Built to the spec in [`SPEC.md`](SPEC.md) (a VCG case brief — "VCG" is a
fictional firm; the corpus and RFP fixtures are synthetic). **Core + Should-have
+ selected Stretch** are implemented: end-to-end pipeline (RFP → approved
proposal), traceability matrix, deterministic verifier, Streamlit hero screen,
section-level approval with edit preservation, SQLite audit log, conflict
detection, run resumability, local AI via Ollama, optional hosted LiteLLM,
Phase-0 calibration, and Markdown / CSV / DOCX export. CRM, HR, rate-card,
and time/billing inputs are fictional local sample files, not live integrations.

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
pytest -q                            # run the current test suite
streamlit run app.py                 # RFP → Requirements → Execution → Evidence → Draft → 🎯 Traceability → Review
```

### API keys

**There are none to replace.** Generation runs on a local Ollama model, so no
key is required and no document leaves the machine. `.env.example` lists every
setting; the only one that would need a credential is the optional hosted
`LLM_PROVIDER=litellm` path, which is not used for the demonstration.

### Running with the local model

```bash
ollama pull gemma3                 # one-time download, needs internet
ollama serve                       # if not already running
LLM_PROVIDER=ollama LLM_MODEL=gemma3:latest streamlit run app.py
```

After the pull, inference talks only to `127.0.0.1:11434` — you can disconnect
the network and the product still works.

**Which stages use the model.** `config.provider_for()` routes per stage:

| Stage | Handler | Why |
|---|---|---|
| Extract requirements, plan | Deterministic parser + source-span gate | A 4B local model produced requirements that retrieved no evidence at all (measured: fit 0%, 70 unresolvable citations). Structural parsing with a hallucination gate is both more reliable and faster here |
| **Draft sections, decompose claims** | **Local Ollama model** | Generation is where a model genuinely earns its place |
| Verify | Deterministic rules | Never a model. This is the product's whole thesis |

Set `LLM_ALL_STAGES=true` to route every stage through the model and reproduce
the measurement above.

### Recording the presentation run

A full local pass takes several minutes — too slow to perform live. Record it
once, then reopen it instantly from the sidebar and perform one short live
action on top:

```bash
LLM_PROVIDER=ollama LLM_MODEL=gemma3:latest python scripts/record_demo_run.py
```

The Execution tab reports measured tokens, latency, the local electricity cost
and the hosted-API equivalent, with every rate shown as a stated assumption.

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
  → plan_response → retrieve_internal → rank_evidence (select/reject w/ reasons)
  → qualify → practice-lead BID/NO_BID decision
  → detect_conflicts → optional_web_enrichment (disabled in offline modes)
  → draft_sections → extract_atomic_claims → deterministic_verify → build_traceability
  → section review + partner commercial sign-off → export
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
| LLM (extract / plan / draft / decompose) | `LLM_PROVIDER=mock` — deterministic simulation | `LLM_PROVIDER=ollama` + local model for real offline AI; optional `litellm` sends data to a hosted provider |
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
tests/                    verifier and approval-gate tests
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
- No code path drafts before a recorded practice-lead BID decision. No code path
  exports without every section approved and a partner commercial sign-off;
  unresolved gaps block export unless overridden with a recorded reason.
- The system never sends or submits anything externally.
