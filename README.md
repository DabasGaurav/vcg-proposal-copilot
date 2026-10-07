# Proposal Copilot

Turns an inbound RFP into a source-grounded, review-ready proposal in which
**every factual statement is traceable to the evidence it was written from** —
and any statement the evidence does not support is caught before a reviewer
sees it.

- **Live (deterministic):** <https://rfp-proposal.streamlit.app/>
- **Live AI:** runs locally on Ollama — no API key, no network, nothing leaves
  the machine. See [Running with the local model](#running-with-the-local-model).

The hosted URL cannot run a local model (Streamlit Community Cloud has no GPU
and no way to host one), so it runs the deterministic generator and says so in
the interface. The generative demonstration is the local one.

> "VCG" is a fictional firm. The evidence corpus and the four tenders are
> synthetic and labelled as such. Nothing here depicts a real client,
> engagement or person.

---

## What it actually does

Five stages, with two human gates that cannot be bypassed in code:

| | Stage | Gate |
|---|---|---|
| 1 | **Intake** — parse the tender into requirements, each tied to a quotation located in the source document | |
| 2 | **Qualify** — score evidence coverage, recommend bid / no-bid | **A practice lead must record a decision, a name and a reason before anything is drafted** |
| 3 | **Draft** — retrieve firm evidence, rank it, write each section from the passages that survived | |
| 4 | **Verify** — numeric, attribution and context checks, by rule | |
| 5 | **Release** — section approval + partner commercial sign-off | **No export until every section is approved and every unsupported claim is resolved or overridden with a recorded justification** |

## The demonstration

Running the ABC Bank tender (`python scripts/run_demo.py`) produces, among
others, these rows — reproduced from a real run:

| Requirement | Evidence | Drafted statement | Verdict |
|---|---|---|---|
| Named team members with relevant lending operations experience | `CV_001` | Ananya Mehta, Partner, has 18 years of experience in banking and lending operations | **Substantiated** |
| Demonstrated experience redesigning retail lending operations | `CASE_BANK_001` | In a retail lending engagement in India, VCG reduced pilot approval turnaround time by 18 percent and reduced manual handoffs by 30 percent | **Substantiated** |
| Evidence of **greater than 30 percent** turnaround-time improvement | *(none)* | In a comparable engagement, VCG delivered a **35 percent** turnaround-time improvement | **Unsubstantiated** |

The last row is the point. The tender demands a threshold the evidence base
cannot meet, so the drafter does what a writer under pressure to answer every
evaluation criterion does: it asserts a figure that clears the bar, with nothing
behind it. That claim is **built from the tender's own metric and threshold**,
not from a fixed sentence — a tender asking for ">25 percent reduction in
days-sales-outstanding" produces a claim about days-sales-outstanding. It
carries no citation, so verification rejects it as an orphan claim and it blocks
release.

---

## Quick start

Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_corpus.py      # build the evidence index from data/corpus/
pytest -q                          # 110 tests
streamlit run app.py
```

In the app: pick a tender, **Assess bid fit**, record a practice-lead decision,
then review the draft, the traceability matrix and the evidence; approve each
section and the commercial reference to unlock export.

Command line, no browser:

```bash
python scripts/run_demo.py                                # ABC Bank, prints the matrix
python scripts/run_demo.py xyz_insurer_actuarial_ai.md    # capability gap -> go/no-go
python scripts/run_demo.py pqr_bank_procurement_heavy.md  # procurement-governed tender
python scripts/run_demo.py def_capital_no_rubric.md       # tender with no evaluation rubric
```

### API keys

**There are none.** Generation runs on a local model, so no credential is
required and no document leaves the machine. `.env.example` documents every
setting; the only one that would need a key is the optional hosted
`LLM_PROVIDER=litellm` path, which the demonstration does not use.

---

## Running with the local model

```bash
ollama pull gemma3                 # one-time download, needs internet
LLM_PROVIDER=ollama LLM_MODEL=gemma3:latest streamlit run app.py
```

After the pull, inference talks only to `127.0.0.1:11434` — disconnect the
network and the product still works.

### Which stages use the model, and why

`config.provider_for()` routes per stage. This is a measured decision, not a
preference:

| Stage | Handler | Why |
|---|---|---|
| Extract, plan | Deterministic parsing behind the source-span gate | Routing these through a 4B local model was **worse**: bid fit scored 0%, no claim was substantiated, and 70 citations resolved to nothing, because model-extracted requirements retrieved no evidence |
| **Draft sections** | **Local model** | Generation is where a model genuinely earns its place |
| Decompose claims | Deterministic splitter | Through the model this hung for 14 minutes on 1.4 seconds of CPU — a small model given a bare JSON-array schema has no natural stopping point. Splitting prose into sentences is mechanical |
| **Verify** | **Deterministic rules — never a model** | This is the product's whole thesis |

`LLM_ALL_STAGES=true` routes everything through the model and reproduces the
measurement above.

### Recording a run for a demonstration

A full local pass takes minutes — too slow to perform live. Record it once, then
reopen it instantly from the sidebar and perform one short live action on top:

```bash
LLM_PROVIDER=ollama LLM_MODEL=gemma3:latest python scripts/record_demo_run.py
```

A measured run on an M4 / 16 GB laptop: **7 calls, 10,474 input and 1,924 output
tokens, 250 s, 5 statements substantiated and 9 blocked.**

---

## How it works

```
intake -> extract + validate (source-span gate; ungrounded requirements dropped)
  -> plan -> retrieve -> rank (select / reject, each with a recorded reason)
  -> QUALIFY ------- practice-lead BID / NO-BID gate -------+
                                                            |
  -> detect conflicts -> optional external context (off by default)
  -> draft -> decompose into atomic claims -> VERIFY -> build traceability
  -> section review + partner commercial sign-off -> export
```

A plain ordered function chain; every stage mutates one `ProposalAgentState` and
appends to `execution_log`.

**The model interprets and writes. It never judges whether its own output is
true.** That is [`pipeline/verification.py`](pipeline/verification.py), which is
extractive and rule-based:

- **numeric** — every figure in a claim must have a rounding-tolerant match in
  the cited passage *whose plus/minus 20-token context is topically consistent*.
  This is what catches a "35%" that exists in the corpus only in an unrelated
  document about office electricity.
- **attribution** — valid by default; invalid only on a real contradiction. The
  facts are read from the firm's own CV documents, so adding a CV adds a
  checkable person.
- **context** — a claim's geography or industry qualifier must not be
  contradicted by the cited passage's metadata.
- A contradicted figure can **never** be recorded as substantiated, at any
  confidence.

Call it **evidence-consistency verification**, not fact-checking. It catches the
error categories the corpus is built to surface and nothing beyond that.

### Every drafted sentence is composed from a cited passage

Section text is not templated. Phase names come from a retrieved methodology
passage and the engagement length from the tender; each person's name, role and
tenure are parsed from their own CV passage; the risk register comes from a
past-engagement passage that enumerates delivery risks; figures are read out of
the passage being cited, so a claim and its citation cannot drift apart.

**Where no passage supports a section, the drafter writes an
`[EVIDENCE GAP: ...]` rather than prose about an industry the tender may have
nothing to do with.** Feeding it a hospital revenue-cycle tender yields evidence
gaps in Approach, Team, Risks and the Executive Summary — not a lending
methodology. Two regression tests enforce this.

---

## Cost

The Execution tab reports measured tokens, latency, the local electricity cost
and the hosted-API equivalent for the same workload, plus a 10,000-user monthly
projection. Token counts and elapsed time are **measured**; every rate is a
**declared assumption** shown beside the figures and set in `config.py`
(see `services/costing.py`).

Running locally the marginal cost is electricity — fractions of a rupee per
proposal — against a few rupees for the same tokens on a hosted API. The
trade-off is explicit: hosted is faster and better written; local keeps the
tender and the firm's evidence inside the tenant.

---

## Known limitations

Stated plainly, because the product's whole claim is that it does not overstate:

- **Retrieval is weak.** TF-IDF barely separates good evidence from bad, so bid
  fit reads lower than it should. `EMBEDDINGS_BACKEND=sentence-transformers`
  improves it but needs a model download.
- **The local model invents citation IDs.** They are all rejected, which is the
  system working, but a run produces a substantial number of them.
- **Confidence is not calibrated.** It is a weighted blend of the signals, not a
  probability, despite being rendered as a bar.
- **No per-user isolation.** Saved runs are shared across browser sessions on a
  single deployment; the hosted URL is a single-tenant demonstration.
- **Chunking will mishandle tables.** Fixed-size splitting on headings; real
  tender eligibility criteria often live in tables.
- **No prompt-injection boundary.** Tender text reaches the drafting prompt
  untreated when a model is in use.
- **The evidence pool admits document-level passages.** A metric-bearing chunk
  from a selected *document* is made available to the drafter without itself
  passing the ranker threshold.
- **The corpus is synthetic**, so the demonstration is illustrative rather than a
  measurement against independently labelled ground truth.

---

## Backends

| Concern | Default | Alternative |
|---|---|---|
| Orchestrator | plain ordered function chain | — |
| Generation | `LLM_PROVIDER=mock` (deterministic) | `ollama` for local AI; `litellm` sends data to a hosted provider |
| Embeddings | `tfidf` — fit on the seeded corpus, no download | `sentence-transformers` |
| Vector store | local numpy matrix, pickle-persisted | ChromaDB |
| External context | `mock`, disabled | `tavily` or `ddg` — background only, never cited as firm evidence |

`scripts/calibrate.py` scores known-good and known-bad pairs against the real
corpus and embedding backend and writes the verification thresholds into `.env`.

## Resumability

Every stage persists a JSON snapshot and a full pickled state to SQLite.
`pipeline.graph.load_run(run_id)` reopens a run fully working — review,
regeneration and export all continue. Review actions re-persist, so a reopened
run reflects approval progress. The sidebar has a **Reopen run** selector.

## Layout

```
config.py                  thresholds, model routing, cost assumptions, paths
models/schemas.py          Pydantic v2 models
state/graph_state.py       ProposalAgentState
data/corpus/*.md           10 synthetic evidence documents
data/sample_systems/*.json fictional CRM / HR / rate-card / time-billing inputs
fixtures/rfp/*.md          4 tenders (happy path, capability gap, procurement, no rubric)
pipeline/                  one module per stage, plus graph.py, qualification.py,
                           verification.py, review.py, export.py
services/                  corpus loader, embeddings, vector store, LLM providers,
                           costing, persistence, text utilities
scripts/                   seed_corpus, calibrate, run_demo, record_demo_run
tests/                     110 tests
app.py, ui.py              Streamlit interface and design tokens
```

## Guarantees

- Every extracted requirement carries a locatable source quotation; ungrounded
  ones are dropped, not passed downstream. A document yielding no requirements
  stops the run rather than producing a proposal.
- Selected **and** rejected evidence both carry reasons; conflicts are surfaced,
  never silently resolved.
- Every citation must resolve to selected evidence — including on
  forward-looking statements, which need no evidence but may not assert false
  provenance.
- No code path drafts before a recorded practice-lead decision. No code path
  exports without every section approved and a partner commercial sign-off;
  unresolved gaps block release unless overridden with a recorded justification.
- The system never transmits or submits anything externally. Submission remains
  a manual action outside the platform.
