"""Presentation layer: design tokens, CSS, and small reusable components.

Dark is the default surface. Colour follows the validated reference palette
(dataviz `palette.md`):

  * status roles are FIXED and never themed -- good / warning / critical, plus an
    informational blue for FORWARD_LOOKING (a claim that isn't judged at all).
    All four clear 3:1 on the dark surface #1a1a19 (validated), which is why dark
    is the better surface here: on light, warning amber sits at 1.83:1 and needs
    the relief rule; on dark it measures 9.49:1;
  * the brand accent is blue, so red is reserved exclusively for problems -- a red
    primary button competing with "GAP is red" was the main colour bug earlier;
  * every status still ships with a dot + a word, so colour never carries meaning
    alone (CVD, print, forced-colors).
"""
from __future__ import annotations

# --- surfaces & ink (reference palette, dark column) ----------------------
PAGE = "#0d0d0d"        # page plane
SURFACE = "#1a1a19"     # card / chart surface
ELEV = "#212120"        # raised surface (hover, inputs)
LINE = "#2c2c2a"        # hairline / gridline
AXIS = "#383835"        # baseline / axis
INK = "#ffffff"         # primary
INK_2 = "#c3c2b7"       # secondary
MUTED = "#898781"       # axis / labels
BRAND = "#3987e5"       # accent -- NOT red

# --- status roles (fixed; fills are mode-invariant) ----------------------
STATUS: dict[str, dict[str, str]] = {
    "SUPPORTED": {
        "fill": "#0ca30c", "ink": "#2fc32f", "tint": "rgba(12,163,12,.15)",
        "icon": "●", "label": "Supported",
    },
    "PARTIAL": {
        "fill": "#fab219", "ink": "#fab219", "tint": "rgba(250,178,25,.15)",
        "icon": "●", "label": "Partial",
    },
    "GAP": {
        "fill": "#d03b3b", "ink": "#e66767", "tint": "rgba(208,59,59,.17)",
        "icon": "●", "label": "Gap",
    },
    "FORWARD_LOOKING": {
        "fill": "#3987e5", "ink": "#5598e7", "tint": "rgba(57,135,229,.15)",
        "icon": "●", "label": "Forward-looking",
    },
    "NO_ROW": {
        "fill": "#898781", "ink": "#c3c2b7", "tint": "rgba(137,135,129,.15)",
        "icon": "●", "label": "Not addressed",
    },
}
STATUS_ORDER = ["SUPPORTED", "PARTIAL", "GAP", "FORWARD_LOOKING", "NO_ROW"]


def status_fill(key: str) -> str:
    return STATUS.get(key, STATUS["NO_ROW"])["fill"]


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

#MainMenu, footer, [data-testid="stToolbar"] {{visibility:hidden;}}
.block-container {{padding-top:3rem; padding-bottom:3.5rem; max-width:1240px;}}
html, body, [class*="css"], button, input, select, textarea,
h1, h2, h3, h4, h5, h6 {{
  font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  -webkit-font-smoothing:antialiased;
}}
h1,h2,h3,h4 {{letter-spacing:-.015em; color:{INK};}}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{gap:.15rem; border-bottom:1px solid {LINE};}}
.stTabs [data-baseweb="tab"] {{
  height:2.5rem; padding:0 .9rem; font-size:.9rem; font-weight:500; color:{INK_2};
}}
.stTabs [aria-selected="true"] {{color:{BRAND}; font-weight:650;}}

/* ---- typography helpers ---- */
.eyebrow {{letter-spacing:.13em; text-transform:uppercase; font-size:.7rem;
          font-weight:700; color:{BRAND};}}
.hero-h1 {{font-size:2.6rem; line-height:1.1; font-weight:800; margin:.35rem 0 .7rem;
          letter-spacing:-.028em; color:{INK};}}
