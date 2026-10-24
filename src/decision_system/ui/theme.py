"""Shared visual system and responsive, semantic read views for every data table."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

STYLE = """
<style>
:root { --research-ink:#17352e; --research-accent:#116b55; }
.stApp { background: #f6f8f7; }
[data-testid="stMainBlockContainer"] { max-width:1280px; padding-top:2rem; padding-bottom:4rem; }
[data-testid="stSidebar"] { background:#edf3ef; border-right:1px solid #dce6df; }
[data-testid="stHeader"] { background:rgba(246,248,247,.95); }
h1,h2,h3,h4 { color:var(--research-ink); letter-spacing:-.025em; }
h1 { font-size:2rem !important; line-height:1.35 !important; }
h2 { font-size:1.5rem !important; }
h3 { font-size:1.18rem !important; }
.research-eyebrow { color:#116b55; font-size:.75rem; font-weight:700; letter-spacing:.16em; margin-bottom:.45rem; }
.research-lead { color:#52665b; max-width:48rem; line-height:1.7; }
[data-testid="stVerticalBlockBorderWrapper"]>div { border-radius:14px; }
[data-testid="stMetric"] { background:white; border:1px solid #dce6df; border-radius:12px; padding:1rem; }
[data-testid="stMetricValue"] { font-size:1.8rem; }
[data-testid="stMetricDelta"] { white-space:normal; }
button, input, textarea, [data-baseweb="select"] { font-size:1rem !important; }
button:focus-visible, a:focus-visible { outline:3px solid #116b55 !important; outline-offset:3px; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button { min-height:44px; border-radius:9px; }
[data-testid="stExpander"] { background:white; border-radius:10px; }
[data-testid="stExpander"] summary { min-height:48px; }
[data-testid="stMarkdownContainer"] { overflow-wrap:anywhere; }
.research-mobile-records { display:none; }
.research-mobile-records article { background:white; padding:1rem; border:1px solid #dce6df; border-radius:10px; margin:.6rem 0; }
.research-mobile-records dl { margin:0; }
.research-mobile-records dt { color:#52665b; font-size:.8rem; margin-top:.7rem; }
.research-mobile-records dd { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; }
@media (max-width:768px) {
 [data-testid="stMainBlockContainer"] { padding:1rem .85rem 3rem; }
 h1 { font-size:1.55rem !important; }
 [data-testid="stHorizontalBlock"] { flex-wrap:wrap; gap:.7rem; }
 [data-testid="stColumn"] { width:100% !important; flex:1 1 100% !important; min-width:0 !important; }
 [data-testid="stMetric"] { padding:.8rem; }
 [data-testid="stMetricLabel"] p { white-space:normal; }
 [data-testid="stRadio"] label { min-height:44px; }
 [data-testid="stTabs"] [role="tablist"] { flex-wrap:wrap; }
 [data-testid="stTabs"] [role="tab"] { min-height:44px; white-space:normal; }
 .research-mobile-records { display:block; }
 [class*="st-key-readable_"] [data-testid="stDataFrame"] { display:none; }
}
@media (prefers-color-scheme:dark) {
 /* Explicit light palette is configured in Streamlit; keep embedded read views legible. */
 .research-mobile-records article { color:#17352e; }
}
</style>
"""


def apply_theme(*, interactive_tables: bool = False) -> None:
    st.html(STYLE)
    if interactive_tables:
        st.html(
            '<style>.research-mobile-records{display:none!important}[class*="st-key-readable_"] [data-testid="stDataFrame"]{display:block!important}</style>'
        )


def table_cards(data) -> str:
    frame = (
        data.data
        if hasattr(data, "data") and isinstance(data.data, pd.DataFrame)
        else pd.DataFrame(data)
    )
    articles = []
    for index, row in enumerate(frame.to_dict(orient="records"), start=1):
        fields = "".join(
            f"<dt>{html.escape(str(k))}</dt><dd>{html.escape('暂无数据' if v is None or (pd.api.types.is_scalar(v) and pd.isna(v)) else str(v))}</dd>"
            for k, v in row.items()
        )
        articles.append(
            f'<article aria-label="记录 {index}"><dl>{fields}</dl></article>'
        )
    return '<div class="research-mobile-records">' + "".join(articles) + "</div>"


def data_table(data, **kwargs):
    """Same data on both screens; wide tables on desktop, complete key/value cards on phones.

    No columns or actions are removed. Call sites retain dataframe return values for selections.
    Large datasets use the native table instead of constructing thousands of DOM cards.
    """
    counter = st.session_state.get("_readable_table_count", 0) + 1
    st.session_state["_readable_table_count"] = counter
    frame = (
        data.data
        if hasattr(data, "data") and isinstance(data.data, pd.DataFrame)
        else pd.DataFrame(data)
    )
    if len(frame) > 250:
        st.caption("数据较多，可横向滑动表格或使用表格右上角下载完整数据。")
        return st.dataframe(data, **kwargs)
    with st.container(key=f"readable_{counter}"):
        result = st.dataframe(data, **kwargs)
        st.html(table_cards(frame))
    return result
