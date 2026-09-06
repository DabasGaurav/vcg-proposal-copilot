"""Phase 0 -- Calibration (SPEC Section 16).

Embed the SPEC Section 15 known-good / known-bad (claim, evidence) pairs against
the ACTUAL seeded corpus and ACTUAL embedding backend, print the real
semantic / lexical scores the verifier will see (claim vs the *best matching
chunk* of the cited document, not the whole doc), then choose
SEM_SUPPORTED / SEM_PARTIAL / LEX_SUPPORTED that separate good from bad and
WRITE them into .env.

    python scripts/seed_corpus.py
    python scripts/calibrate.py            # prints + writes .env
    python scripts/calibrate.py --dry-run  # prints only
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from services.text import lexical_overlap  # noqa: E402
from services.vectorstore import VectorStore  # noqa: E402

# (label, claim, cited source_id, expected verdict)
PAIRS = [
    ("good", "VCG reduced pilot approval turnaround time by 18 percent", "CASE_BANK_001", "SUPPORTED"),
    ("bad",  "VCG reduced lending turnaround time by 35 percent", "CASE_BANK_001", "GAP (numeric)"),
    ("bad",  "VCG reduced lending turnaround time by 35 percent", "DISTRACTOR_001", "GAP (context)"),
    ("bad",  "Rohan Sen has 18 years of experience", "CV_001", "GAP (attribution)"),
    ("good", "Ananya Mehta has 18 years of experience in banking and lending", "CV_001", "SUPPORTED"),
    ("bad",  "VCG delivered a supply chain operating model transformation for a bank", "CASE_SC_001", "distractor"),
    ("mid",  "VCG delivered lending improvement for Indian banks", "CASE_BANK_002", "PARTIAL (geography)"),
    ("good", "VCG uses a phased Diagnose Design Pilot Scale methodology to redesign lending operations", "METHOD_001", "SUPPORTED"),
]

_KEYS = ("SEM_SUPPORTED", "SEM_PARTIAL", "LEX_SUPPORTED")


def _best_chunk_scores(store: VectorStore, claim: str, source_id: str) -> tuple[float, float]:
    best_sem, best_lex = 0.0, 0.0
    for ch in store.chunks:
        if ch.document_id != source_id:
            continue
        sem = store.semantic_similarity(claim, ch.text)
        if sem > best_sem:
            best_sem = sem
            best_lex = lexical_overlap(claim, ch.text)
    return best_sem, best_lex


def _write_env(values: dict[str, float]) -> None:
    env = config.ROOT / ".env"
    lines = env.read_text().splitlines() if env.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in values.items():
        if key not in seen:
            out.append(f"{key}={val}")
    env.write_text("\n".join(out) + "\n")


def main() -> int:
    dry = "--dry-run" in sys.argv
    store = VectorStore.load()

    print(f"backend={store.embedder.backend}  dim={store.embedder.dim}\n")
    print(f"{'label':<5} {'expected':<22} {'semantic':>9} {'lexical':>8}  claim")
    print("-" * 96)
    goods, bads, mids = [], [], []
    for label, claim, src, exp in PAIRS:
        sem, lex = _best_chunk_scores(store, claim, src)
        print(f"{label:<5} {exp:<22} {sem:>9.3f} {lex:>8.3f}  {claim[:42]}")
        {"good": goods, "bad": bads, "mid": mids}[label].append((sem, lex))

    min_good_sem = min(s for s, _ in goods)
    max_bad_sem = max(s for s, _ in bads)
    min_good_lex = min(x for _, x in goods)

    if min_good_sem > max_bad_sem:
        sem_supported = round((min_good_sem + max_bad_sem) / 2, 3)
    else:
        # overlap -> lean toward recall; the numeric/attribution/context rules
        # (C/D/E) do the heavy lifting, F/G is the similarity fallback.
        sem_supported = round(min_good_sem * 0.85, 3)
    values = {
        "SEM_SUPPORTED": max(sem_supported, 0.05),
        "SEM_PARTIAL": round(max(sem_supported * 0.5, 0.02), 3),
        "LEX_SUPPORTED": round(min_good_lex * 0.8, 3),
    }

    print("\ngood semantic range : "
          f"{min_good_sem:.3f} – {max(s for s, _ in goods):.3f}")
    print(f"bad  semantic max   : {max_bad_sem:.3f}")
    print("\nchosen thresholds:")
    for k, v in values.items():
        print(f"  {k}={v}")

    if dry:
        print("\n--dry-run: .env not modified")
        return 0
    _write_env(values)
    print(f"\nwrote {', '.join(_KEYS)} -> {config.ROOT / '.env'}")
    print("re-run `pytest -q` and `python scripts/run_demo.py` to confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
