# Pre-registered expectations — five new RFPs

Written before any run. Derived only from the corpus contents, not from output.

## Corpus ground truth (the only facts that exist)

| Doc | Domain / region | Figures it actually records |
|---|---|---|
| CASE_BANK_001 | banking, retail_lending, India | turnaround -18%, processing effort -22%, manual handoffs -30%, credit loss unchanged |
| CASE_BANK_002 | banking, sme_lending, SE Asia | rework loops -25%, RM doc-chasing -17%; **explicitly NO turnaround figure** |
| CASE_SC_001 | consumer_goods, supply_chain, India | forecast accuracy +12 points, inventory cover -9 days |
| CV_001 | banking, retail_lending, India | Ananya Mehta, Partner, 18 years |
| CV_002 | banking, sme_lending, India | Rohan Sen, Principal, 12 years, SME underwriting |
| DISTRACTOR_001 | facilities, India | electricity -35%, paper -40% |
| METHOD_001 | lending_operations, global | methodology only, no results |
| METHOD_002 | core_banking, global | **diagnostic only; says it must not be cited as delivery evidence** |
| PROP_001 / PROP_002 | lending / credit ops | winning-proposal patterns, no results |

No corpus document records: a core banking replacement delivery, any Europe
engagement, any Middle East engagement, or a supply-chain CV.

## Hard invariants — a breach of any of these is a FAILURE

- **H1** No SUPPORTED claim may contain a figure that is absent from its cited passage.
- **H2** Every `[[ev:...]]` in the rendered draft resolves to selected evidence.
- **H3** No SUPPORTED claim of a turnaround-time result may cite CASE_BANK_002.
- **H4** DISTRACTOR_001 figures (35% electricity, 40% paper) never appear as delivery evidence.
- **H5** `supported/partial/gap_claim_count` equal the distinct claim counts.
- **H6** Export is blocked for all five (nothing approved).
- **H7** No section fabricates domain prose where evidence is absent; it returns EVIDENCE GAP.

## Per-RFP predictions

### 1. nutriva_supply_chain_planning (India, consumer goods, supply chain)
Evidence exists for the *case* (CASE_SC_001) but there is **no supply-chain CV**.
- fit ≤ 50; recommendation REVIEW or NO_BID_REVIEW
- Experience section *may* substantiate forecast accuracy +12 points / inventory -9 days
- **Team section must NOT offer Ananya Mehta or Rohan Sen as supply-chain experts.**
  Predicted: EVIDENCE GAP. Confidence only ~60% — the CV docs are banking-tagged,
  so metadata match should exclude them, but if they are selected the drafter
  names whoever is in the pool. I expect this is the likeliest failure here.
- SUPPORTED claims: 0–2. False SUPPORTED expected: 0.

### 2. merantau_sme_underwriting (SE Asia, SME underwriting)
The best-matched RFP of the five: CASE_BANK_002 + CV_002 + PROP_002 all fit.
- fit ≥ 50 — expected the **highest** of the five; BID_REVIEW or REVIEW
- Should substantiate: Rohan Sen 12 years SME underwriting; rework loops -25%
- **No turnaround-time claim may be SUPPORTED** (H3). CASE_BANK_002 records none.
- A claim qualified "Southeast Asia" cited to CV_002 (region: India) *should*
  trip Rule E → PARTIAL. That would be correct behaviour, not a failure.
- SUPPORTED claims: 1–3. False SUPPORTED expected: 0.

### 3. helvetia_core_platform_delivery (Europe, core banking replacement)
Mandatory requirement the corpus cannot meet. METHOD_002 is the trap.
- fit 0; NO_BID_REVIEW (matching the xyz_insurer unmet-mandatory behaviour)
- **Predicted FAILURE, ~50% likely:** nothing in the code reads METHOD_002's
  "must not be cited as delivered lending/core transformation" note. If
  METHOD_002 is selected, a sentence like "VCG has relevant delivery experience:
  Core Banking Diagnostic Framework" could reach SUPPORTED on lexical/semantic
  grounds — a diagnostic framework presented as delivery evidence. The corpus
  warns against exactly this and the warning is unenforced.
