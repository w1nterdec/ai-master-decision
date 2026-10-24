"""页面五｜风险与路径规划。

职责：围绕「只有一次考研机会」这一约束，说明风险来源与准备事项。
纪律：
    * 只说明**风险与不确定性**，不给录取概率、不给"上岸率"；
    * 历史名额只作为历史事实展示，并标注口径与年份；
    * 数据缺口与"已有数据但未结构化"分开列出。
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from decision_system.models.entities import AdmissionPath
from decision_system.services import view_service
from decision_system.ui.blocks import (
    path_label,
    path_short,
    render_demo_weight_notice,
    render_decision_explanation,
    render_disclaimer,
    render_path_header,
    render_quotas,
    render_research_dossier,
)
from decision_system.ui.formatting import pct, render_status, show_value
from decision_system.ui.viewmodels import (
    QUAL_CONFIRMED,
    EXAMPLE_BACKGROUND,
    PathSummary,
)

# 准备事项：与用户"仅一次机会"约束直接相关的通用动作（非院校推荐）
_PREP_ITEMS = (
    "确认目标路径的初试第四单元是否稳定（当前多条路径为「待核」，需以官方目录为准）",
    "确认全日制 + 统考路径在 2028 目录中的存在性（目录发布后第一时间核对）",
    "区分三种名额口径：目录计划数（含推免）/ 统考计划 / 实际录取，不互相换算",
    "补齐报考可行性相关指标的有效证据，使该维度不再显示「无法判断」",
)


def _pick(summaries: Sequence[PathSummary]) -> PathSummary:
    labels = [path_label(p) for p in summaries]
    chosen = st.selectbox("选择路径", labels, key="risk_pick")
    return summaries[labels.index(chosen)]


def _render_hard(rs) -> None:
    st.markdown("#### 硬约束")
    st.markdown(f"当前状态：{render_status(rs.hard_constraint_state)}")
    if rs.hard_constraint_reasons:
        st.markdown("判定理由：")
        for r in rs.hard_constraint_reasons:
            st.markdown(f"- {r}")
    else:
        st.caption("引擎未给出额外理由。")


def render(
    session, rows, *, threshold: float = 0.8, profile_code: str = "phase37c_demo"
) -> None:
    st.subheader("风险与路径规划")
    st.info(
        "功能状态：风险缺口与准备事项已实现。R7 调剂推荐算法、直接就业路径评分尚未实现，下面相关段落仅为说明，不是自动生成的方案。"
    )
    summaries = view_service.load_path_summaries(session, rows)
    if not summaries:
        st.info("数据库中暂无招生路径。")
        return

    st.warning(
        "本页面说明**风险与不确定性**，不提供录取概率、上岸率或任何形式的成功率估计。"
    )
    render_demo_weight_notice(profile_code)
    with st.expander("原案例风险政策（示例，需自行核对适用性）", expanded=False):
        for k, v in EXAMPLE_BACKGROUND:
            st.markdown(f"- **{k}**：{v}")

    p = _pick(summaries)
    rs = view_service.build_risk_summary(session, p)

    # Phase 6.1｜M7：历史研究信息（第一层）与该路径 2028 正式状态（第二层）分开
    with st.container(border=True):
        st.markdown("### 该路径的历史研究信息（第一层）")
        dossier = view_service.build_research_dossier(
            session, [p], title=f"{path_label(p)} 历史研究档案"
        )
        render_research_dossier(
            dossier,
            layer2_lines=(
                f"2028 正式资格：{p.qualification_2028}",
                f"硬约束：{p.eligibility}",
                f"有效覆盖率：{pct(p.coverage)}（门槛 {pct(threshold)}）",
                f"适用 2028 的已核验声明：{p.evidence.verified_2028_claims} 条",
            ),
            layer2_state=p.qualification_2028,
        )

    render_path_header(p)
    st.markdown(f"风险评估等级：{render_status(rs.risk_level)}")
    if p.qualification_2028 != QUAL_CONFIRMED:
        st.caption(
            "等级显示为「暂无数据」的原因是：2028 正式资格未确认，"
            "风险无法被可靠量化——这是**证据不足**，不是「风险低」。"
        )

    # Phase 7.0｜四层决策解释（L1-L4，含「不二战」全局政策与失败后备路径）
    orm_path = session.get(AdmissionPath, p.path_id)
    if orm_path is not None:
        expl = view_service.build_path_decision_explanation(
            session, orm_path, p, archive=None
        )
        render_decision_explanation(expl, expanded=False)

    _render_hard(rs)

    st.markdown("---")
    st.markdown("### 2028 资格不确定性")
    if p.qualification_2028 != QUAL_CONFIRMED:
        st.error(
            f"该路径的 2028 正式资格为「{p.qualification_2028}」，"
            "即**未取得**。在 2028 招生目录发布并通过严格核验之前，"
            "不能把它当作一个确定的报考选项。"
        )
        st.caption(
            f"该路径已核验声明 {p.evidence.verified_claims} 条，"
            f"其中适用 2028 的 **{p.evidence.verified_2028_claims} 条**。"
            "历史年度（如 2027）的已核实事实只能说明该路径**历史上存在**，"
            "不能证明 2028 仍然存在。"
        )
    else:
        st.success("该路径已确认 2028 正式资格。")

    st.markdown("---")
    st.markdown("### 一志愿风险")
    for item in rs.first_choice:
        st.markdown(f"- {item}")
    with st.expander("历史名额明细（分口径，仅供参照）", expanded=False):
        render_quotas(p)
        st.caption("历史名额**不代表 2028 计划**，也不得换算成录取难度。")

    st.markdown("### 调剂路径")
    for item in rs.transfer:
        st.markdown(f"- {item}")
    st.caption(
        "调剂是否可接受取决于**培养价值证据**是否充分；"
        "当前库内无调剂路径记录，也不存在足够证据支持调剂推荐。"
    )

    st.markdown("### 就业与长期衔接")
    for item in rs.employment:
        st.markdown(f"- {item}")
    st.caption("本模块不做就业预测，只说明与已确认方向相关的事实与缺口。")

    st.markdown("---")
    st.markdown("### 数据缺口（按优先级排序）")
    if not rs.gaps:
        st.success("该路径未发现阻断性数据缺口。")
    else:
        for g in rs.gaps:
            tag = (
                "🔴"
                if g.priority_text == "高"
                else ("🟠" if g.priority_text == "中" else "🟡")
            )
            with st.container(border=True):
                st.markdown(f"{tag} **{g.topic}**（优先级：{g.priority_text}）")
                st.caption(g.reason)
                if g.data_exists_but_unstructured:
                    st.caption(
                        "类型：数据已存在但未结构化/未核验 → 可通过补登记与核验解决。"
                    )
                else:
                    st.caption("类型：数据本身缺失 → 需要新增采集。")

    st.markdown("### 准备事项")
    for i, item in enumerate(_PREP_ITEMS, 1):
        st.markdown(f"{i}. {item}")
    st.caption("以上为通用准备动作，**不指向任何具体学校**。")

    st.markdown("---")
    st.markdown("### 全部路径的阻断性缺口概览")
    all_gaps = view_service.build_risk_gaps(session, summaries)
    if all_gaps:
        for g in all_gaps:
            st.markdown(f"- **{g.topic}** — {g.reason}")
    else:
        st.caption("暂无。")
    render_disclaimer()
