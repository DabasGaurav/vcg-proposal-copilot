"""Phase 9 -- end to end on all three fixtures."""
from __future__ import annotations

import config
from models.schemas import RequirementHandling, VerificationStatus
from pipeline.graph import continue_approved_pipeline, run_pipeline
from pipeline.qualification import record_decision


def approved_run(path):
    state = run_pipeline(str(path), persist=False)
    record_decision(state, "BID", "fixture practice lead", "Test fixture")
    return continue_approved_pipeline(state, persist=False)


def test_abc_happy_path_end_to_end(abc_state):
    assert abc_state["rfp_data"].client and "Bank" in abc_state["rfp_data"].client
    assert len(abc_state["proposal_draft"].sections) >= 5
    assert abc_state["proposal_draft"].supported_claim_count >= 1
    assert abc_state["proposal_draft"].gap_claim_count >= 1
    assert abc_state["procedural_checklist"]  # english-only / pricing separate / refs


def test_xyz_capability_gap_run_still_completes():
    st = approved_run(config.FIXTURE_DIR / "xyz_insurer_actuarial_ai.md")
    handlings = {r.handling for r in st["rfp_data"].requirements}
    assert RequirementHandling.CAPABILITY_GAP in handlings
    assert st["proposal_draft"] is not None            # run did not fail outright
    assert any(e.verification_status == VerificationStatus.GAP
               for e in st["overall_traceability"])


def test_pqr_procedural_items_all_land_in_checklist():
    st = approved_run(config.FIXTURE_DIR / "pqr_bank_procurement_heavy.md")
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


def test_out_of_domain_tender_gets_no_banking_prose(tmp_path):
    """The drafter must not assert lending content on a tender from another
    sector. It previously emitted "branch change fatigue", a lending methodology
    and "VCG reduced lending turnaround time by 35 percent" on a hospital RFP,
    because those sentences were hard-coded."""
    rfp = tmp_path / "hospital.md"
    rfp.write_text(
        "# RFP — Hospital Revenue Cycle\n\n## Client\nMeridian Health, a hospital network.\n\n"
        "## Background\nLong payer settlement cycles.\n\n"
        "## Timeline\nThe engagement must be completed in 14 weeks.\n\n"
        "## Scope of Work\n- Diagnose the revenue cycle end to end.\n\n"
        "## Evaluation Criteria\n"
        "- Demonstrated experience transforming hospital revenue cycle operations.\n"
        "- Evidence of greater than 25 percent reduction in days-sales-outstanding.\n\n"
        "## Procedural Requirements\n- Proposals must be submitted in English.\n"
    )
    st = approved_run(rfp)
    draft = " ".join(st["draft_sections"].values()).lower()
    for leaked in ("branch change fatigue", "credit-risk appetite", "auto-decisioning",
                   "lending turnaround", "ananya", "rohan", "retail lending redesign"):
        assert leaked not in draft, f"banking prose leaked onto a hospital tender: {leaked!r}"


def test_unsupported_threshold_claim_uses_the_tender_s_own_metric(tmp_path):
    """When the tender demands a threshold the evidence cannot meet, the
    resulting unsupported claim must be about the metric the tender asked for --
    and must still be caught."""
    from models.schemas import VerificationStatus

    rfp = tmp_path / "hospital.md"
    rfp.write_text(
        "# RFP\n\n## Client\nMeridian Health.\n\n## Background\nSlow settlement.\n\n"
        "## Timeline\nCompleted in 14 weeks.\n\n## Scope of Work\n- Diagnose the cycle.\n\n"
        "## Evaluation Criteria\n"
        "- Evidence of greater than 25 percent reduction in days-sales-outstanding.\n\n"
        "## Procedural Requirements\n- English only.\n"
    )
    st = approved_run(rfp)
    draft = " ".join(st["draft_sections"].values())
    assert "days-sales-outstanding" in draft
    assert "30 percent" in draft                      # the tender's 25% + margin
    blocked = [e for e in st["overall_traceability"]
               if "days-sales-outstanding" in e.claim_text
               and e.verification_status == VerificationStatus.GAP]
    assert blocked, "an uncited threshold claim must be rejected"
