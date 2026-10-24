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

from decision_system.ui.theme import data_table
from sqlalchemy import select

from decision_system.models.entities import AdmissionPath, WeightProfile
from decision_system.services import view_service
from decision_system.ui.blocks import (
    get_archive,
    path_label,
    render_demo_weight_notice,
    render_decision_explanation,
    render_disclaimer,
    render_research_dossier,
)
from decision_system.ui.formatting import pct, show_value
from decision_system.ui.viewmodels import (
    QUAL_CONFIRMED,
    EXAMPLE_BACKGROUND,
    PathSummary,
    SchoolSummary,
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


def _focus_schools(
    session,
    summaries: Sequence[PathSummary],
    schools: Sequence[SchoolSummary],
    archive,
) -> list[tuple[SchoolSummary, list[PathSummary]]]:
    """重点研究学校 = **用户自己在档案里标记过的路径**所属的学校。

    系统**不预设**任何学校为重点/最优；未标记即为空。
    """
    marked = list(archive.favorite_path_ids) + [
        i for i in archive.candidate_path_ids if i not in archive.favorite_path_ids
    ]
    excluded = set(archive.excluded_path_ids)
    by_id = {p.path_id: p for p in summaries}
    by_code: dict[str, list[PathSummary]] = {}
    for pid in marked:
        if pid in excluded:
            continue
        p = by_id.get(pid)
        if p is None:
            continue
        by_code.setdefault(p.school_code, []).append(p)
    out: list[tuple[SchoolSummary, list[PathSummary]]] = []
    for s in schools:
        if s.code in by_code:
            out.append((s, by_code[s.code]))
    return out


def _render_focus(session, focus, *, threshold: float) -> None:
    archive = get_archive()
    st.markdown("### 我重点研究的学校")
    if not focus:
        st.info(
            "你还没有把任何路径标记为「重点关注」或「候选」。"
            "标记后，这里会显示该学校的**已核实历史事实、优势与风险、最重要的待核验问题**。\n\n"
            "系统不会替你指定重点学校——重点由你的档案决定。"
        )
        return

    for s, paths in focus:
        with st.container(border=True):
            st.markdown(f"#### {s.name}")
            st.caption(
                f"地区：{show_value(s.region)}　|　在库路径 {s.path_count} 条　|　"
                f"2028 资格：{s.qualification_2028}"
            )
            dossier = view_service.build_research_dossier(
                session, paths, title=f"{s.name} 历史研究档案"
            )
            lines = [
                f"2028 正式资格：{s.qualification_2028}"
                f"（{'已确认' if s.qualification_2028 == QUAL_CONFIRMED else '未确认，按未取得处理'}）",
                f"该学校在库路径的有效覆盖率："
                + "；".join(pct(p.coverage) for p in paths),
            ]
            render_research_dossier(
                dossier, layer2_lines=lines, layer2_state=s.qualification_2028
            )

            st.markdown("**最重要的待核验问题**")
            gaps = view_service.build_risk_gaps(session, paths)
            if not gaps:
                st.caption("该学校暂无阻断性数据缺口记录。")
            for g in gaps[:3]:
                tag = (
                    "🔴"
                    if g.priority_text == "高"
                    else ("🟠" if g.priority_text == "中" else "🟡")
                )
                st.markdown(f"{tag} **{g.topic}**（优先级：{g.priority_text}）")
                st.caption(g.reason)
            st.caption(
                "以上问题按**对结论的影响力**排序，不是同等优先级；"
                "标为「可能改变选择」的项属于前提级信息。"
            )
            for p in paths:
                st.markdown(
                    f"- 我标记的路径：{path_label(p)}（{p.direction or '未分方向'}）"
                )
                orm_path = session.get(AdmissionPath, p.path_id)
                if orm_path is not None:
                    expl = view_service.build_path_decision_explanation(
                        session, orm_path, p, archive=archive
                    )
                    render_decision_explanation(expl, expanded=False)


def render(session, rows, *, profile_code: str, threshold: float = 0.8) -> None:
    st.subheader("决策驾驶舱")
    from decision_system.ui.research_blocks import get_catalog

    catalog = get_catalog()
    if catalog is not None:
        st.markdown("### 从研究到决策")
        st.caption(
            f"已整理 {len(catalog.paths)} 条招生路径、{len(catalog.records)} 条研究映射。资料可搜索、按主题对比，并回查底稿行号。"
        )

        def navigate(page):
            st.session_state["nav_page"] = page

        c1, c2, c3 = st.columns(3)
        c1.button(
            "探索招生路径", on_click=navigate, args=("② 院校探索",), width="stretch"
        )
        c2.button(
            "搜索研究资料", on_click=navigate, args=("⑧ 研究资料库",), width="stretch"
        )
        c3.button(
            "对比候选路径", on_click=navigate, args=("③ 多校对比",), width="stretch"
        )
    summaries = view_service.load_path_summaries(session, rows)
    schools = view_service.build_school_summaries(
        session, summaries, threshold=threshold
    )

    if not summaries:
        st.info("数据库中暂无招生路径，请先导入数据（高级功能 → 数据维护）。")
        return

    # --- 顶部状态条 -------------------------------------------------------
    st.caption(
        f"评估年份：2028　|　权重配置：`{profile_code}`　|　"
        f"覆盖率门槛：{threshold:.0%}　|　证据闸门：严格（年份不匹配即拒）"
    )

    # 审计项 A-01：驾驶舱此前完全没有演示权重提示
    prof = session.execute(
        select(WeightProfile).where(WeightProfile.code == profile_code)
    ).scalar_one_or_none()
    render_demo_weight_notice(
        profile_code, is_demo=True if prof is None else bool(prof.is_demo)
    )

    confirmed = [p for p in summaries if p.qualification_is_confirmed]
    if not confirmed:
        st.warning(
            "**当前没有任何路径取得 2028 正式资格。**\n\n"
            f"本地资料尚未收录可确认资格的 2028 招生目录，库内 {len(summaries)} 条路径均为**历史候选路径**。"
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
            tag = (
                "🔴"
                if g.priority_text == "高"
                else ("🟠" if g.priority_text == "中" else "🟡")
            )
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

    # --- 我重点研究的学校（来自用户档案，非系统预设） ----------------------
    archive = get_archive()
    _render_focus(
        session,
        _focus_schools(session, summaries, schools, archive),
        threshold=threshold,
    )
    st.caption("「重点研究学校」由**你在档案中的标记**决定，系统不预先指定任何学校。")

    # --- 公开示例背景 -----------------------------------------------------
    with st.expander("示例场景前提（不代表当前使用者）", expanded=False):
        for k, v in EXAMPLE_BACKGROUND:
            st.markdown(f"- **{k}**：{v}")
        st.caption(
            "以上为公开示例；你的条件请在我的决策档案填写。示例不自动成为你的硬约束，也不用于推断录取概率。"
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
    data_table(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "2028 资格": st.column_config.TextColumn(
                help="仅「已确认」才算取得 2028 正式资格"
            ),
            "有效覆盖率": st.column_config.TextColumn(
                help="有效证据权重 / 有权重指标总权重；未知不计入分子，也不冒充 0"
            ),
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
