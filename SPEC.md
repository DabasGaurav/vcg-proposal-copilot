# VCG Proposal Copilot Agent — Final Build Spec (v4, consolidated)

**Target file:** `SPEC.md` — hand this directly to Claude Code.
**Objective:** Turn an inbound RFP into a source-grounded, review-ready proposal, with full Requirement → Evidence → Draft traceability, deterministic (non-LLM-judged) fact-checking, and a hard architectural gate requiring human approval before any export.

This document supersedes all prior drafts. It keeps what worked, fixes one real logic bug found in the previous draft's verification rules, replaces unvalidated-looking thresholds with a mandatory calibration step, and sets an honest time-box.

---

## 0. Build Directive for Claude Code

**Priority order — do not reorder:**
1. End-to-end working pipeline (RFP → approved proposal), even if UI is rough.
2. Requirement → Evidence → Draft traceability.
3. Deterministic detection of unsupported claims (this is the demo's entire point).
4. Explicit evidence rejection, gap-surfacing, and conflict-surfacing.
5. Human review gates — no code path to export without them.
6. Inspectable agent execution log.
7. Exportable proposal.
8. Code cleanliness.

**Do not add:** authentication, enterprise SSO, Docker/Kubernetes, message queues, multi-tenancy, production cloud infra, autonomous client submission, real pricing logic, OCR (v1), multilingual support.

**Sequencing instruction — read this before writing any code:** implement **only** Core-tier scope first (see table below). Do not write code for Should-have or Stretch capabilities until every Core acceptance test in §15 and §18 is green. Where a Core module's interface needs something from a Should-have piece (e.g. the audit log, DOCX export), stub it with a no-op or an in-memory placeholder rather than building it early. This is the single most effective guard against burning the day on polish before the 18%-vs-35% demo moment actually works.

**Honest time-box** (this is the part every prior draft got wrong — treat this table as binding):

| Tier | Scope | Realistic effort |
|---|---|---|
| **Core (must finish)** | Corpus + fixtures → extraction w/ source-span validation → retrieval/ranking → drafting → deterministic verifier → traceability matrix → Streamlit hero screen (evidence + traceability tabs) → section-level approval → Markdown export | ~1 focused day |
| **Should have** | SQLite audit log, conflict detection, DOCX export, section regeneration, human-edit preservation, 2nd/3rd demo RFP fixtures | Add if Core finishes with time to spare |
| **Stretch, cut first if behind** | Live web search (Tavily/DDG), resumability UX, sophisticated NER, visual polish | Do not attempt before Core is fully green |

Run locally:
```bash
pip install -r requirements.txt
python scripts/seed_corpus.py
pytest -q
streamlit run app.py
```
Deterministic CLI demo (no live web required):
```bash
python scripts/run_demo.py
```

**Known environment risks to check on day 1, not day-of-demo:**
- `sentence-transformers` downloads a model from Hugging Face on first run — confirm network access before relying on it; have a pinned local cache or a smaller pure-Python fallback (e.g. TF-IDF cosine via scikit-learn) ready if offline.
- LangGraph adds real framework-learning overhead. It's kept here because it gives the "visible agent state transitions" hero feature almost for free — but if it's fighting you after ~2 hours, fall back to a **plain ordered list of Python functions**, each appending to the same `execution_log` list. The audit/demo value is nearly identical; only the automatic conditional-routing sugar is lost, and this pipeline only has two real branch points anyway.

---

## 1. Product Objective & Hero Feature

The system must visibly do more than generate text. For every material factual claim it must be able to answer, on demand, in the UI:

```
RFP requirement → exact source quote in the RFP
    → evidence need identified
    → candidates retrieved
    → weak/irrelevant candidates explicitly rejected (with reason)
    → selected chunk (verbatim text, not a summary)
    → claim drafted from it
    → claim independently verified against that exact chunk
    → human approved / rejected it
```

**Hero screen — the Requirement → Evidence → Draft Traceability Matrix:**

| RFP Requirement | Evidence | Draft Claim | Status |
|---|---|---|---|
| Demonstrate lending transformation experience | CASE_BANK_001 | VCG redesigned retail lending operations for a large Indian bank | SUPPORTED |
| Demonstrate measurable results | CASE_BANK_001 | Pilot approval turnaround time reduced by 18% | SUPPORTED |
| Demonstrate >30% TAT improvement | *(none)* | VCG reduced lending TAT by 35% | GAP |

The last row must never silently survive into an approved proposal. That single interaction — 18% passes, 35% is caught — is the entire demo.

---

## 2. Users & Authority

| Actor | Role |
|---|---|
| Requester (BD/Partner) | Uploads RFP, triggers the run |
| Reviewer (Partner/EM) | Approves/rejects per section and per claim |
| Agent | Executes bounded pipeline stages only |
| System Owner | Owns thresholds, corpus, calibration |

**Hard authority rule:** the agent never autonomously finalizes pricing, commercial terms, named staffing commitments, client references, or unverified credentials. There is **no code path** from draft to export that skips human approval of every section. The system never sends or submits anything externally — that stays a manual, out-of-system action, permanently.

---

## 3. Goals / Non-Goals

**Goals:** ingest PDF/Markdown/text RFPs; extract requirements with source-span validation; classify each as content/procedural/commercial/compliance and by handling type; retrieve + rank synthetic internal evidence; reject weak matches with a reason; surface conflicts and gaps explicitly (never resolve silently); optionally enrich client/industry context via web (never VCG credentials); draft section-by-section from selected evidence only; decompose drafts into atomic claims; verify factual claims deterministically; build a full traceability matrix; support section-level human approval with edit preservation; export approved content only.

**Non-goals:** real CRM/SharePoint integration; production security; OCR in v1 (scanned PDF → clear error, not a guess); enterprise SSO; a real pricing engine; automatic submission; general-purpose fact-checking beyond the demo corpus; multilingual support; complex concurrency.

---

## 4. Success Criteria

A demo user can: upload an RFP → see extracted client/problem/timeline/scope/deliverables/criteria with each traced to its source quote → see the evidence checklist and response plan → see selected *and* rejected evidence with reasons → see any conflict or gap as an explicit flag → get ≥5 drafted sections → inspect the exact chunk behind any claim → see unsupported claims auto-flagged → approve/reject at the section and claim level → regenerate only the affected section → have direct manual edits survive later regeneration of other sections → export Markdown (DOCX if time allows) → export the traceability matrix as CSV.

---

## 5. Architecture

```
                    STREAMLIT UI
  Upload | Requirements | Execution | Evidence | Draft | Traceability | Review
                         │
                         ▼
                LANGGRAPH PIPELINE (or plain function chain — see §0 fallback)

  intake → decompose_rfp → validate_requirements
      ↳ invalid → retry (max 2) → still invalid → flag, don't pass downstream
  → plan_response → retrieve_internal → rank_evidence → detect_conflicts
  → retrieval_decision ──(gap)──► optional_web_enrichment ──┐
                    └──(sufficient)───────────────────────────┤
                                                               ▼
                                                        draft_sections
                                                               ▼
                                                     extract_atomic_claims
                                                               ▼
                                                     deterministic_verify
                                                               ▼
                                                     build_traceability
                                                               ▼
                                                     await_human_review
                                          ┌─────────────┴─────────────┐
                                    all approved              changes requested
                                          │                           │
                                      finalize               revise_section → deterministic_verify → await_human_review (loop)
       │                    │                     │
       ▼                    ▼                     ▼
  LiteLLM (Anthropic/OpenAI)   ChromaDB (internal KB)   Web provider (mock/Tavily/DDG)
                                     │
                            SQLite: audit_log + review_decisions (state resumability via LangGraph checkpointer)
```

**Design principle:** LLMs interpret, plan, rank candidates, draft, and decompose claims. LLMs are **never** the sole judge of whether their own output is factually true — that's the deterministic verifier's job, using extractive scoring, not a second LLM opinion.

---

## 6. State Schema

```python
# state/graph_state.py
from typing import TypedDict
from models.schemas import (
    RFPRequirements, EvidenceChecklistItem, EvidenceItem,
    ProposalDraft, TraceabilityEntry, AtomicClaim, ReviewDecisionRecord,
    EvidenceConflict,
)

class ProposalAgentState(TypedDict, total=False):
    run_id: str
    version: int

    rfp_path: str
    rfp_raw_text: str
    rfp_filename: str
    language: str

    rfp_data: RFPRequirements
    requirement_validation_errors: list[str]

    checklist: list[EvidenceChecklistItem]
    proposal_outline: list[str]
    procedural_checklist: list[str]
    human_input_requirements: list[str]

    retrieval_queries: dict[str, list[str]]
    retrieved_evidence: dict[str, list[EvidenceItem]]
    selected_evidence: dict[str, list[EvidenceItem]]
    rejected_evidence: dict[str, list[EvidenceItem]]
    retrieval_gaps: list[str]
    evidence_conflicts: list[EvidenceConflict]

    web_evidence: list[EvidenceItem]
    web_search_enabled: bool

    draft_sections: dict[str, str]
    proposal_draft: ProposalDraft

    atomic_claims: list[AtomicClaim]
    overall_traceability: list[TraceabilityEntry]

    review_status: str
    section_review_status: dict[str, str]
    reviewer_decisions: list[ReviewDecisionRecord]
    human_edits: dict[str, str]

    warnings: list[str]
    errors: list[str]
    retry_count: dict[str, int]
    execution_log: list[dict]
```

---

## 7. Data Models (`models/schemas.py`, Pydantic v2)

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

class EvidenceCategory(str, Enum):
    CASE_STUDY = "CASE_STUDY"; METHODOLOGY = "METHODOLOGY"; TEAM_CV = "TEAM_CV"
    WINNING_PROPOSAL = "WINNING_PROPOSAL"; MARKET_RESEARCH = "MARKET_RESEARCH"; OTHER = "OTHER"

class RequirementCategory(str, Enum):
    CONTENT = "CONTENT"; PROCEDURAL = "PROCEDURAL"; COMMERCIAL = "COMMERCIAL"; COMPLIANCE = "COMPLIANCE"

class RequirementHandling(str, Enum):
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"; NEEDS_HUMAN_INPUT = "NEEDS_HUMAN_INPUT"
    TEMPLATE_SATISFIABLE = "TEMPLATE_SATISFIABLE"; PROCEDURAL_ONLY = "PROCEDURAL_ONLY"
    CAPABILITY_GAP = "CAPABILITY_GAP"

class VerificationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"; PARTIAL = "PARTIAL"; GAP = "GAP"; FORWARD_LOOKING = "FORWARD_LOOKING"

class ReviewDecision(str, Enum):
    PENDING = "PENDING"; APPROVED = "APPROVED"; REJECTED = "REJECTED"; CHANGES_REQUESTED = "CHANGES_REQUESTED"

class ClaimType(str, Enum):
    FACTUAL = "FACTUAL"; NUMERIC = "NUMERIC"; EXPERIENCE = "EXPERIENCE"
    METHODOLOGY = "METHODOLOGY"; PROPOSED_ACTION = "PROPOSED_ACTION"; OPINION = "OPINION"

class SourceSpan(BaseModel):
    page: int | None = None
    section: str | None = None
    quote: str                 # must be locatable in normalized RFP text — see §8
    start_char: int | None = None
    end_char: int | None = None

class RFPRequirement(BaseModel):
    requirement_id: str
    text: str
    category: RequirementCategory
    handling: RequirementHandling
    mandatory: bool | None
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    source_span: SourceSpan

class EvidenceItem(BaseModel):
    evidence_id: str
    source_id: str
    title: str
    category: EvidenceCategory
    chunk_id: str
    chunk_text: str             # INVARIANT: verbatim source text, never an LLM summary
    source_path: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    metadata_match_score: float = 0.0
    reasoning: str
    selected: bool = False
    rejection_reason: str | None = None
    usage_restriction: str = "internal_only"   # or "nda_restricted"
    freshness_date: str | None = None
    superseded_by: str | None = None
    conflict_flag: bool = False
    metadata: dict = Field(default_factory=dict)

class EvidenceConflict(BaseModel):
    conflict_id: str
    evidence_ids: list[str]
    conflict_type: str          # "numeric_mismatch" | "attribution_mismatch" | "superseded"
    description: str
    requires_human_resolution: bool = True

class AtomicClaim(BaseModel):
    claim_id: str
    section_name: str
    claim_text: str
    claim_type: ClaimType
    cited_evidence_ids: list[str] = Field(default_factory=list)
    numeric_tokens: list[str] = Field(default_factory=list)
    named_entities: list[str] = Field(default_factory=list)   # empty = no attribution check applies
    context_qualifiers: list[str] = Field(default_factory=list)  # e.g. ["India"], ["SME"] — simple keyword extraction, checked against evidence metadata in §15
    requires_verification: bool = True

class TraceabilityEntry(BaseModel):
    trace_id: str
    requirement_id: str
    rfp_requirement: str
    requirement_source_span: SourceSpan | None = None
    matched_evidence_id: str | None = None
    matched_chunk_text: str | None = None
    draft_section: str
    claim_id: str
    claim_text: str
    verification_status: VerificationStatus
    confidence_score: float = Field(ge=0.0, le=1.0)
    lexical_overlap: float = 0.0
    semantic_similarity: float = 0.0
    numeric_match: bool | None = None      # None = not applicable (no numeric token in claim)
    attribution_valid: bool = True         # DEFAULT TRUE — see §11 fix; only set False on an actual mismatch
    conflict_flag: bool = False
    verification_reason: str
    reviewer_decision: ReviewDecision = ReviewDecision.PENDING
    reviewer_comment: str | None = None

class ProposalSection(BaseModel):
    section_id: str
    title: str
    content_markdown: str
    version: int = 1
    evidence_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    has_gaps: bool = False
    review_status: ReviewDecision = ReviewDecision.PENDING
    human_edited: bool = False

class ProposalDraft(BaseModel):
    proposal_id: str
    client: str
    rfp_id: str
    run_id: str
    sections: list[ProposalSection]
    overall_traceability: list[TraceabilityEntry]
    supported_claim_count: int = 0
    partial_claim_count: int = 0
    gap_claim_count: int = 0
    status: ReviewDecision = ReviewDecision.PENDING

class ReviewDecisionRecord(BaseModel):
    decision_id: str
    run_id: str
    section_id: str
    reviewer: str
    decision: ReviewDecision
    comment: str | None = None
    timestamp: datetime

class AuditLogEntry(BaseModel):
    event_id: str
    run_id: str
    stage: str
    actor: str          # "agent" | "human"
    timestamp: datetime
    status: str
    notes: str | None = None
```

---

## 8. Requirement Extraction & Validation

1. Extract discrete requirements with: text, category, handling, mandatory flag, source span, confidence.
2. **Split compound bullets** into separate trackable requirements.
3. **Source-span validation (anti-hallucination gate):** normalize both the RFP text and `source_span.quote`, and confirm the quote is locatable via substring/fuzzy match. If it isn't, the requirement is invalid — flag it, do **not** pass it downstream. This is the single check that prevents the extractor from inventing requirements.
4. Separate **procedural** items (NDA, references, submission format) into a procedural checklist — these must appear somewhere even though they never become proposal prose.
5. If a requirement asks for a capability the corpus has zero coverage for, classify as `CAPABILITY_GAP` — a go/no-go signal for a human, never papered over.
6. If evaluation criteria are absent from the RFP entirely, flag this explicitly rather than inventing a rubric.
7. On missing optional fields: `None`/`[]` plus a warning — never invent a value.

---

## 9. Synthetic Knowledge Base (10 documents, `data/corpus/*.md`)

Every document carries metadata: `document_id, category, industry, subsector, region, year, freshness_date, usage_restriction, superseded_by`.

| ID | Purpose | Key facts |
|---|---|---|
| `CASE_BANK_001` | Primary supporting evidence | Indian retail bank, 16-week lending-ops redesign. **18% pilot approval TAT reduction**, 22% processing-effort reduction, 30% fewer manual handoffs. **Must never mention 35% anywhere.** |
| `CASE_BANK_002` | Nuance/partial-match test | SE Asian SME bank, 14 weeks, 25%/17% process metrics, **no validated TAT reduction recorded** — tests that the ranker doesn't overclaim geography/domain match. |
| `CASE_SC_001` | Distractor (same buzzwords, wrong domain) | Consumer-goods supply-chain redesign; "operating model," "transformation," "India" all appear, but zero banking/lending content — tests semantic-distractor rejection. |
| `METHOD_001` | Workplan evidence | 12-week, 4-phase methodology (Diagnose/Design/Pilot/Scale) — primary source for the proposed workplan. |
| `METHOD_002` | Capability ≠ experience test | Core-banking diagnostic framework — proves methodology capability only, must not be cited as proof of past lending delivery. |
| `CV_001` | Attribution test (Person A) | Ananya Mehta, Partner, **18 years** experience, banking/lending. |
| `CV_002` | Attribution test (Person B) | Rohan Sen, Principal, **12 years**, SME lending/underwriting. Do not invent CFA/ex-RBI/ML credentials. |
| `PROP_001` | Reusable structure | Winning-proposal skeleton (9 standard sections + tone patterns). |
| `PROP_002` | Reusable structure | Winning-proposal patterns for credit-ops engagements. |
| `DISTRACTOR_001` | Numeric false-positive test | VCG office-sustainability initiative, **"35%" reduction in electricity use**, zero client/banking content — this is the document that catches a verifier doing naive substring number-matching instead of context-aware matching. |

---

## 10. Demo RFP Fixtures (build all three — this is how you prove the edge cases actually work, not just describe them)

1. **`abc_bank_lending_transformation.md`** — happy path. Client/context/12-week timeline/6 scope items/6 deliverables/6 evaluation criteria, plus a **Procedural Requirements** section (English-only submission, pricing submitted separately, two client references) to exercise procedural-item handling even on the "easy" fixture.
2. **`xyz_insurer_actuarial_ai.md`** — capability-gap fixture. Contains a mandatory requirement (deep actuarial-AI transformation experience) the corpus cannot support. Expected: that requirement resolves to `CAPABILITY_GAP`, and the run still completes for everything else rather than failing outright.
3. **`pqr_bank_procurement_heavy.md`** — procedural-heavy fixture. Signed declaration, strict formatting rules, two references, a separate commercial-response requirement, mixed in with real content requirements. Expected: every procedural item lands in the procedural checklist and none of them silently vanish or get treated as content requirements needing evidence.

---

## 11. Retrieval, Ranking & Conflict Detection

- Chunk corpus docs on Markdown headings (target ~700 chars, 100 overlap), preserving heading context and `source_path`.
- Generate 2–4 retrieval queries per checklist item; retrieve top-k per query; dedupe by `chunk_id`.
- Rerank: `final_score = 0.65*semantic + 0.20*lexical + 0.15*metadata_match`.
- **Thresholds are starting points, not settled constants** — `select_threshold≈0.68`, `partial_threshold≈0.58` (or your semantic-similarity equivalents) must be tuned in **Phase 0 calibration** (§16) against the actual seeded corpus and actual embedding model, using the known-good/known-bad pairs in §13 as ground truth. Do not treat the first numbers you pick as correct.
- No candidate clears threshold → explicit `GAP`, never a forced weak match. Cap retrieval refinement at 2 passes per requirement.
- **Conflict detection**, before drafting: same metric/same engagement with different numbers; same named person with different tenure; a document superseded by another. Any conflict → `EvidenceConflict`, `requires_human_resolution=True`. A conflicting claim can never auto-resolve to `SUPPORTED`.
- `usage_restriction="nda_restricted"` documents may inform internal judgment but must never be cited in client-facing draft text.

---

## 12. Web Enrichment (secondary, optional)

Internal evidence is the *only* authoritative source for VCG experience, credentials, methodology, and people. Web search may only supply client/industry background — never a VCG credential. Default `WEB_SEARCH_PROVIDER=mock`; the core demo must run correctly with web disabled.

---

## 13. Drafting

Draft section-by-section (Context → Approach → Credentials → Risks → Executive Summary last, synthesizing the rest), not one monolithic call. Grounding rules, enforced via system prompt and re-checked deterministically afterward — never trust the prompt alone:

1. Factual statements about VCG may only cite supplied evidence.
2. Never invent client names, results, percentages, credentials, or engagement durations.
3. Proposed future actions are phrased prospectively ("We propose...") and marked `requires_verification=False` / `FORWARD_LOOKING` — they are not historical claims and are not held to the same bar.
4. If evidence is insufficient for a requirement, write `[EVIDENCE GAP: ...]` — never fill it.
5. Sections needing human-only content (pricing, named staffing, commercial terms) get a `HUMAN INPUT REQUIRED` marker, never a plausible guess.

---

## 14. Claim Extraction

Decompose drafted prose into atomic, independently-checkable claims (an LLM step — decomposition only, not verification). Compound sentences must be split: *"VCG has 18 years of banking experience and reduced TAT by 18%"* → two separate claims, checked independently. Claims recognizably prospective ("we propose," "the team will") are marked `requires_verification=False`.

---

## 15. Deterministic Evidence-Consistency Verification (for supported claim types) — the core of the whole system

**No step in this pipeline may ask an LLM "is this claim true."** Verification is extractive and rule-based only.

**Precision note on what this actually checks:** call this "evidence-consistency verification," not "factual verification" in any demo narrative or documentation — the distinction matters. Embedding cosine similarity measures topical closeness, not logical entailment: a chunk can be highly semantically similar to a claim while still contradicting it on a non-numeric, non-attribution dimension the rules below don't explicitly check (e.g., a claim about *why* an outcome happened, when the evidence describes a different causal mechanism). The numeric-contradiction, attribution, and context-mismatch rules below catch every category of error the demo corpus is designed to surface — but the system does not do general-purpose logical fact-checking, and should never be described as if it does.

For each claim: (1) check citation exists → (2) validate cited evidence IDs are real and were actually selected → (3) fetch exact cited chunk text → (4) normalize both texts → (5) extract numeric tokens (percentages, currency, durations) via regex → (6) extract simple entities (capitalized names, known role/sector terms) → (7) compute lexical overlap on normalized significant tokens → (8) compute embedding cosine similarity → (9) check numeric consistency **within a ±20-token context window** around each number, not just "does this number appear somewhere in the corpus" → (10) check entity/attribution consistency **only if the claim contains a named entity** → (11) apply decision rules → (12) emit a `TraceabilityEntry` with a mechanically generated reason string.

**Numeric matching needs a rounding tolerance** (missing from the prior draft): treat two numbers as matching if they're equal after rounding to the same precision as the claim, or within a small absolute tolerance (e.g. ±0.5 percentage points) — otherwise "18%" vs. evidence's "18.2%" would wrongly fail.

**Corrected decision rules** (fixes the attribution bug in the prior draft — `attribution_valid` now defaults `True` and is only forced `False` by an actual mismatch, never by the mere absence of a named entity — and fixes an underspecified `PARTIAL` path: the geography-mismatch test case had no rule that could actually produce it):

`AtomicClaim` needs one more lightweight field: `context_qualifiers: list[str]` — simple keyword-extracted terms the claim asserts about *where/what kind* (e.g. "India", "Indian banks", "SME"). Compare these against the matched evidence's own `metadata` (`region`, `industry`, `subsector`). This is deliberately simple keyword matching, not NER — good enough to catch "claim says India, evidence is Southeast Asia."

```python
# attribution_valid defaults True (see schema). It is set False ONLY when
# the claim contains a named entity AND that entity's claimed fact contradicts
# the entity's own source document (e.g. "Rohan has 18 years" contradicts CV_002).
# A claim with zero named entities never touches this check — it stays True.

def context_mismatch(claim, evidence_match) -> bool:
    # True if the claim asserts a geography/industry/subsector qualifier that
    # the matched evidence's metadata contradicts (not merely fails to mention).
    for qualifier in claim.context_qualifiers:
        if evidence_match.metadata_contradicts(qualifier):
            return True
    return False

def decide(claim, evidence_match) -> VerificationStatus:
    if not claim.cited_evidence_ids:
        return GAP  # Rule A: no citation at all
    if evidence_match is None:
        return GAP  # Rule B: cited ID doesn't resolve to real, selected evidence
    if claim.numeric_tokens and evidence_match.numeric_match is False:
        return GAP  # Rule C: numeric contradiction — never overridable by high semantic similarity
    if claim.named_entities and not evidence_match.attribution_valid:
        return GAP  # Rule D: real attribution mismatch
    if context_mismatch(claim, evidence_match):
        return PARTIAL  # Rule E: e.g. claim says "Indian banks", evidence region is Southeast Asia —
                         # real, relevant evidence, but doesn't fully substantiate the claim as stated
    if (evidence_match.semantic_similarity >= SEM_SUPPORTED
            and evidence_match.lexical_overlap >= LEX_SUPPORTED
            and evidence_match.numeric_match is not False):
        return SUPPORTED  # Rule F — no longer blocked by an always-False attribution default
    if evidence_match.semantic_similarity >= SEM_PARTIAL and evidence_match.numeric_match is not False:
        return PARTIAL  # Rule G: weaker similarity alone, no hard contradiction
    return GAP
```

**Data-model clarification (many-to-many, not one-to-one):** a single RFP requirement can map to multiple claims across multiple sections, and a single claim can substantiate more than one requirement. `TraceabilityEntry` is the join record between them, not a unique key on either side. "Every requirement appears in the traceability matrix" (§4, §18) means every requirement has at least one corresponding row in the requirement-summary roll-up view — it does not mean each requirement or each claim maps to exactly one `TraceabilityEntry`. Don't let the schema or the UI enforce a uniqueness constraint that doesn't reflect this.

Confidence score uses the same corrected default:
```python
attribution_component = 1.0 if attribution_valid else 0.0   # True by default, so unaffected claims aren't penalized
confidence = 0.50*semantic + 0.25*lexical + 0.15*numeric_component + 0.10*attribution_component
```
A numeric contradiction can never be overridden into `SUPPORTED` regardless of confidence score.

**Mandatory test cases** (write these first, TDD-style, before implementing the rules):
- "reduced pilot approval TAT by 18%" + `CASE_BANK_001` → `SUPPORTED` (this must pass now that the attribution bug is fixed).
- "reduced lending TAT by 35%" + `CASE_BANK_001` (which says 18%) → `GAP`.
- "reduced lending TAT by 35%" + `DISTRACTOR_001` (which says 35%, unrelated context) → `GAP` — proves context-window matching, not naive number lookup.
- "Rohan Sen has 18 years of experience" (actually Ananya's number) → `GAP` — real attribution mismatch.
- "Ananya Mehta has 18 years of experience" → `SUPPORTED`.
- Zero cited evidence → `GAP` (orphan claim).
- Claim matched to `CASE_BANK_002` (SE Asia) asserting "delivered for Indian banks" → `PARTIAL`, not `SUPPORTED` — this exercises Rule E (`context_mismatch`) specifically, not the similarity thresholds; write this test against `context_mismatch()` directly so it can't pass by accident if thresholds shift later.
- A clearly prospective claim ("During weeks 1–2 the team will...") → `FORWARD_LOOKING`, not verified against history at all.

---

## 16. Build Phases (includes the calibration phase the prior drafts skipped)

**Phase 0 — Calibration (new, do this before trusting any threshold):** seed the corpus, embed the 8 test-case pairs from §15, print actual similarity/overlap scores, and set `SEM_SUPPORTED`/`SEM_PARTIAL`/`LEX_SUPPORTED` to values that correctly separate your known-good from known-bad pairs. Do not proceed on assumed numbers.

**Phase 1 — Scaffold, corpus, schemas:** repo tree, dependencies, Pydantic models, all 10 corpus docs, all 3 RFP fixtures, chunker, Chroma seeding.
Pass: `python scripts/seed_corpus.py && pytest tests/test_ingestion.py tests/test_retrieval.py -q`

**Phase 2 — Extraction + validation + planning:** decomposition, source-span validation, procedural/handling classification, response planner.
Pass: `pytest tests/test_requirement_validation.py tests/test_planner.py -q`

**Phase 3 — Retrieval + ranking + conflicts:** hybrid scoring, rejection reasons, conflict detector.
Pass: `pytest tests/test_reranking.py tests/test_conflict_detection.py -q`

**Phase 4 — Drafting + claim extraction:** section-by-section drafting, atomic claim decomposition. CLI reaches `atomic_claims`.

**Phase 5 — Deterministic verifier (TDD, red→green):** write all §15 test cases first, then implement numeric matcher (with rounding tolerance), context-window check, entity/attribution matcher (corrected default), similarity, final decision rules, traceability builder.
Pass: `pytest tests/test_numeric_matcher.py tests/test_fact_checker.py tests/test_traceability.py -q`

**Phase 6 — Review + persistence:** section-level approval, human-edit preservation, `audit_log` table, LangGraph checkpointer (or manual state snapshot if LangGraph was dropped per §0) for resumability.
Pass: `pytest tests/test_review_workflow.py tests/test_persistence.py -q`

**Phase 7 — Streamlit UI:** RFP → Execution → Evidence → Draft → Traceability (hero) → Review, in that order. Don't build Traceability last — it's the point of the demo.

**Phase 8 — Export:** Markdown, traceability CSV, DOCX (best-effort, fail gracefully if `python-docx` missing).

**Phase 9 — Demo hardening:** run `scripts/run_demo.py`, full `pytest -q`, and `streamlit run app.py` with web search disabled. Confirm the 18%/35% moment works live, not just in tests.

---

## 17. Tech Stack

`Python 3.11+ · LangGraph (or plain function pipeline, see §0) · Pydantic v2 · LiteLLM (Anthropic/OpenAI, model name from .env, never hardcoded) · ChromaDB (local persistence) · sentence-transformers/all-MiniLM-L6-v2 (or scikit-learn TF-IDF fallback if offline) · pypdf/PyMuPDF · Streamlit + pandas · python-docx · pytest · SQLite for audit_log + review_decisions`

---

## 18. Definition of Done

- [ ] Every extracted requirement carries a real, locatable source span; ungrounded ones are flagged, not passed downstream.
- [ ] Compound requirements split; procedural items preserved in their own checklist; capability gaps explicit.
- [ ] Corpus has exactly the 10 specified documents; all 3 RFP fixtures exist and behave as designed.
- [ ] Retrieval correctly favors banking/lending evidence and rejects the supply-chain and office-sustainability distractors, with thresholds calibrated (Phase 0), not guessed.
- [ ] Conflicting evidence is surfaced, never silently resolved.
- [ ] ≥5 proposal sections generated; each cites only selected evidence.
- [ ] All 8 §15 test cases pass, including the corrected 18%-supported case.
- [ ] Traceability matrix shows RFP source span → exact evidence chunk → claim → status for every material claim.
- [ ] Section-level approval works; direct human edits persist through later regenerations of other sections.
- [ ] No code path exports without every section at `APPROVED`; unresolved `GAP`s block export unless explicitly overridden with a recorded reason.
- [ ] System never sends/submits anything externally.
- [ ] Markdown + traceability CSV export work; DOCX works or fails gracefully.

---

## 19. Final Implementation Principle

The product succeeds if a Partner can click on any sentence in the draft and see, without needing to trust the model: *the client asked for this → here's the exact RFP text → here's why this evidence was chosen over the alternatives that were rejected → here's the exact source chunk → here's how the verifier independently checked it → here's who approved it.* If that chain is real and inspectable — not narrated, not simulated — the prototype has done its job.
