"""页面三｜多校对比。

职责：把若干路径放在同一张表里**并列事实**，让用户自己看差异。
纪律：
    * 比较单位 = **路径**（学校+学院+专业+学习方式+方向），不是"学校"；
    * 证据不足的维度显示「无法判断」，**绝不**补 0 后比较；
    * **不宣布赢家**、不排名、不输出录取概率。
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st

from decision_system.services import view_service
from decision_system.ui.blocks import (
    path_short,
    render_comparison_legend,
    render_demo_weight_notice,
    render_disclaimer,
)
from decision_system.ui.formatting import pct, render_status
from decision_system.ui.viewmodels import PathSummary

MAX_SELECT = 4


def _select_paths(summaries: Sequence[PathSummary]) -> list[PathSummary]:
    options = {p.path_id: p for p in summaries}
    default = [
        pid
        for pid in st.session_state.get("compare_selection", [])
        if pid in options
    ]
    picked = st.multiselect(
        f"选择要对比的路径（最多 {MAX_SELECT} 条；比较单位是「路径」，不是学校）",
        options=list(options.keys()),
        default=default or [p.path_id for p in summaries[:2]],
        format_func=lambda pid: path_short(options[pid]),
        max_selections=MAX_SELECT,
        key="compare_multiselect",
    )
    st.session_state["compare_selection"] = picked
    return [options[pid] for pid in picked]


def render(session, rows, *, threshold: float = 0.8, profile_code: str = "phase37c_demo") -> None:
    st.subheader("多校对比")
    summaries = view_service.load_path_summaries(session, rows)
    if len(summaries) < 2:
        st.info("至少需要 2 条路径才能对比。")
        return

    render_demo_weight_notice(profile_code)
    st.caption(
        "比较单位是**招生路径**（学校+学院+专业+学习方式+方向）。"
        "同一专业的不同方向是**各自独立的路径**，应当并列比较，而不是先看学校再看方向。"
    )

    picked = _select_paths(summaries)
    if len(picked) < 2:
        st.info("请至少选择 2 条路径。")
        render_disclaimer()
        return

    comp = view_service.build_comparison(session, picked)

    st.caption("比较对象：" + "　｜　".join(path_short(p) for p in comp.paths))

    judgeable = comp.judgeable_rows
    if judgeable == 0:
        st.warning(
            "**当前没有任何维度具备可判断的差异。**\n\n"
            "原因：各路径的评分型维度均处于「无法判断」（无有效评分），"
            "可展示的只有事实字段。这是证据不足时的**正确系统行为**。"
        )
    else:
        st.info(f"{judgeable} / {len(comp.rows)} 个维度存在差异且证据足以判断。")

    table = []
    for dim, cells in comp.rows:
        row: dict[str, str] = {"维度": dim}
        for p, c in zip(comp.paths, cells):
            row[path_short(p)] = c.text
        table.append(row)
    df = pd.DataFrame(table)

    def _style(val: str) -> str:
        if val in ("暂无数据", "无法判断", "不适用", "待核验"):
            return "color: #9aa0a6;"
        return ""

    st.dataframe(
        df.style.map(_style),
        hide_index=True,
        width="stretch",
    )
    render_comparison_legend()

    st.markdown("### 证据与覆盖率")
    ev_rows = [
        {
            "路径": path_short(p),
            "2028 资格": p.qualification_2028,
            "硬约束": p.eligibility,
            "有效覆盖率": pct(p.coverage),
            "覆盖率门槛": pct(threshold),
            "声明总数": p.evidence.total_claims,
            "已核验": p.evidence.verified_claims,
            "已核验且含 2028": p.evidence.verified_2028_claims,
        }
        for p in comp.paths
    ]
    st.dataframe(pd.DataFrame(ev_rows), hide_index=True, width="stretch")

    st.error("本表**不产生排名，也不宣布最优选择**。")
    st.caption(
        "「差异」仅指字段值不同；是否重要取决于你的偏好权重。"
        "在权重经你确认之前，本系统不会替你判断哪条更好。"
    )
    render_disclaimer()