.hero-sub {{font-size:1.05rem; color:{INK_2}; max-width:46rem; line-height:1.55;}}
.sec-h {{font-size:.78rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase;
        color:{MUTED}; margin:.2rem 0 .6rem;}}

/* ---- cards ---- */
.card {{border:1px solid {LINE}; border-radius:14px; padding:1.05rem 1.15rem;
       background:{SURFACE}; height:100%;}}
.card h4 {{margin:.1rem 0 .4rem; font-size:.97rem; font-weight:700; color:{INK};}}
.card p {{margin:0; color:{INK_2}; font-size:.88rem; line-height:1.55;}}

/* ---- stat tiles ---- */
.tiles {{display:grid; grid-template-columns:repeat(auto-fit,minmax(118px,1fr)); gap:.55rem;}}
.tile {{border:1px solid {LINE}; border-radius:13px; padding:.8rem .95rem; background:{SURFACE};
       border-top:3px solid var(--accent,{LINE});}}
.tile .k {{font-size:.72rem; font-weight:600; letter-spacing:.05em; text-transform:uppercase;
          color:{MUTED};}}
.tile .v {{font-size:1.85rem; font-weight:750; line-height:1.15; margin-top:.15rem; color:{INK};}}
.tile .s {{font-size:.76rem; color:{INK_2}; margin-top:.1rem;}}

/* ---- status pills ---- */
.pill {{display:inline-flex; align-items:center; gap:.34rem; border-radius:999px;
       padding:.16rem .6rem; font-size:.76rem; font-weight:600; white-space:nowrap;
       border:1px solid transparent;}}
.pill .dot {{font-size:.62rem; line-height:1;}}
.pills {{display:flex; flex-wrap:wrap; gap:.4rem; margin:.45rem 0 .1rem;}}

/* ---- verdict banner ---- */
.verdict {{border-radius:14px; padding:.95rem 1.15rem; border:1px solid transparent;
          display:flex; gap:.85rem; align-items:flex-start;}}
.verdict .vt {{font-weight:750; font-size:1rem; margin-bottom:.12rem;}}
.verdict .vb {{font-size:.87rem; line-height:1.5;}}

/* ---- pipeline strip ---- */
.flow {{display:flex; flex-wrap:wrap; gap:.35rem;}}
.flow span {{background:{SURFACE}; border:1px solid {LINE}; border-radius:999px;
            padding:.27rem .68rem; font-size:.78rem; color:{INK_2}; white-space:nowrap;}}
.flow span.gate {{background:{STATUS['GAP']['tint']}; border-color:{STATUS['GAP']['fill']}55;
                 color:{STATUS['GAP']['ink']}; font-weight:650;}}

/* ---- claim inspector ---- */
.chain {{border:1px solid {LINE}; border-left:3px solid {BRAND}; border-radius:0 12px 12px 0;
        background:{SURFACE}; padding:.75rem .95rem; margin-bottom:.5rem;}}
.chain .cl {{font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
            color:{MUTED}; margin-bottom:.25rem;}}
.chain .cv {{font-size:.92rem; color:{INK}; line-height:1.55;}}
.quote {{font-style:italic; color:{INK_2};}}
.mono {{font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem;
       color:{INK_2};}}

