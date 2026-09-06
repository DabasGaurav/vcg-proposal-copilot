"""VCG Proposal Copilot -- Streamlit hero screen (SPEC Phase 7).

Tabs, in the order the spec asks for:
    RFP -> Requirements -> Execution -> Evidence -> Draft -> Traceability -> Review

The Traceability tab is the point of the demo: for any claim, the full
Requirement -> exact RFP quote -> why this evidence (and why the rejected ones
were rejected) -> exact source chunk -> deterministic verifier result -> human
decision chain is inspectable, not narrated.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import config
from models.schemas import ReviewDecision, VerificationStatus
from pipeline import export, review
from pipeline.graph import load_run, run_pipeline
from pipeline.traceability import evidence_display_id
from services.persistence import get_store
from services.vectorstore import VectorStore

st.set_page_config(page_title="VCG Proposal Copilot", layout="wide",
                   page_icon="📝", initial_sidebar_state="expanded")
config.ensure_dirs()


@st.cache_resource(show_spinner="Building the evidence knowledge base…")
def _bootstrap():
    """First-load setup so a hosted deploy needs no manual seed step."""
    VectorStore.ensure_seeded()
    return True


_bootstrap()

STATUS_ICON = {
    "SUPPORTED": "🟢", "PARTIAL": "🟡", "GAP": "🔴", "FORWARD_LOOKING": "🔵",
}

st.markdown(
    """
    <style>
      #MainMenu, footer, [data-testid="stToolbar"] {visibility: hidden;}
      .block-container {padding-top: 2.4rem; max-width: 1180px;}
      html, body, [class*="css"], h1, h2, h3 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }
      .eyebrow {letter-spacing:.14em; text-transform:uppercase; font-size:.72rem;
                font-weight:700; color:#c0392b;}
      .hero-h1 {font-size:2.5rem; line-height:1.12; font-weight:800; margin:.35rem 0 .6rem;
                letter-spacing:-.02em;}
      .hero-sub {font-size:1.06rem; color:#3c4450; max-width:44rem; line-height:1.55;}
      .card {border:1px solid #e7e9ee; border-radius:14px; padding:1.05rem 1.15rem;
             background:#fff; height:100%;}
      .card h4 {margin:.1rem 0 .35rem; font-size:1rem; font-weight:700;}
      .card p {margin:0; color:#54606e; font-size:.9rem; line-height:1.5;}
      .flow {display:flex; flex-wrap:wrap; gap:.4rem; margin:.2rem 0 .2rem;}
      .flow span {background:#f2f4f7; border:1px solid #e7e9ee; border-radius:999px;
                  padding:.28rem .7rem; font-size:.8rem; color:#414b57; white-space:nowrap;}
      .flow span.gate {background:#fdecea; border-color:#f5c6c0; color:#a5342a; font-weight:600;}
      .cta {margin-top:1rem; font-size:.95rem; color:#1b1f24;}
      .cta b {color:#c0392b;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Sidebar -- pick / upload an RFP and run the pipeline
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 📝 Proposal Copilot")
    st.caption("RFP → source-grounded, review-ready proposal")
    st.divider()
    fixtures = sorted(p.name for p in config.FIXTURE_DIR.glob("*.md"))
    choice = st.selectbox("Demo RFP", fixtures,
                          help="Four scenarios: happy path, capability gap, "
                               "procurement-heavy, and no evaluation rubric.")
    uploaded = st.file_uploader("…or upload your own RFP", type=["md", "txt", "pdf"])
    web = st.checkbox("Web enrichment (industry context only)", value=False)

    if st.button("▶ Run pipeline", type="primary", use_container_width=True):
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
            except Exception as exc:  # keep the app usable on failure
                st.session_state.state = None
                st.error(f"Pipeline failed: {exc}")

    if st.session_state.get("state"):
        s = st.session_state.state
        d = s["proposal_draft"]
        st.metric("Supported / Partial / Gap",
                  f"{d.supported_claim_count} / {d.partial_claim_count} / {d.gap_claim_count}")
        st.caption(f"run_id {s['run_id'][:12]} · {len(s['overall_traceability'])} matrix rows")

    st.divider()
    st.subheader("Resume a run")
    try:
        prev = get_store().list_runs()
    except Exception:
        prev = []
    if prev:
        pick = st.selectbox("Persisted runs", [r["run_id"] for r in prev],
                            format_func=lambda r: f"{r[:12]}…")
        if st.button("↺ Load run", use_container_width=True):
            try:
                st.session_state.state = load_run(pick)
                st.session_state.rfp_name = st.session_state.state.get("rfp_filename", pick)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load: {exc}")
    else:
        st.caption("No persisted runs yet.")

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
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.markdown(
        '<div class="card"><h4>Requirement → Evidence → Draft</h4>'
        '<p>A live traceability matrix. Click any sentence and see the RFP line it '
        'answers, the source chunk it was written from, and the candidates that were '
        'rejected — with reasons.</p></div>', unsafe_allow_html=True)
    c2.markdown(
        '<div class="card"><h4>Deterministic verification</h4>'
        '<p>Numeric, attribution and geography/industry checks — rule-based, not an '
        'LLM grading its own output. A contradicted number can never pass as '
        '“supported”.</p></div>', unsafe_allow_html=True)
    c3.markdown(
        '<div class="card"><h4>Human approval gate</h4>'
        '<p>No code path reaches an export without a reviewer approving every section. '
        'Unsupported claims block the export until resolved or overridden with a '
        'recorded reason.</p></div>', unsafe_allow_html=True)

    st.write("")
    st.markdown(
        '<div class="flow">'
        '<span>RFP</span><span>extract + validate</span><span>retrieve evidence</span>'
        '<span>rank / reject</span><span>draft</span><span>decompose claims</span>'
        '<span>verify</span><span>traceability</span>'
        '<span class="gate">human review</span><span>export</span>'
        '</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cta">← Pick a demo RFP in the sidebar and press '
        '<b>Run pipeline</b>. Try <b>abc_bank_lending_transformation</b> first — '
        'it contains a claim the evidence can\'t support.</div>',
        unsafe_allow_html=True)
    st.stop()

_rs = state.get("review_status", "PENDING")
_client = (state["rfp_data"].client or "Untitled RFP").rstrip(".")
st.markdown(f'<div class="eyebrow">Proposal · review status {_rs}</div>'
            f'<div class="hero-h1" style="font-size:1.9rem;margin:.2rem 0 .5rem;">{_client}</div>',
            unsafe_allow_html=True)
st.caption(
    f"`{st.session_state.get('rfp_name','')}` · run `{state['run_id'][:12]}` · "
    f"{len(state['checklist'])} evidence needs · "
    f"{len(state['procedural_checklist'])} procedural items · "
    f"{sum(1 for e in state['overall_traceability'] if e.verification_status.value=='GAP')} GAP rows"
)

tab_rfp, tab_req, tab_exec, tab_ev, tab_draft, tab_trace, tab_review = st.tabs(
    ["RFP", "Requirements", "Execution", "Evidence", "Draft", "🎯 Traceability", "Review"]
)

# --------------------------------------------------------------------------- #
# RFP
# --------------------------------------------------------------------------- #
with tab_rfp:
    st.subheader(st.session_state.get("rfp_name", "RFP"))
    rd = state["rfp_data"]
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Client**\n\n{rd.client or '—'}")
    c2.markdown(f"**Timeline**\n\n{rd.timeline or '—'}")
    c3.markdown(f"**Procedural items**\n\n{len(state['procedural_checklist'])}")
    st.markdown(f"**Problem statement**\n\n{rd.problem_statement or '—'}")
    with st.expander("Raw RFP text"):
        st.text(state["rfp_raw_text"])


# --------------------------------------------------------------------------- #
# Requirements
# --------------------------------------------------------------------------- #
with tab_req:
    rd = state["rfp_data"]
    if rd.warnings:
        for w in rd.warnings:
            st.warning(w)
    if state["requirement_validation_errors"]:
        st.error("Ungrounded requirements were dropped (source quote not locatable):")
        for e in state["requirement_validation_errors"]:
            st.write("• ", e)

    st.markdown("#### Extracted requirements (each traced to its source quote)")
    rows = [
        {
            "id": r.requirement_id, "requirement": r.text,
            "category": r.category.value, "handling": r.handling.value,
            "mandatory": r.mandatory, "confidence": round(r.extraction_confidence, 2),
            "source quote": r.source_span.quote,
        }
        for r in rd.requirements
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    cols = st.columns(2)
    with cols[0]:
        st.markdown("#### Procedural checklist (never becomes prose)")
        for p in state["procedural_checklist"]:
            st.checkbox(p, key=f"proc_{p[:30]}", value=False)
    with cols[1]:
        st.markdown("#### Needs human input")
        for h in state["human_input_requirements"] or ["—"]:
            st.write("• ", h)
        caps = [r.text for r in rd.requirements if r.handling.value == "CAPABILITY_GAP"]
        if caps:
            st.markdown("#### ⚠️ Capability gaps (go / no-go)")
            for c in caps:
                st.write("• ", c)


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
with tab_exec:
    st.markdown("#### Agent execution log")
    st.dataframe(pd.DataFrame(state["execution_log"]), use_container_width=True, hide_index=True)
    if state["warnings"]:
        st.markdown("#### Warnings")
        for w in state["warnings"]:
            st.warning(w)
    if state.get("web_evidence"):
        st.markdown("#### Web background (context only — never cited as VCG evidence)")
        st.dataframe(pd.DataFrame(state["web_evidence"]), use_container_width=True,
                     hide_index=True)
    try:
        trail = get_store().audit_trail(state["run_id"])
        if trail:
            with st.expander("SQLite audit trail"):
                st.dataframe(pd.DataFrame(trail), use_container_width=True, hide_index=True)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Evidence -- selected AND rejected, with reasons
# --------------------------------------------------------------------------- #
with tab_ev:
    if state["evidence_conflicts"]:
        st.error("Conflicts surfaced (never auto-resolved):")
        for c in state["evidence_conflicts"]:
            st.write(f"• `{c.conflict_id}` **{c.conflict_type}** — {c.description}")

    checklist_by_id = {c.checklist_id: c for c in state["checklist"]}
    for cid, sel in state["selected_evidence"].items():
        if cid == "__pool__":
            continue
        item = checklist_by_id.get(cid)
        if item is None:
            continue
        icon = "🟢" if sel else "🔴"
        with st.expander(f"{icon} {item.requirement_text}  ·  {item.target_section}"):
            st.caption(item.evidence_need)
            if sel:
                for e in sel:
                    st.markdown(f"**SELECTED · {e.source_id}** — {e.reasoning}")
                    st.code(e.chunk_text.strip()[:600])
            else:
                st.markdown("**No evidence cleared threshold — explicit GAP.**")
            rej = state["rejected_evidence"].get(cid, [])
            if rej:
                st.markdown("_Rejected candidates:_")
                for e in rej[:6]:
                    st.markdown(f"- ❌ `{e.source_id}` — {e.rejection_reason}")


# --------------------------------------------------------------------------- #
# Draft
# --------------------------------------------------------------------------- #
with tab_draft:
    for sec in state["proposal_draft"].sections:
        flag = " ✏️ human-edited" if sec.human_edited else ""
        gap = " · ⚠️ contains gap marker" if sec.has_gaps else ""
        st.markdown(f"### {sec.title}{flag}{gap}")
        st.markdown(sec.content_markdown)
        st.divider()


# --------------------------------------------------------------------------- #
# Traceability -- the hero screen
# --------------------------------------------------------------------------- #
with tab_trace:
    st.markdown("### Requirement → Evidence → Draft Claim → Status")
    entries = state["overall_traceability"]

    # the hero moment, called out explicitly
    hero_18 = next((e for e in entries if "18 percent" in e.claim_text
                    and e.verification_status == VerificationStatus.SUPPORTED), None)
    hero_35 = next((e for e in entries if "35 percent" in e.claim_text
                    and e.verification_status == VerificationStatus.GAP), None)
    hc1, hc2 = st.columns(2)
    if hero_18:
        hc1.success(f"🟢 **SUPPORTED** — “{hero_18.claim_text}”  \n"
                    f"traced to `{evidence_display_id(hero_18.matched_evidence_id)}`, "
                    f"numeric match confirmed in context.")
    if hero_35:
        hc2.error(f"🔴 **GAP** — “{hero_35.claim_text}”  \n"
                  f"{hero_35.verification_reason}")
    if hero_18 and hero_35:
        st.caption("18% passes, 35% is caught — before either can reach an approved proposal.")

    d = state["proposal_draft"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Supported", d.supported_claim_count)
    m2.metric("Partial", d.partial_claim_count)
    m3.metric("Gap", d.gap_claim_count)
    m4.metric("Matrix rows", len(entries))

    f1, f2 = st.columns([1, 2])
    show = f1.multiselect(
        "Status", [s.value for s in VerificationStatus],
        default=["SUPPORTED", "PARTIAL", "GAP"],
    )
    only_reqs = f2.checkbox("Only rows tied to an RFP requirement", value=True)

    view = [
        e for e in entries
        if e.verification_status.value in show
        and (not only_reqs or e.requirement_id != "-")
    ]
    df = pd.DataFrame([
        {
            "": STATUS_ICON.get(e.verification_status.value, ""),
            "RFP Requirement": e.rfp_requirement[:70],
            "Evidence": evidence_display_id(e.matched_evidence_id),
            "Draft Claim": e.claim_text[:80],
            "Status": e.verification_status.value,
            "Conf": round(e.confidence_score, 2),
            "Reviewer": e.reviewer_decision.value,
        }
        for e in view
    ])
    _bg = {"SUPPORTED": "#e6f4ea", "PARTIAL": "#fef7e0", "GAP": "#fce8e6",
           "FORWARD_LOOKING": "#e8f0fe"}
    styled = df.style.apply(
        lambda row: [f"background-color: {_bg.get(row['Status'], '')}"] * len(row), axis=1
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=360)

    st.markdown("#### Inspect one claim end-to-end")
    labels = [f"{STATUS_ICON.get(e.verification_status.value,'')} {e.claim_text[:90]}" for e in view]
    if labels:
        idx = st.selectbox("Claim", range(len(labels)), format_func=lambda i: labels[i])
        e = view[idx]
        st.markdown(f"**RFP requirement** ({e.requirement_id})  \n> {e.rfp_requirement}")
        if e.requirement_source_span:
            st.caption(f"exact RFP quote: “{e.requirement_source_span.quote}”")
        st.markdown(f"**Draft claim** ({e.draft_section})  \n> {e.claim_text}")
        if e.matched_chunk_text:
            st.markdown(f"**Exact source chunk** (`{e.matched_evidence_id}`)")
            st.code(e.matched_chunk_text.strip()[:700])
        else:
            st.markdown("**Source chunk:** _none — this claim cites no selected evidence._")
        st.markdown(
            f"**Deterministic verifier**  \n"
            f"status `{e.verification_status.value}` · confidence {e.confidence_score:.2f} · "
            f"semantic {e.semantic_similarity:.2f} · lexical {e.lexical_overlap:.2f} · "
            f"numeric `{e.numeric_match}` · attribution `{e.attribution_valid}`  \n"
            f"> {e.verification_reason}"
        )

    csv = export.traceability_csv(state)
    st.download_button("⬇ traceability matrix (CSV)", csv,
                       file_name=f"traceability_{state['run_id'][:8]}.csv", mime="text/csv")


# --------------------------------------------------------------------------- #
# Review -- section approval, edits, gap overrides, export
# --------------------------------------------------------------------------- #
with tab_review:
    draft = state["proposal_draft"]
    st.markdown("#### Section-level approval")
    for sec in draft.sections:
        with st.expander(f"{sec.review_status.value} · {sec.title}"
                         + (" ✏️" if sec.human_edited else "")):
            st.markdown(sec.content_markdown)
            comment = st.text_input("Comment", key=f"cm_{sec.section_id}")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("Approve", key=f"ap_{sec.section_id}"):
                review.submit_section_decision(state, sec.section_id, "reviewer",
                                               ReviewDecision.APPROVED, comment)
                st.rerun()
            if b2.button("Request changes", key=f"cc_{sec.section_id}"):
                review.submit_section_decision(state, sec.section_id, "reviewer",
                                               ReviewDecision.CHANGES_REQUESTED, comment)
                st.rerun()
            if b3.button("Reject", key=f"rj_{sec.section_id}"):
                review.submit_section_decision(state, sec.section_id, "reviewer",
                                               ReviewDecision.REJECTED, comment)
                st.rerun()
            if b4.button("Regenerate", key=f"rg_{sec.section_id}"):
                review.regenerate_section(state, sec.title)
                st.rerun()
            new_md = st.text_area("Direct human edit (preserved through later regens)",
                                  value=sec.content_markdown, key=f"ed_{sec.section_id}",
                                  height=140)
            if st.button("Save edit", key=f"sv_{sec.section_id}"):
                review.apply_human_edit(state, sec.title, new_md)
                st.rerun()

    st.divider()
    st.markdown("#### Unresolved GAPs (block export unless overridden with a reason)")
    gaps = review.unresolved_gaps(state)
    if not gaps:
        st.success("No unresolved GAP rows.")
    for g in gaps:
        st.write(f"🔴 `{g.trace_id}` — {g.rfp_requirement[:80]} → {g.claim_text[:60]}")
        r = st.text_input("Override reason", key=f"ov_{g.trace_id}")
        if st.button("Record override", key=f"ovb_{g.trace_id}"):
            if r.strip():
                review.override_gap(state, g.trace_id, r)
                st.rerun()
            else:
                st.error("A reason is required.")

    st.divider()
    ok, reasons = review.can_export(state)
    if ok:
        st.success("Export gate OPEN — every section approved, no unresolved GAP.")
        if st.button("Finalize", type="primary"):
            review.finalize(state)
            st.rerun()
        st.download_button("⬇ proposal (Markdown)", export.render_markdown(state, enforce=False),
                           file_name=f"proposal_{state['run_id'][:8]}.md")
        st.download_button("⬇ traceability (CSV)", export.traceability_csv(state),
                           file_name=f"traceability_{state['run_id'][:8]}.csv")
    else:
        st.warning("Export gate BLOCKED:")
        for r in reasons:
            st.write("• ", r)
    st.caption("The system never sends or submits anything externally — that stays "
               "a manual, out-of-system action, permanently.")
