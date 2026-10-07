"""Adversarial stress test of the deterministic verifier.

Drafts a claim, cites a REAL selected passage, and runs the real verifier. Every
case marked FALSE is a misstatement of what the cited passage says; the only
outcome this product cannot have is one of them reaching SUPPORTED.

    ./.venv/bin/python scripts/stress_test.py

Run it after any change to services/text.py or pipeline/verification.py. The
findings it produced are pinned as tests in tests/test_stress_bypasses.py; this
script is for probing new attack shapes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from models.schemas import AtomicClaim, EvidenceItem  # noqa: E402
from pipeline.verification import verify_claim  # noqa: E402
from services.mock_llm import decompose_claims  # noqa: E402
from services.vectorstore import VectorStore  # noqa: E402

TRUE, FALSE = "TRUE", "FALSE"


def build_index() -> dict[str, EvidenceItem]:
    store = VectorStore.load()
    index: dict[str, EvidenceItem] = {}
    for ch in store.chunks:
        meta = ch.metadata or {}
        index[ch.chunk_id] = EvidenceItem(
            evidence_id=ch.chunk_id, source_id=ch.document_id, chunk_id=ch.chunk_id,
            title=meta.get("title") or ch.document_id, chunk_text=ch.text,
            category=meta.get("category", "CASE_STUDY"), metadata=meta,
            source_path=str(ch.source_path), relevance_score=0.9, selected=True,
        )
    return index


def main() -> int:
    config.ensure_dirs()
    VectorStore.ensure_seeded()
    index = build_index()
    sem = VectorStore.load().semantic_similarity

    tat = next(e for e in index.values() if "turnaround" in e.chunk_text.lower()
               and re.search(r"18\s*(percent|%)", e.chunk_text, re.I))
    cv = next(e for e in index.values() if "ananya" in e.chunk_text.lower())

    cases = [
        # truth,  label,                 drafted sentence,                          cited passage
        (FALSE, "inflated figure",      "VCG reduced turnaround time by 35 percent.", tat),
        (FALSE, "deflated figure",      "VCG reduced turnaround time by 8 percent.", tat),
        (FALSE, "figure in words",      "VCG reduced turnaround time by thirty-five percent.", tat),
        (FALSE, "direction flipped",    "VCG increased turnaround time by 18 percent.", tat),
        (FALSE, "percent -> pp",        "VCG reduced turnaround time by 18 percentage points.", tat),
        (FALSE, "'more than' hedge",    "VCG reduced turnaround time by more than 18 percent.", tat),
        (FALSE, "'up to' hedge",        "VCG reduced turnaround time by up to 40 percent.", tat),
        (FALSE, "range claim",          "VCG reduced turnaround time by 30 to 40 percent.", tat),
        (FALSE, "superlative",          "VCG achieved the largest turnaround reduction in the Indian market.", tat),
        (FALSE, "universal quantifier", "VCG has reduced turnaround time by 18 percent for every lending client.", tat),
        (FALSE, "metric swapped",       "VCG reduced loan default rates by 18 percent.", tat),
        (FALSE, "wrong person",         "Rohan Sen, Partner, has 18 years of experience in banking and lending operations.", cv),
        (FALSE, "tenure inflated",      "Ananya Mehta, Partner, has 28 years of experience in banking and lending operations.", cv),
        (FALSE, "geography swapped",    "In a retail lending engagement in Europe, VCG reduced turnaround time by 18 percent.", tat),
        (FALSE, "negation",             "VCG recorded no reduction in turnaround time.", tat),
        (FALSE, "invented currency",    "VCG delivered Rs 240 crore of savings.", tat),
        (FALSE, "wrong credential",     "VCG is certified to ISO 9001.", tat),
        (FALSE, "invented aggregate",   "VCG has completed 40 lending transformations.", tat),
        # Controls: these ARE supported by the cited passage and must pass.
        (TRUE,  "control: figure",      "VCG reduced pilot approval turnaround time by 18 percent.", tat),
        (TRUE,  "control: tenure",      "Ananya Mehta, Partner, has 18 years of experience in banking and lending operations.", cv),
        (TRUE,  "control: unnamed",     "Our Partner has 18 years of experience in banking and lending operations.", cv),
    ]

    failures = 0
    for truth, label, sentence, ev in cases:
        for raw in decompose_claims("Relevant Experience & Credentials",
                                    f"{sentence} [[ev:{ev.evidence_id}]]"):
            claim = AtomicClaim(**raw)
            result = verify_claim(claim, index, sem)
            status = result["status"].value
            bad = ((truth is FALSE and status == "SUPPORTED")
                   or (truth is TRUE and status != "SUPPORTED"))
            flag = ""
            if bad:
                failures += 1
                flag = ("  <-- FALSE CLAIM REACHED SUPPORTED" if truth is FALSE
                        else "  <-- TRUE CLAIM WAS BLOCKED")
            print(f"{truth:5} {label:22} [{status:16}] {claim.claim_text[:58]}{flag}")
            if bad:
                print(f"{'':46}{result['reason'][:150]}")

    print(f"\n{failures} failure(s) across {len(cases)} cases")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
