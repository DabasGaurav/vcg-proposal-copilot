"""Produce the presentation run with the local model and save it for instant reload.

A full local generation pass takes minutes, which is too slow to perform live.
This records a real end-to-end Ollama run and persists it, so the presenter can
reopen it instantly and then perform one short live action (a section
regeneration, or qualification of a second tender) on top of it.

    LLM_PROVIDER=ollama LLM_MODEL=gemma3:latest python scripts/record_demo_run.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from pipeline.graph import continue_approved_pipeline, run_pipeline  # noqa: E402
from pipeline.qualification import record_decision  # noqa: E402
from services import costing  # noqa: E402
from services.vectorstore import VectorStore  # noqa: E402

RUN_ID = "demo-local"
FIXTURE = "abc_bank_lending_transformation.md"


def main() -> int:
    config.ensure_dirs()
    VectorStore.ensure_seeded()
    print(f"provider={config.LLM_PROVIDER} model={config.LLM_MODEL} ctx={config.OLLAMA_NUM_CTX}")

    t0 = time.time()
    state = run_pipeline(str(config.FIXTURE_DIR / FIXTURE), run_id=RUN_ID, persist=True)
    q = state.get("qualification", {})
    print(f"[{time.time()-t0:5.0f}s] qualify: fit={q.get('score')} -> {q.get('recommendation')}")

    record_decision(state, "BID", "Practice Lead (demo)",
                    "Evidence coverage adequate; proceeding to draft.")
    state = continue_approved_pipeline(state, persist=True)
    print(f"[{time.time()-t0:5.0f}s] drafted, verified and traced")

    d = state["proposal_draft"]
    print(f"\nsections={len(d.sections)} substantiated={d.supported_claim_count} "
          f"partial={d.partial_claim_count} unsubstantiated={d.gap_claim_count}")

    c = costing.session_cost(state.get("model_usage") or [])
    print(f"calls={c['calls']} in={c['input_tokens']} out={c['output_tokens']} "
          f"gen={c['seconds']:.0f}s local=Rs{c['local_inr']:.3f} "
          f"hosted-equiv=Rs{c['api_equivalent_inr']:.2f}")

    orphans = [e for e in state["overall_traceability"]
               if e.claim_id != "(none)" and not e.matched_evidence_id]
    print(f"claims citing nothing resolvable: {len(orphans)}")
    print(f"\nSaved as run '{RUN_ID}' -- reopen it from the sidebar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