- "europe" IS in the context-qualifier catalog, so Europe-qualified claims
  should trip Rule E against India/global evidence → PARTIAL.
- SUPPORTED claims: 0–1. If 1, I expect it to be the METHOD_002 mislabel.

### 4. apex_aggressive_thresholds (India, 45% / 50% / 60% demanded)
Corpus maxima are 18% / 22% / 30%. All three thresholds unmeetable.
- fit 25–75 (strong domain match, unmet thresholds)
- **The hero mechanism at three thresholds:** the drafter should emit overclaims
  at 50 / 55 / 65 percent and the verifier must GAP every one on
  `numeric=CONTRADICTED`. Expect ≥1 such GAP, and 0 SUPPORTED claims containing
  50, 55 or 65 percent.
- Risk: `_threshold_pct` may not parse "at least 45 percent" / "more than 60
  percent". If it misses, no overclaim is generated — a safe failure (no false
  claim) but the test then does not exercise Rule C. I will report which happened.
- SUPPORTED claims: 1–4 (true ones about 18%/22%/30% and the CV). False: 0.

### 5. gulfstar_word_thresholds (Middle East, word-number thresholds)
Three traps: a 20% threshold against a true 18%; a 15-percentage-point forecast
accuracy threshold whose only source is a *supply-chain* document; and a region
the corpus has never worked in.
- fit 0–50
- **No SUPPORTED claim of >20% turnaround** (truth is 18%).
- **No SUPPORTED claim of a 15-point forecast accuracy gain**, and CASE_SC_001's
  +12 points must not be cited as banking delivery evidence.
- **Predicted FAILURE:** `extract_context_qualifiers` has catalog
  ["india","indian","southeast asia","south asia","europe","us","sme","retail",
  "consumer","corporate"] — **"middle east" is absent**. So a claim qualified
  "in the Middle East" will not be checked for geography mismatch and Rule E
  cannot fire. I expect an unchallenged Middle East claim if the drafter writes one.
- Word-number thresholds ("twenty percent") likely won't be parsed by
  `_threshold_pct` → no overclaim. Safe failure.
- SUPPORTED claims: 0–2. False SUPPORTED expected: 0, but the Middle East
  qualifier gap is a real hole even if no false figure appears.

## Summary of predicted failures

1. **Helvetia / METHOD_002** — a diagnostic framework citable as delivery evidence (~50%).
2. **GulfStar / Middle East** — region absent from the qualifier catalog, so Rule E cannot fire (high confidence).
3. **Nutriva / banking CVs** — banking Partners possibly offered for a supply-chain bid (~40%).

Everything else I expect to hold.

---

# Measured outcome

Run deterministically (`LLM_PROVIDER=mock`) on 2026-10-07 against commit `698209c`
plus the two gate tests. No source file was modified for this test.

| RFP | predicted fit | actual | predicted rec | actual | false SUPPORTED |
|---|---|---|---|---|---|
| nutriva_supply_chain_planning | ≤50 | **33** | REVIEW / NO_BID | REVIEW | 0 |
| merantau_sme_underwriting | ≥50, highest | **67** (3rd) | BID/REVIEW | BID_REVIEW | 0 |
| helvetia_core_platform_delivery | **0** | **75** | **NO_BID_REVIEW** | **BID_REVIEW** | **1** |
| apex_aggressive_thresholds | 25–75 | **100** | — | BID_REVIEW | 0 |
| gulfstar_word_thresholds | 0–50 | **50** | — | REVIEW | 0 |

Hard invariants H1–H7: **all held on all five RFPs.**

## Predictions that were right

- **Nutriva**: banking CVs were correctly kept out of a supply-chain bid. Only
  CASE_SC_001 was selected; Team & Credentials returned EVIDENCE GAP rather than
  offering Ananya Mehta as a supply-chain expert. This was the ~40% risk I flagged;
  it held.
