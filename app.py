"""Proposal Copilot -- Streamlit front end (SPEC Phase 7).

Tabs:
    Overview -> Traceability -> Evidence -> Draft -> Requirements -> Execution -> Review

Overview answers "what happened, and is this safe to send?".
Traceability is the proof: for any claim, the full Requirement -> exact RFP quote
-> why this evidence (and why the rejected ones were rejected) -> exact source
chunk -> deterministic verifier result -> human decision chain, inspectable
rather than narrated.

Presentation tokens and components live in ui.py.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

import config
import ui
from models.schemas import ReviewDecision, VerificationStatus
from pipeline import export, review
from pipeline.graph import load_run, run_pipeline
from pipeline.traceability import evidence_display_id
from services.persistence import get_store
from services.vectorstore import VectorStore

st.set_page_config(page_title="Proposal Copilot", layout="wide",
                   page_icon="📝", initial_sidebar_state="expanded")
config.ensure_dirs()


@st.cache_resource(show_spinner="Building the evidence knowledge base…")
def _bootstrap():
    """First-load setup so a hosted deploy needs no manual seed step."""
    VectorStore.ensure_seeded()
    return True


_bootstrap()
st.markdown(ui.CSS, unsafe_allow_html=True)
H = {"unsafe_allow_html": True}


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 📝 Proposal Copilot")
    st.caption("RFP → source-grounded, review-ready proposal")
    st.divider()

    fixtures = sorted(p.name for p in config.FIXTURE_DIR.glob("*.md"))
    choice = st.selectbox("Demo RFP", fixtures,
                          help="Four scenarios: happy path, capability gap, "
                               "procurement-heavy, and an RFP with no evaluation rubric.")
    uploaded = st.file_uploader("…or upload your own RFP", type=["md", "txt", "pdf"])
    web = st.checkbox("Web enrichment (industry context only)", value=False)

    if st.button("▶  Run pipeline", type="primary", use_container_width=True):
        if uploaded is not None:
            dest = config.DATA_DIR / f"upload_{uploaded.name}"
            dest.write_bytes(uploaded.getbuffer())
            rfp_path = str(dest)
        else:
            rfp_path = str(config.FIXTURE_DIR / choice)
        with st.spinner("Running RFP → approved-proposal pipeline…"):
            try:
                st.session_state.state = run_pipeline(rfp_path, web_search=web)
                st.session_state.rfp_name = choice if uploaded is None else uploaded.name
            except Exception as exc:                       # keep the app usable
                st.session_state.state = None
                st.error(f"Pipeline failed: {exc}")

    if st.session_state.get("state"):
        s = st.session_state.state
        d = s["proposal_draft"]
        st.markdown(
            f'<div class="pills">{ui.pill("SUPPORTED", str(d.supported_claim_count))}'
            f'{ui.pill("PARTIAL", str(d.partial_claim_count))}'
            f'{ui.pill("GAP", str(d.gap_claim_count))}</div>', **H)
        st.caption(f"run `{s['run_id'][:12]}` · {len(s['overall_traceability'])} matrix rows")

    st.divider()
    st.markdown("**Resume a run**")
    try:
        prev = get_store().list_runs()
    except Exception:
        prev = []
    if prev:
        pick = st.selectbox("Persisted runs", [r["run_id"] for r in prev],
                            format_func=lambda r: f"{r[:12]}…", label_visibility="collapsed")
        if st.button("↺  Load run", use_container_width=True):
            try:
                st.session_state.state = load_run(pick)
                st.session_state.rfp_name = st.session_state.state.get("rfp_filename", pick)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load: {exc}")
    else:
        st.caption("No persisted runs yet.")


# --------------------------------------------------------------------------- #
# Landing (no run yet)
# --------------------------------------------------------------------------- #
state = st.session_state.get("state")
if not state:
    st.markdown(
        """
        <div class="eyebrow">VCG · Proposal Copilot</div>
        <div class="hero-h1">Every claim in the proposal,<br>traceable to its source.</div>
        <div class="hero-sub">
          Drop in an RFP. Get a review-ready draft where every factual statement links
          to the exact evidence it came from — and any claim the evidence doesn't
          support is flagged before a partner ever sees it.
        </div>
        """, **H)
    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.markdown(
        '<div class="card"><h4>Requirement → Evidence → Draft</h4>'
        '<p>A live traceability matrix. Click any sentence and see the RFP line it '
        'answers, the source chunk it was written from, and the candidates that were '
        'rejected — with reasons.</p></div>', **H)
    c2.markdown(
        '<div class="card"><h4>Deterministic verification</h4>'
        '<p>Numeric, attribution and geography checks — rule-based, not an LLM '
        'grading its own output. A contradicted number can never pass as '
        '“supported”.</p></div>', **H)
    c3.markdown(
        '<div class="card"><h4>Human approval gate</h4>'
        '<p>No code path reaches an export without a reviewer approving every '
        'section. Unsupported claims block the export until resolved or overridden '
        'with a recorded reason.</p></div>', **H)

    st.write("")
    st.markdown(
        '<div class="flow">'
        '<span>RFP</span><span>extract + validate</span><span>retrieve evidence</span>'
        '<span>rank / reject</span><span>draft</span><span>decompose claims</span>'
        '<span>verify</span><span>traceability</span>'
        '<span class="gate">human review</span><span>export</span></div>', **H)
    st.markdown(
        '<div class="cta">← Pick a demo RFP in the sidebar and press '
        '<b>Run pipeline</b>. Try <b>abc_bank_lending_transformation</b> first — '
        'it contains a claim the evidence can\'t support.</div>', **H)
    st.stop()


# --------------------------------------------------------------------------- #
# Derived figures used across tabs
# --------------------------------------------------------------------------- #
draft = state["proposal_draft"]
entries = state["overall_traceability"]
summary = state.get("requirement_summary", [])
export_ok, export_reasons = review.can_export(state)

n_selected = sum(len(v) for k, v in state["selected_evidence"].items() if k != "__pool__")
n_rejected = sum(len(v) for v in state["rejected_evidence"].values())
n_gap_rows = sum(1 for e in entries if e.verification_status == VerificationStatus.GAP)
n_approved = sum(1 for s in draft.sections if s.review_status == ReviewDecision.APPROVED)
coverage = Counter(s["rollup_status"] for s in summary)
usage = Counter(evidence_display_id(e.matched_evidence_id)
                for e in entries if e.matched_evidence_id)

_client = (state["rfp_data"].client or "Untitled RFP").rstrip(".")
st.markdown(
    f'<div class="eyebrow">Proposal · review status {state.get("review_status","PENDING")}</div>'
    f'<div class="hero-h1" style="font-size:1.95rem;margin:.2rem 0 .45rem;">{_client}</div>', **H)
st.caption(f"`{st.session_state.get('rfp_name','')}` · run `{state['run_id'][:12]}` · "
           f"{len(state['checklist'])} evidence needs · "
           f"{len(state['procedural_checklist'])} procedural items")

tab_over, tab_trace, tab_ev, tab_draft, tab_req, tab_exec, tab_review = st.tabs(
    ["📊  Overview", "🎯  Traceability", "Evidence", "Draft",
     "Requirements", "Execution", "✅  Review"]
)


# --------------------------------------------------------------------------- #
# Overview -- the reporting dashboard
# --------------------------------------------------------------------------- #
with tab_over:
    st.markdown(
        ui.verdict(
            export_ok,
            "Cleared for export" if export_ok
            else "Not cleared for export",
            "Every section approved and no unresolved gaps."
            if export_ok else " · ".join(export_reasons),
        ), **H)
    st.write("")

    st.markdown(ui.tiles([
        ("Requirements", len(summary), "extracted & validated", ui.BRAND),
        ("Claims verified", len(draft.overall_traceability), "atomic, independently checked", ui.BRAND),
        ("Supported", draft.supported_claim_count, "evidence confirmed",
         ui.STATUS["SUPPORTED"]["fill"]),
        ("Gaps", n_gap_rows, "block export until resolved", ui.STATUS["GAP"]["fill"]),
        ("Sections approved", f"{n_approved}/{len(draft.sections)}", "human sign-off",
         ui.STATUS["SUPPORTED"]["fill"] if n_approved == len(draft.sections)
         else ui.STATUS["PARTIAL"]["fill"]),
        ("Evidence", f"{n_selected}", f"selected · {n_rejected} rejected", ui.MUTED),
    ]), **H)

    st.write("")
    left, right = st.columns([1.15, 1])

    with left:
        st.markdown('<div class="sec-h">Requirement coverage</div>', **H)
        chart = ui.coverage_bar(coverage)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
        st.markdown(
            '<div class="pills">' + "".join(
                ui.pill(k, f"{ui.STATUS[k]['label']} · {coverage[k]}")
                for k in ui.STATUS_ORDER if coverage.get(k)
            ) + "</div>", **H)
        st.caption("How every requirement extracted from the RFP resolved. "
                   "“Not addressed” means no claim was drafted for it.")

    with right:
        st.markdown('<div class="sec-h">Evidence actually cited</div>', **H)
        chart = ui.evidence_bar(usage)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No evidence was cited by any claim.")
        st.caption(f"{n_selected} chunks cleared the ranker; {n_rejected} were rejected "
                   f"with a written reason (see the Evidence tab).")

    st.write("")
    st.markdown('<div class="sec-h">Section readiness</div>', **H)
    rows = []
    for s in draft.sections:
        sec_status = "GAP" if s.has_gaps else "SUPPORTED"
        rows.append(
            f'<tr><td style="padding:.42rem .7rem;border-bottom:1px solid {ui.LINE}">'
            f'<b>{s.title}</b>{" ✏️" if s.human_edited else ""}</td>'
            f'<td style="padding:.42rem .7rem;border-bottom:1px solid {ui.LINE};'
            f'text-align:right;color:{ui.INK_2}">{len(s.claim_ids)}</td>'
            f'<td style="padding:.42rem .7rem;border-bottom:1px solid {ui.LINE}">'
            f'{ui.pill(sec_status, "contains a gap" if s.has_gaps else "clean")}</td>'
            f'<td style="padding:.42rem .7rem;border-bottom:1px solid {ui.LINE}">'
            f'{ui.pill("SUPPORTED" if s.review_status == ReviewDecision.APPROVED else "NO_ROW", s.review_status.value.title())}'
            f'</td></tr>')
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:.88rem">'
        f'<tr><th style="text-align:left;padding:.3rem .7rem;font-size:.72rem;'
        f'letter-spacing:.06em;text-transform:uppercase;color:{ui.MUTED}">Section</th>'
        f'<th style="text-align:right;padding:.3rem .7rem;font-size:.72rem;'
        f'letter-spacing:.06em;text-transform:uppercase;color:{ui.MUTED}">Claims</th>'
        f'<th style="text-align:left;padding:.3rem .7rem;font-size:.72rem;'
        f'letter-spacing:.06em;text-transform:uppercase;color:{ui.MUTED}">Content</th>'
        f'<th style="text-align:left;padding:.3rem .7rem;font-size:.72rem;'
        f'letter-spacing:.06em;text-transform:uppercase;color:{ui.MUTED}">Review</th></tr>'
        + "".join(rows) + "</table>", **H)

    if state["warnings"]:
        st.write("")
        st.markdown('<div class="sec-h">Flagged for a human</div>', **H)
        for w in state["warnings"]:
            st.warning(w, icon="⚠️")


# --------------------------------------------------------------------------- #
# Traceability -- the proof
# --------------------------------------------------------------------------- #
with tab_trace:
    hero_18 = next((e for e in entries if "18 percent" in e.claim_text
                    and e.verification_status == VerificationStatus.SUPPORTED), None)
    hero_35 = next((e for e in entries if "35 percent" in e.claim_text
                    and e.verification_status == VerificationStatus.GAP), None)
    if hero_18 or hero_35:
        hc1, hc2 = st.columns(2)
        if hero_18:
            hc1.markdown(ui.verdict(
                True, "Verified — Supported",
                f'“{hero_18.claim_text}”<br><span style="color:{ui.MUTED}">traced to '
                f'<b>{evidence_display_id(hero_18.matched_evidence_id)}</b>; numeric match '
                f'confirmed in context.</span>'), **H)
        if hero_35:
            hc2.markdown(ui.verdict(
                False, "Caught — Gap",
                f'“{hero_35.claim_text}”<br><span style="color:{ui.MUTED}">'
                f'{hero_35.verification_reason}</span>'), **H)
        st.caption("18 % passes, 35 % is caught — before either can reach an approved proposal.")
        st.write("")

    f1, f2 = st.columns([2, 1])
    show = f1.multiselect("Filter by status", [s.value for s in VerificationStatus],
                          default=["SUPPORTED", "PARTIAL", "GAP"])
    only_reqs = f2.checkbox("Only rows tied to an RFP requirement", value=True)

    view = [e for e in entries
            if e.verification_status.value in show
            and (not only_reqs or e.requirement_id != "-")]

    df = pd.DataFrame([{
        "Status": e.verification_status.value,
        "RFP Requirement": e.rfp_requirement[:72],
        "Evidence": evidence_display_id(e.matched_evidence_id),
        "Draft Claim": e.claim_text[:86],
        "Conf": round(e.confidence_score, 2),
        "Reviewer": e.reviewer_decision.value,
    } for e in view])

    if not df.empty:
        _tint = {k: ui.STATUS[k]["tint"] for k in ui.STATUS}
        st.dataframe(
            df.style.apply(
                lambda r: [f"background-color: {_tint.get(r['Status'], '')}"] * len(r), axis=1),
            use_container_width=True, hide_index=True, height=340,
            column_config={
                "Conf": st.column_config.ProgressColumn(
                    "Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
            })
    else:
        st.info("No rows match the current filter.")

    st.write("")
    st.markdown('<div class="sec-h">Inspect one claim end to end</div>', **H)
    if view:
        labels = [f"{ui.STATUS.get(e.verification_status.value, ui.STATUS['NO_ROW'])['label']}"
                  f"  ·  {e.claim_text[:88]}" for e in view]
        idx = st.selectbox("Claim", range(len(labels)), format_func=lambda i: labels[i],
                           label_visibility="collapsed")
        e = view[idx]

        st.markdown(
            f'<div class="pills">{ui.pill(e.verification_status.value)}'
            f'{ui.pill("NO_ROW", "confidence " + format(e.confidence_score, ".2f"))}'
            f'{ui.pill("NO_ROW", "section: " + e.draft_section)}</div>', **H)

        st.markdown(ui.chain_step(
            f"1 · RFP requirement ({e.requirement_id})", e.rfp_requirement), **H)
        if e.requirement_source_span:
            st.markdown(ui.chain_step(
                "2 · Exact quote located in the RFP",
                f'“{e.requirement_source_span.quote}”', "quote"), **H)
        if e.matched_chunk_text:
            st.markdown(ui.chain_step(
                f"3 · Source chunk used ({e.matched_evidence_id})",
                e.matched_chunk_text.strip()[:700].replace("\n", "<br>"), "mono"), **H)
        else:
            st.markdown(ui.chain_step(
                "3 · Source chunk used",
                "<i>none — this claim cites no selected evidence.</i>"), **H)
        st.markdown(ui.chain_step("4 · Drafted claim", e.claim_text), **H)

        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Semantic", f"{e.semantic_similarity:.2f}")
        v2.metric("Lexical", f"{e.lexical_overlap:.2f}")
        v3.metric("Numeric", {True: "match", False: "contradicted", None: "n/a"}[e.numeric_match])
        v4.metric("Attribution", "valid" if e.attribution_valid else "mismatch")
        st.markdown(ui.chain_step("5 · Deterministic verifier", e.verification_reason), **H)

    st.write("")
    st.download_button("⬇  Traceability matrix (CSV)", export.traceability_csv(state),
                       file_name=f"traceability_{state['run_id'][:8]}.csv", mime="text/csv")


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
with tab_ev:
    if state["evidence_conflicts"]:
        st.error("Conflicting evidence surfaced — never auto-resolved:", icon="⚠️")
        for c in state["evidence_conflicts"]:
            st.write(f"• `{c.conflict_id}` **{c.conflict_type}** — {c.description}")

    st.caption(f"{n_selected} chunks selected · {n_rejected} rejected, each with a reason.")
    checklist_by_id = {c.checklist_id: c for c in state["checklist"]}
    for cid, sel in state["selected_evidence"].items():
        if cid == "__pool__":
            continue
        item = checklist_by_id.get(cid)
        if item is None:
            continue
        badge = "SUPPORTED" if sel else "GAP"
        with st.expander(f"{item.requirement_text}   ·   {item.target_section}"):
            st.markdown(f'<div class="pills">{ui.pill(badge, "selected" if sel else "no evidence")}'
                        f'{ui.pill("NO_ROW", str(len(state["rejected_evidence"].get(cid, []))) + " rejected")}'
                        f'</div>', **H)
            st.caption(item.evidence_need)
            for e in sel:
                st.markdown(f"**{e.source_id}** — {e.reasoning}")
                st.code(e.chunk_text.strip()[:600])
            if not sel:
                st.markdown("**No candidate cleared the threshold — explicit GAP.**")
            rej = state["rejected_evidence"].get(cid, [])
            if rej:
                st.markdown("_Rejected candidates:_")
                for e in rej[:6]:
                    st.markdown(f"- `{e.source_id}` — {e.rejection_reason}")


# --------------------------------------------------------------------------- #
# Draft
# --------------------------------------------------------------------------- #
with tab_draft:
    for sec in draft.sections:
        badges = ui.pill("SUPPORTED" if not sec.has_gaps else "GAP",
                         "clean" if not sec.has_gaps else "contains a gap marker")
        if sec.human_edited:
            badges += ui.pill("FORWARD_LOOKING", "human-edited")
        st.markdown(f"### {sec.title}", **H)
        st.markdown(f'<div class="pills">{badges}</div>', **H)
        st.markdown(sec.content_markdown)
        st.divider()


# --------------------------------------------------------------------------- #
# Requirements
# --------------------------------------------------------------------------- #
with tab_req:
    rd = state["rfp_data"]
    if state["requirement_validation_errors"]:
        st.error("Ungrounded requirements were dropped (source quote not locatable in the RFP):")
        for e in state["requirement_validation_errors"]:
            st.write("• ", e)

    st.markdown('<div class="sec-h">Extracted requirements · each traced to its source quote</div>', **H)
    st.dataframe(pd.DataFrame([{
        "ID": r.requirement_id, "Requirement": r.text,
        "Category": r.category.value, "Handling": r.handling.value,
        "Mandatory": r.mandatory, "Confidence": round(r.extraction_confidence, 2),
        "Source quote": r.source_span.quote,
    } for r in rd.requirements]), use_container_width=True, hide_index=True,
        column_config={"Confidence": st.column_config.ProgressColumn(
            "Confidence", min_value=0.0, max_value=1.0, format="%.2f")})

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="sec-h">Procedural checklist · never becomes prose</div>', **H)
        for p in state["procedural_checklist"] or ["—"]:
            st.checkbox(p, key=f"proc_{p[:30]}", value=False)
    with c2:
        st.markdown('<div class="sec-h">Needs human input</div>', **H)
        for h in state["human_input_requirements"] or ["—"]:
            st.write("• ", h)
        caps = [r.text for r in rd.requirements if r.handling.value == "CAPABILITY_GAP"]
        if caps:
            st.markdown('<div class="sec-h">Capability gaps · go / no-go</div>', **H)
            for c in caps:
                st.markdown(f'{ui.pill("GAP", "capability gap")}&nbsp; {c}', **H)


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
with tab_exec:
    st.markdown('<div class="sec-h">Agent execution log</div>', **H)
    st.dataframe(pd.DataFrame(state["execution_log"]), use_container_width=True,
                 hide_index=True)
    if state.get("web_evidence"):
        st.markdown('<div class="sec-h">Web background · context only, never cited as evidence</div>', **H)
        st.dataframe(pd.DataFrame(state["web_evidence"]), use_container_width=True,
                     hide_index=True)
    try:
        trail = get_store().audit_trail(state["run_id"])
        if trail:
            with st.expander("SQLite audit trail (every stage + every human decision)"):
                st.dataframe(pd.DataFrame(trail), use_container_width=True, hide_index=True)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #
with tab_review:
    st.markdown(ui.verdict(
        export_ok,
        "Export gate OPEN" if export_ok else "Export gate BLOCKED",
        "Every section approved and no unresolved gaps."
        if export_ok else " · ".join(export_reasons)), **H)
    st.write("")

    st.markdown('<div class="sec-h">Section-level approval</div>', **H)
    for sec in draft.sections:
        approved = sec.review_status == ReviewDecision.APPROVED
        with st.expander(f"{'✓' if approved else '○'}  {sec.title}"
                         f"{'  ·  edited' if sec.human_edited else ''}"):
            st.markdown(f'<div class="pills">'
                        f'{ui.pill("SUPPORTED" if approved else "NO_ROW", sec.review_status.value.title())}'
                        f'{ui.pill("GAP", "contains a gap") if sec.has_gaps else ""}</div>', **H)
            st.markdown(sec.content_markdown)
            comment = st.text_input("Comment", key=f"cm_{sec.section_id}")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("Approve", key=f"ap_{sec.section_id}", use_container_width=True):
                review.submit_section_decision(state, sec.section_id, "reviewer",
                                               ReviewDecision.APPROVED, comment)
                st.rerun()
            if b2.button("Request changes", key=f"cc_{sec.section_id}", use_container_width=True):
                review.submit_section_decision(state, sec.section_id, "reviewer",
                                               ReviewDecision.CHANGES_REQUESTED, comment)
                st.rerun()
            if b3.button("Reject", key=f"rj_{sec.section_id}", use_container_width=True):
                review.submit_section_decision(state, sec.section_id, "reviewer",
                                               ReviewDecision.REJECTED, comment)
                st.rerun()
            if b4.button("Regenerate", key=f"rg_{sec.section_id}", use_container_width=True):
                review.regenerate_section(state, sec.title)
                st.rerun()
            new_md = st.text_area("Direct human edit (preserved through later regenerations)",
                                  value=sec.content_markdown, key=f"ed_{sec.section_id}",
                                  height=140)
            if st.button("Save edit", key=f"sv_{sec.section_id}"):
                review.apply_human_edit(state, sec.title, new_md)
                st.rerun()

    st.divider()
    st.markdown('<div class="sec-h">Unresolved gaps · block export unless overridden with a reason</div>', **H)
    gaps = review.unresolved_gaps(state)
    if not gaps:
        st.markdown(ui.verdict(True, "No unresolved gaps", "Nothing is blocking on this side."), **H)
    for g in gaps:
        st.markdown(f'{ui.pill("GAP")}&nbsp; <b>{g.rfp_requirement[:80]}</b><br>'
                    f'<span style="color:{ui.MUTED}">→ {g.claim_text[:90]}</span>', **H)
        r = st.text_input("Override reason", key=f"ov_{g.trace_id}",
                          placeholder="e.g. no comparable >30% engagement — we will not claim it")
        if st.button("Record override", key=f"ovb_{g.trace_id}"):
            if r.strip():
                review.override_gap(state, g.trace_id, r)
                st.rerun()
            else:
                st.error("A reason is required.")

    st.divider()
    if export_ok:
        if st.button("Finalize proposal", type="primary"):
            review.finalize(state)
            st.rerun()
        d1, d2 = st.columns(2)
        d1.download_button("⬇  Proposal (Markdown)",
                           export.render_markdown(state, enforce=False),
                           file_name=f"proposal_{state['run_id'][:8]}.md",
                           use_container_width=True)
        d2.download_button("⬇  Traceability (CSV)", export.traceability_csv(state),
                           file_name=f"traceability_{state['run_id'][:8]}.csv",
                           use_container_width=True)
    else:
        st.caption("Approve every section and resolve or override each gap to unlock export.")
    st.caption("The system never sends or submits anything externally — that stays a "
               "manual, out-of-system action, permanently.")
