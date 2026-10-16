"""页面一｜决策驾驶舱。

职责：回答「我现在处在什么状态、下一步该做什么」。
纪律：
    * **不推荐任何学校**、不预设最优目标、不输出录取概率；
    * 没有可比较路径时明确说明「尚不能比较」，并指向补证据动作；
    * 数据全部来自 view_service（只读）与 engine 输出。
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from decision_system.services import view_service
from decision_system.ui.blocks import (
    get_archive,
    path_label,
    render_disclaimer,
)
from decision_system.ui.formatting import pct, show_value
from decision_system.ui.viewmodels import (
    USER_CONFIRMED_BACKGROUND,
    PathSummary,
)


def _metric_row(summaries: Sequence[PathSummary], schools) -> None:
    confirmed = [p for p in summaries if p.qualification_is_confirmed]
    comparable = [
        p
        for p in summaries
        if p.decision is not None
        and str(p.decision.base.status).startswith("可比较")
        and p.decision.base.weighted_score is not None
    ]
    pending_claims = sum(p.evidence.pending_claims for p in summaries)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("在库招生路径", f"{len(summaries)} 条", f"覆盖 {len(schools)} 所学校")
    c2.metric("已确认 2028 资格", f"{len(confirmed)} 条", "未确认一律按未取得处理")
    c3.metric("当前可比较路径", f"{len(comparable)} 条", "证据不足时不比较")
    c4.metric("待核验声明", f"{pending_claims} 条", "不参与评分")


def render(session, rows, *, profile_code: str, threshold: float = 0.8) -> None:
    st.subheader("决策驾驶舱")
    summaries = view_service.load_path_summaries(session, rows)
    schools = view_service.build_school_summaries(session, summaries, threshold=threshold)

    if not summaries:
        st.info("数据库中暂无招生路径，请先导入数据（高级功能 → 数据维护）。")
        return

    # --- 顶部状态条 -------------------------------------------------------
    st.caption(
        f"评估年份：2028　|　权重配置：`{profile_code}`　|　"
        f"覆盖率门槛：{threshold:.0%}　|　证据闸门：严格（年份不匹配即拒）"
    )

    confirmed = [p for p in summaries if p.qualification_is_confirmed]
    if not confirmed:
        st.warning(
            "**当前没有任何路径取得 2028 正式资格。**\n\n"
            "2028 招生目录尚未发布，库内 10 条路径均为**历史候选路径**。"
            "这不是故障，而是严格证据闸门的正确结果：历史招生事实不得冒充 2028。"
        )
    else:
        st.success(f"{len(confirmed)} 条路径已确认 2028 正式资格。")

    _metric_row(summaries, schools)

    # --- 下一步该做什么 ---------------------------------------------------
    st.markdown("### 现在最该做什么")
    gaps = view_service.build_risk_gaps(session, summaries)
    if not gaps:
        st.success("未发现阻断性数据缺口。")
    else:
        for g in gaps[:3]:
            tag = "🔴" if g.priority_text == "高" else ("🟠" if g.priority_text == "中" else "🟡")
            with st.container(border=True):
                st.markdown(f"{tag} **{g.topic}**（优先级：{g.priority_text}）")
                st.caption(g.reason)
                flags = []
                if g.affects_hard_constraint:
                    flags.append("影响硬约束")
                if g.affects_first_choice_risk:
                    flags.append("影响一志愿风险")
                if g.may_change_choice:
                    flags.append("可能改变选择")
                st.caption(" · ".join(flags) if flags else "暂无影响标注")
    st.caption("以上为**数据缺口**，不是院校推荐。补齐证据后结论才可能改变。")

    # --- 用户已确认背景 ---------------------------------------------------
    with st.expander("我的决策前提（用户已确认，非系统推断）", expanded=False):
        for k, v in USER_CONFIRMED_BACKGROUND:
            st.markdown(f"- **{k}**：{v}")
        st.caption(
            "以上为用户在本项目中明确陈述的前提；系统不会替你改写，也不会据此推断录取概率。"
        )

    # --- 路径状态速览 -----------------------------------------------------
    st.markdown("### 各路径当前状态")
    table = [
        {
            "路径": path_label(p),
            "2028 资格": p.qualification_2028,
            "硬约束": p.eligibility,
            "有效覆盖率": pct(p.coverage),
            "证据": p.evidence.state,
            "考试科目": show_value(p.exam_unit4),
        }
        for p in summaries
    ]
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "2028 资格": st.column_config.TextColumn(help="仅「已确认」才算取得 2028 正式资格"),
            "有效覆盖率": st.column_config.TextColumn(help="有效证据权重 / 有权重指标总权重；未知不计入分子，也不冒充 0"),
        },
    )
    st.caption(
        "列表中按路径 ID 排列，**不构成排名**；"
        "「有效覆盖率」为 暂无数据 或远低于门槛时，该路径只能显示「无法判断」。"
    )

    # --- 关注与候选 -------------------------------------------------------
    archive = get_archive()
    if archive.candidate_path_ids or archive.favorite_path_ids:
        st.markdown("### 我的候选与关注")
        by_id = {p.path_id: p for p in summaries}
        for label_text, ids in (
            ("候选", archive.candidate_path_ids),
            ("关注", archive.favorite_path_ids),
        ):
            names = [path_label(by_id[i]) for i in ids if i in by_id]
            if names:
                st.markdown(f"- **{label_text}**：{('；'.join(names))}")
        st.caption("候选与关注是**用户自己的标记**，不代表系统推荐。")

    render_disclaimer()