/* ---- misc ---- */
.cta {{margin-top:1.1rem; font-size:.95rem; color:{INK};}}
.cta b {{color:{BRAND};}}
hr {{border-color:{LINE};}}
[data-testid="stMetricValue"] {{font-size:1.7rem; font-weight:750;}}
.stDownloadButton button, .stButton button {{border-radius:9px; font-weight:600;}}
code {{color:{INK_2};}}
</style>
"""


# --------------------------------------------------------------------------- #
# Components (return HTML; render with st.markdown(..., unsafe_allow_html=True))
# --------------------------------------------------------------------------- #
def pill(status_key: str, text: str | None = None) -> str:
    s = STATUS.get(status_key, STATUS["NO_ROW"])
    return (f'<span class="pill" style="background:{s["tint"]};color:{s["ink"]};'
            f'border-color:{s["fill"]}55"><span class="dot" style="color:{s["fill"]}">'
            f'{s["icon"]}</span>{text or s["label"]}</span>')


def tiles(items: list[tuple[str, object, str, str]]) -> str:
    """items = [(label, value, sublabel, accent_hex)]"""
    cells = "".join(
        f'<div class="tile" style="--accent:{accent}">'
        f'<div class="k">{label}</div><div class="v">{value}</div>'
        f'<div class="s">{sub}</div></div>'
        for label, value, sub, accent in items
    )
    return f'<div class="tiles">{cells}</div>'


def verdict(ok: bool, title: str, body: str) -> str:
    role = STATUS["SUPPORTED"] if ok else STATUS["GAP"]
    return (f'<div class="verdict" style="background:{role["tint"]};'
            f'border-color:{role["fill"]}55">'
            f'<div style="font-size:1.3rem;line-height:1.2;color:{role["ink"]}">'
            f'{"✓" if ok else "✕"}</div>'
            f'<div><div class="vt" style="color:{role["ink"]}">{title}</div>'
            f'<div class="vb" style="color:{INK_2}">{body}</div></div></div>')


def chain_step(label: str, value: str, extra_class: str = "") -> str:
    return (f'<div class="chain"><div class="cl">{label}</div>'
            f'<div class="cv {extra_class}">{value}</div></div>')


# --------------------------------------------------------------------------- #
# Charts (Altair) -- thin marks, recessive axes, tooltips, no chart junk
# --------------------------------------------------------------------------- #
def coverage_bar(counts: dict[str, int]):
    """One stacked horizontal bar: how the RFP's requirements resolved.

    Composition of a whole -> a single stacked bar, with a 2px surface-coloured
    gap between segments; direct-labelled by the pill legend beneath it.
    """
    import altair as alt
    import pandas as pd

    rows = [{"status": k, "n": counts[k], "label": STATUS[k]["label"], "rank": i}
            for i, k in enumerate(STATUS_ORDER) if counts.get(k)]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    return (
        alt.Chart(df)
        .mark_bar(cornerRadius=5, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("n:Q", stack="zero", axis=None, title=None),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=[r["status"] for r in rows],
                                range=[status_fill(r["status"]) for r in rows]),
                legend=None,
            ),
            # best -> worst, not alphabetical
            order=alt.Order("rank:Q", sort="ascending"),
            tooltip=[alt.Tooltip("label:N", title="Status"),
                     alt.Tooltip("n:Q", title="Requirements")],
        )
        .properties(height=42, background="transparent")
        .configure_view(strokeWidth=0)
    )


def evidence_bar(usage: dict[str, int]):
    """Which corpus documents actually got cited, and how often.

    Magnitude across a named set -> horizontal bars, one series (no legend
    needed; the heading names it), sorted by value.
    """
    import altair as alt
    import pandas as pd

    if not usage:
        return None
    df = pd.DataFrame([{"doc": k, "n": v} for k, v in usage.items()])
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4, color=BRAND)
        .encode(
            # one band per document; Step sizing keeps labels from colliding
            y=alt.Y("doc:N", sort="-x", title=None,
                    scale=alt.Scale(paddingInner=0.45, paddingOuter=0.25),
                    axis=alt.Axis(labelColor=INK_2, labelFontSize=12, domain=False,
                                  ticks=False, labelPadding=10, labelLimit=180)),
            x=alt.X("n:Q", title=None,
                    axis=alt.Axis(labelColor=MUTED, labelFontSize=11, grid=True,
                                  gridColor=LINE, domain=False, ticks=False,
                                  tickMinStep=1, format="d")),
            tooltip=[alt.Tooltip("doc:N", title="Document"),
                     alt.Tooltip("n:Q", title="Claims citing it")],
        )
        .properties(height=alt.Step(34), background="transparent")
        .configure_view(strokeWidth=0)
    )
