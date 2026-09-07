"""Presentation layer: design tokens, CSS, and reusable components.

Type system: IBM Plex Sans for the interface, IBM Plex Mono for identifiers and
source passages. Restrained scale and weight -- headings are set at 600/650, not
800, and the hero is sized as an application header rather than a marketing
banner.

Colour follows the validated reference palette (dataviz `palette.md`) on a dark
surface:

  * status roles are FIXED and never themed -- good / warning / critical, plus an
    informational blue for FORWARD_LOOKING. All four clear 3:1 against the dark
    surface #1a1a19 (validated); on a light surface warning amber measures
    1.83:1 and requires the relief rule, which is why dark is the correct
    surface for this interface;
  * the accent is blue, so red is reserved exclusively for exceptions;
  * every status is rendered with a mark and a word, so colour never carries
    meaning unaided.
"""
from __future__ import annotations

# --- surfaces & ink (reference palette, dark column) ----------------------
PAGE = "#0d0d0d"        # page plane
SURFACE = "#1a1a19"     # card / chart surface
ELEV = "#212120"        # raised surface
LINE = "#2c2c2a"        # hairline / gridline
AXIS = "#383835"        # baseline / axis
INK = "#ffffff"         # primary
INK_2 = "#c3c2b7"       # secondary
MUTED = "#898781"       # axis / labels
BRAND = "#3987e5"       # accent -- never red

# --- status roles (fixed; fills are mode-invariant) ----------------------
STATUS: dict[str, dict[str, str]] = {
    "SUPPORTED": {
        "fill": "#0ca30c", "ink": "#2fc32f", "tint": "rgba(12,163,12,.15)",
        "icon": "●", "label": "Substantiated",
    },
    "PARTIAL": {
        "fill": "#fab219", "ink": "#fab219", "tint": "rgba(250,178,25,.15)",
        "icon": "●", "label": "Partial",
    },
    "GAP": {
        "fill": "#d03b3b", "ink": "#e66767", "tint": "rgba(208,59,59,.17)",
        "icon": "●", "label": "Unsubstantiated",
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
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

#MainMenu, footer, [data-testid="stToolbar"] {{visibility:hidden;}}
.block-container {{padding-top:3rem; padding-bottom:4rem; max-width:1260px;}}
html, body, [class*="css"], button, input, select, textarea,
h1, h2, h3, h4, h5, h6 {{
  font-family:'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  -webkit-font-smoothing:antialiased;
}}
code, pre, .mono, [data-testid="stCode"] * {{
  font-family:'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace !important;
}}
h1,h2,h3,h4 {{letter-spacing:-.012em; color:{INK}; font-weight:600;}}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{gap:0; border-bottom:1px solid {LINE};}}
.stTabs [data-baseweb="tab"] {{
  height:2.6rem; padding:0 1.05rem; font-size:.855rem; font-weight:500;
  color:{MUTED}; letter-spacing:.005em;
}}
.stTabs [aria-selected="true"] {{color:{INK}; font-weight:600;}}

/* ---- typography helpers ---- */
.eyebrow {{letter-spacing:.15em; text-transform:uppercase; font-size:.68rem;
          font-weight:600; color:{MUTED};}}
.hero-h1 {{font-size:2.05rem; line-height:1.2; font-weight:600; margin:.4rem 0 .75rem;
          letter-spacing:-.02em; color:{INK};}}
.hero-sub {{font-size:.98rem; color:{INK_2}; max-width:50rem; line-height:1.62;}}
.sec-h {{font-size:.7rem; font-weight:600; letter-spacing:.13em; text-transform:uppercase;
        color:{MUTED}; margin:.35rem 0 .65rem;}}
.note {{font-size:.8rem; color:{MUTED}; line-height:1.55;}}

/* ---- cards ---- */
.card {{border:1px solid {LINE}; border-radius:6px; padding:1.1rem 1.2rem;
       background:{SURFACE}; height:100%;}}
.card h4 {{margin:0 0 .45rem; font-size:.92rem; font-weight:600; color:{INK};
          letter-spacing:-.005em;}}
.card p {{margin:0; color:{INK_2}; font-size:.855rem; line-height:1.62;}}

/* ---- stat tiles ---- */
.tiles {{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.5rem;}}
.tile {{border:1px solid {LINE}; border-radius:6px; padding:.85rem .95rem; background:{SURFACE};
       border-top:2px solid var(--accent,{LINE});}}
.tile .k {{font-size:.665rem; font-weight:600; letter-spacing:.055em; text-transform:uppercase;
          color:{MUTED}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}}
.tile .v {{font-size:1.72rem; font-weight:600; line-height:1.2; margin-top:.28rem; color:{INK};
          font-variant-numeric:tabular-nums; letter-spacing:-.02em;}}
.tile .s {{font-size:.735rem; color:{MUTED}; margin-top:.2rem; line-height:1.4;}}

/* ---- status pills ---- */
.pill {{display:inline-flex; align-items:center; gap:.36rem; border-radius:3px;
       padding:.18rem .55rem; font-size:.735rem; font-weight:500; white-space:nowrap;
       border:1px solid transparent; letter-spacing:.005em;}}
.pill .dot {{font-size:.58rem; line-height:1;}}
.pills {{display:flex; flex-wrap:wrap; gap:.35rem; margin:.45rem 0 .15rem;}}

/* ---- verdict banner ---- */
.verdict {{border-radius:6px; padding:.95rem 1.15rem; border:1px solid transparent;
          border-left-width:3px; display:flex; gap:.8rem; align-items:flex-start;}}
.verdict .vt {{font-weight:600; font-size:.95rem; margin-bottom:.2rem;
              letter-spacing:-.005em;}}
.verdict .vb {{font-size:.845rem; line-height:1.58;}}

/* ---- process strip ---- */
.flow {{display:flex; flex-wrap:wrap; gap:.3rem;}}
.flow span {{background:{SURFACE}; border:1px solid {LINE}; border-radius:3px;
            padding:.28rem .6rem; font-size:.745rem; color:{MUTED}; white-space:nowrap;
            letter-spacing:.02em;}}
.flow span.gate {{background:{STATUS['GAP']['tint']}; border-color:{STATUS['GAP']['fill']}55;
                 color:{STATUS['GAP']['ink']}; font-weight:600;}}

/* ---- claim inspector ---- */
.chain {{border:1px solid {LINE}; border-left:2px solid {BRAND}; border-radius:0 5px 5px 0;
        background:{SURFACE}; padding:.75rem 1rem; margin-bottom:.4rem;}}
.chain .cl {{font-size:.665rem; font-weight:600; letter-spacing:.13em; text-transform:uppercase;
            color:{MUTED}; margin-bottom:.3rem;}}
.chain .cv {{font-size:.895rem; color:{INK}; line-height:1.62;}}
.quote {{color:{INK_2};}}
.mono {{font-size:.8rem; color:{INK_2}; line-height:1.7;}}

/* ---- misc ---- */
.cta {{margin-top:1.15rem; font-size:.9rem; color:{INK_2}; line-height:1.6;}}
.cta b {{color:{INK}; font-weight:600;}}
hr {{border-color:{LINE};}}
[data-testid="stMetricValue"] {{font-size:1.4rem; font-weight:600;
                               font-variant-numeric:tabular-nums;}}
[data-testid="stMetricLabel"] {{font-size:.72rem; letter-spacing:.08em;
                               text-transform:uppercase; color:{MUTED};}}
.stDownloadButton button, .stButton button {{border-radius:4px; font-weight:500;
                                             font-size:.855rem;}}
code {{color:{INK_2}; font-size:.82rem;}}
table.readiness {{width:100%; border-collapse:collapse; font-size:.855rem;}}
table.readiness th {{text-align:left; padding:.35rem .75rem; font-size:.665rem;
                    letter-spacing:.12em; text-transform:uppercase; color:{MUTED};
                    font-weight:600; border-bottom:1px solid {LINE};}}
table.readiness td {{padding:.5rem .75rem; border-bottom:1px solid {LINE};
                    color:{INK_2};}}
table.readiness td.num {{text-align:right; font-variant-numeric:tabular-nums;}}
table.readiness td b {{color:{INK}; font-weight:500;}}
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
            f'border-color:{role["fill"]}55;border-left-color:{role["fill"]}">'
            f'<div><div class="vt" style="color:{role["ink"]}">{title}</div>'
            f'<div class="vb" style="color:{INK_2}">{body}</div></div></div>')