- **Merantau**: Rohan Sen's 12 years and the SE Asia SME engagement both
  substantiated. No turnaround-time claim was made or substantiated (H3), which is
  correct — CASE_BANK_002 records none and says so.
- **Apex, the hero mechanism at three thresholds**: overclaims emitted at exactly
  50 / 55 / 65 percent (threshold + 5) against corpus truths of 18 / 22 / 30, and
  all three rejected with `numeric=CONTRADICTED`. Rule C fired three times in one run.
- **METHOD_002 trap**: confirmed, as predicted at ~50%.
- **GulfStar geography**: confirmed. Word-number thresholds unparsed, as predicted.

## Predictions that were wrong

- I predicted Merantau would score highest. It was third (67); Apex scored 100 and
  Helvetia 75 — both on RFPs the corpus cannot satisfy. The fit score does not rank
  by evidence adequacy, so my reasoning about it was wrong.
- I predicted Helvetia would score 0 / NO_BID_REVIEW on its unmet mandatory
  requirement. It scored 75 / BID_REVIEW. See finding 1.
- I predicted Apex at 25–75. It scored 100 — the maximum — on an RFP whose three
  headline criteria its own verifier contradicts.

## Findings

### 1. Bid/no-bid is driven by retrieval coverage, not substantiation (most serious)

`qualification.run` computes `score = 100 * covered / evidence_items`, where
`covered` means *any* passage was selected for that checklist item. It never
consults the verifier. So:

- **Apex: fit=100 / BID_REVIEW.** `CHK-008` ("at least 45 percent turnaround-time
  improvement") is counted as covered by CASE_BANK_001, which records 18 percent,
  and CASE_BANK_002, which records no turnaround figure at all. Minutes later the
  same pipeline rejects all three threshold claims as contradicted. The stage that
  decides whether to spend money bidding scores it 100/100.
- **Helvetia: the mandatory gate was satisfied by the one document that disclaims
  it.** `CHK-012` is `mandatory=True` — "demonstrated prior experience delivering a
  completed core banking platform replacement" — and is marked covered by
  METHOD_002, whose own text reads: "This framework demonstrates diagnostic
  capability only. It is not a record of delivered lending transformation and must
  not be cited as evidence that VCG has executed a past lending delivery
  engagement." A mandatory gap is only raised when *nothing* was retrieved.

### 2. A methodology document is assertable as delivery experience

`services/mock_llm.py:598` emits, for any selected evidence:

    f"VCG has relevant delivery experience: {top['title']}."

with no check on the document's `category`. METHOD_002's category is `METHODOLOGY`.
The drafted sentence is therefore "VCG has relevant delivery experience: Core
Banking Diagnostic Framework", cited to METHOD_002 and attached to the mandatory
requirement — and the verifier returns **SUPPORTED**, because the title is
literally present in the cited text. The corpus warned against exactly this and
nothing reads the warning.

### 3. Rule E's geography check is an allow-list covering ten strings

`extract_context_qualifiers` matches only india, indian, southeast asia, south
asia, europe, us, sme, retail, consumer, corporate. Identical claims against the
same *Indian* case study:

| claim | verdict |
|---|---|
| "In a comparable **Middle East** engagement, VCG reduced turnaround time by 18 percent." | **SUPPORTED** |
| "In a comparable **Europe** engagement, ..." | PARTIAL |
| "In a comparable **Southeast Asia** engagement, ..." | PARTIAL |

Middle East, Gulf, UAE, Africa and Latin America all extract no qualifier, so the
geography rule cannot fire for most of the world. Latent in the GulfStar run only
because its Experience section gapped first.

### 4. Two number parsers disagree

`_threshold_pct` parses "at least 45 percent" and "more than 60 percent" but
returns `None` for "more than twenty percent" and "at least fifteen percentage
points", while `extract_numeric_tokens` handles all four. A word-number threshold
silently stops being a threshold, so the RFP's bar is never compared to the
evidence. Safe direction — no fabrication — but the criterion goes unchecked.
