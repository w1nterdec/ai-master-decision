"""【决策分析】三情景 + 双目标（Task E）。

情景倍率与双目标相关度矩阵均为演示配置；证据不足时**不**生成排名图。
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st

from decision_system.ui.decision_view import PathRow, missing_indicators
from decision_system.ui.formatting import MISSING_TEXT, pct, render_status, score_text

SCENARIO_NAMES = {
    "career": "职业发展优先",
    "admission": "报考可行性优先",
    "research": "科研培养优先",
}


def render(session, rows: Sequence[PathRow], *, threshold: float = 0.8) -> None:
    st.subheader("决策分析")
    st.warning(
        "情景倍率与双目标相关度矩阵均为**演示配置**（未获用户确认）。"
        "当前输出不含任何录取概率，也不构成院校排名。"
    )
    if not rows:
        st.info("暂无可分析的招生路径。")
        return

    labels = [f"{r.path.legacy_path_id or r.path_key} · {r.school_name}" for r in rows]
    choice = st.selectbox("选择路径", range(len(rows)), format_func=lambda i: labels[i])
    row: PathRow = rows[choice]
    d = row.decision

    st.markdown("#### 硬约束与 2028 资格")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"硬约束状态：{render_status(d.eligibility)}")
    c2.markdown(f"2028 资格核验：{render_status(row.path.verification_2028)}")
    c3.markdown(f"2028 正式资格：{render_status(d.qualification_2028)}")
    if d.constraint_reasons:
        for r in d.constraint_reasons:
            st.caption(f"- {r}")

    st.markdown("#### 三种情景")
    st.caption(f"覆盖率门槛：{threshold:.0%}（各情景独立判断；缺失指标不计入分母，不补零）")
    scen_rows = []
    for code, agg in d.scenarios.items():
        scen_rows.append(
            {
                "情景": SCENARIO_NAMES.get(code, code),
                "有效证据覆盖率": pct(agg.weight_coverage),
                "覆盖率门槛": pct(threshold),
                "当前计算状态": str(agg.status),
                "加权分": score_text(agg.weighted_score),
                "有效指标": f"{agg.valid_count}/{agg.total_count}",
            }
        )
    st.dataframe(pd.DataFrame(scen_rows), hide_index=True, width="stretch")

    st.markdown("#### 双目标（相互独立，禁止互相复制）")
    a, b = d.objective_a, d.objective_b
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**A. 培养与职业价值（是否值得读）**")
        st.markdown(f"- 状态：{render_status(a.status)}")
        st.markdown(f"- 结果：{score_text(a.score)}")
        st.markdown(f"- 有效证据覆盖率：{pct(a.weight_coverage)}")
        if a.reasons:
            for r in a.reasons:
                st.caption(f"- {r}")
    with c2:
        st.markdown(f"**B. 一志愿报考价值（是否值得投入唯一一次考研机会）**")
        st.markdown(f"- 状态：{render_status(b.status)}")
        st.markdown(f"- 结果：{score_text(b.score)}")
        st.markdown(f"- 有效证据覆盖率：{pct(b.weight_coverage)}")
        if b.reasons:
            for r in b.reasons:
                st.caption(f"- {r}")
    st.caption("目标 A 与 B 的相关度矩阵、必备分组与门槛均不同，结果分别独立计算。")

    st.markdown("#### 缺失指标")
    miss = missing_indicators(session, row.path)
    if miss:
        st.markdown(f"共 {len(miss)} 项尚无有效评分：")
        st.dataframe(pd.DataFrame({"缺失指标": miss}), hide_index=True, width="stretch")
    else:
        st.success("该路径的全部三级指标均有评分记录。")

    st.markdown("#### 路径间比较")
    comparable = [
        r
        for r in rows
        if str(r.decision.base.status).startswith("可比较")
        and r.decision.base.weighted_score is not None
    ]
    if not comparable:
        st.error("当前尚不能形成可靠比较。")
        st.caption(
            "原因：没有路径同时满足「硬约束通过」与「覆盖率达标」。"
            "这是证据不足时的**正确系统行为**，不是界面故障。"
        )
    else:
        df = pd.DataFrame(
            [
                {
                    "路径": r.path.legacy_path_id or r.path_key,
                    "基础加权分": r.decision.base.weighted_score,
                    "覆盖率": r.decision.base.weight_coverage,
                }
                for r in comparable
            ]
        ).sort_values("基础加权分", ascending=False)
        st.dataframe(df, hide_index=True, width="stretch")
        st.bar_chart(df.set_index("路径")["基础加权分"])
        st.caption("仅在状态为「可比较（非录取预测）」时才绘制，且不构成录取预测。")

    if d.limitations:
        with st.expander("本次计算的限制说明", expanded=False):
            for lim in d.limitations:
                st.markdown(f"- {lim}")
    st.caption(f"权重配置：{d.profile_code}　评估年份：{d.evaluation_year}")