def chain_step(label: str, value: str, extra_class: str = "") -> str:
    return (f'<div class="chain"><div class="cl">{label}</div>'
            f'<div class="cv {extra_class}">{value}</div></div>')


# --------------------------------------------------------------------------- #
# Charts (Altair) -- thin marks, recessive axes, tooltips, no chart junk
# --------------------------------------------------------------------------- #
def coverage_bar(counts: dict[str, int]):
    """Disposition of every extracted requirement, as one stacked bar.

    Composition of a whole -> a single stacked bar ordered best to worst, with a
    2px surface-coloured gap between segments; direct-labelled by the pill
    legend beneath it.
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
        .mark_bar(cornerRadius=2, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("n:Q", stack="zero", axis=None, title=None),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(domain=[r["status"] for r in rows],
                                range=[status_fill(r["status"]) for r in rows]),
                legend=None,
            ),
            order=alt.Order("rank:Q", sort="ascending"),
            tooltip=[alt.Tooltip("label:N", title="Disposition"),
                     alt.Tooltip("n:Q", title="Requirements")],
        )
        .properties(height=38, background="transparent")
        .configure_view(strokeWidth=0)
    )


def evidence_bar(usage: dict[str, int]):
    """Source documents cited by the drafted claims.

    Magnitude across a named set -> horizontal bars, single series (the heading
    names it, so no legend), sorted by value, Step-sized bands so labels cannot
    collide.
    """
    import altair as alt
    import pandas as pd

    if not usage:
        return None
    df = pd.DataFrame([{"doc": k, "n": v} for k, v in usage.items()])
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopRight=2, cornerRadiusBottomRight=2, color=BRAND)
        .encode(
            y=alt.Y("doc:N", sort="-x", title=None,
                    scale=alt.Scale(paddingInner=0.5, paddingOuter=0.25),
                    axis=alt.Axis(labelColor=INK_2, labelFontSize=11.5, domain=False,
                                  ticks=False, labelPadding=10, labelLimit=190,
                                  labelFont="IBM Plex Mono")),
            x=alt.X("n:Q", title=None,
                    axis=alt.Axis(labelColor=MUTED, labelFontSize=10.5, grid=True,
                                  gridColor=LINE, domain=False, ticks=False,
                                  tickMinStep=1, format="d")),
            tooltip=[alt.Tooltip("doc:N", title="Document"),
                     alt.Tooltip("n:Q", title="Claims citing it")],
        )
        .properties(height=alt.Step(32), background="transparent")
        .configure_view(strokeWidth=0)
    )
