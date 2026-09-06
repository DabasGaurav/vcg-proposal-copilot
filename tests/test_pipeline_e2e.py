"""Phase 9 -- end to end on all three fixtures."""
from __future__ import annotations

import config
from models.schemas import RequirementHandling, VerificationStatus
from pipeline.graph import run_pipeline


def test_abc_happy_path_end_to_end(abc_state):
    assert abc_state["rfp_data"].client and "Bank" in abc_state["rfp_data"].client
    assert len(abc_state["proposal_draft"].sections) >= 5
    assert abc_state["proposal_draft"].supported_claim_count >= 1
    assert abc_state["proposal_draft"].gap_claim_count >= 1
    assert abc_state["procedural_checklist"]  # english-only / pricing separate / refs


def test_xyz_capability_gap_run_still_completes():
    st = run_pipeline(str(config.FIXTURE_DIR / "xyz_insurer_actuarial_ai.md"),
                      persist=False)
    handlings = {r.handling for r in st["rfp_data"].requirements}
    assert RequirementHandling.CAPABILITY_GAP in handlings
    assert st["proposal_draft"] is not None            # run did not fail outright
    assert any(e.verification_status == VerificationStatus.GAP
               for e in st["overall_traceability"])


def test_pqr_procedural_items_all_land_in_checklist():
    st = run_pipeline(str(config.FIXTURE_DIR / "pqr_bank_procurement_heavy.md"),
                      persist=False)
    joined = " ".join(st["procedural_checklist"]).lower()
    for token in ("declaration", "arial", "reference", "commercial response", "portal"):
        assert token in joined
    for item in st["checklist"]:
        assert "signed vendor declaration" not in item.requirement_text.lower()


def test_demo_script_exits_zero():
    import subprocess, sys
    r = subprocess.run([sys.executable, "scripts/run_demo.py"],
                       cwd=str(config.ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "18% claim SUPPORTED : PASS" in r.stdout
    assert "35% claim caught GAP: PASS" in r.stdout
