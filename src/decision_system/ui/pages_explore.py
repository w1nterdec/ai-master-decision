"""页面二｜院校探索。

职责：按学校/地区/科目浏览候选路径，查看**事实与证据**，不下结论。
纪律：
    * 优势/风险只展示**已核验**声明；未核验的不写成优势；
    * 不打分、不排名、不输出录取概率；
    * 未知一律「暂无数据」。
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from decision_system.services import view_service
from decision_system.ui.research_blocks import render_path_research
from decision_system.ui.blocks import (
    evidence_counts_text,
    path_label,
    render_archive_actions,
    render_demo_weight_notice,
    render_disclaimer,
    render_evidence_list,
    render_path_facts,
    render_qualification,
    render_quotas,
    render_research_dossier,
    render_unknown,
)
from decision_system.ui.formatting import pct, render_status, show_value
from decision_system.ui.viewmodels import (
    NOT_APPLICABLE,
    UNKNOWN,
    PathSummary,
    SchoolSummary,
)


def _filter_bar(summaries: Sequence[PathSummary]) -> list[PathSummary]:
    schools = sorted({p.school_name for p in summaries})
    regions = sorted({p.training_location for p in summaries if p.training_location})
    exams = sorted({p.exam_unit4 for p in summaries if p.exam_unit4})
    kinds = sorted({p.path_kind for p in summaries})

    c1, c2 = st.columns(2)
    school = c1.selectbox("学校", ["全部"] + schools, key="explore_school")
    region = c2.selectbox("培养地点", ["全部"] + regions, key="explore_region")
    c3, c4 = st.columns(2)
    exam = c3.selectbox("考试科目（第四单元）", ["全部"] + exams, key="explore_exam")
    kind = c4.selectbox("路径角色", ["全部"] + kinds, key="explore_kind")

    out = list(summaries)
    if school != "全部":
        out = [p for p in out if p.school_name == school]
    if region != "全部":
        out = [p for p in out if p.training_location == region]
    if exam != "全部":
        out = [p for p in out if p.exam_unit4 == exam]
    if kind != "全部":
        out = [p for p in out if p.path_kind == kind]
    return out


def _school_card(session, s: SchoolSummary) -> None:
    with st.container(border=True):
        st.markdown(f"### {s.name}")
        st.caption(
            f"地区：{show_value(s.region)}　|　在库路径 {s.path_count} 条　|　"
            f"2028 资格：{render_status(s.qualification_2028)}"
        )
        left, right = st.columns(2)
        with left:
            st.markdown("**已核实的事实（仅已核验声明）**")
            if s.strengths:
                for t in s.strengths:
                    st.markdown(f"- {t}")
            else:
                st.caption("暂无已核验声明，不能写成优势。")
        with right:
            st.markdown("**已记录的不确定性**")
            if s.risks:
                for t in s.risks:
                    st.markdown(f"- {t}")
            else:
                st.caption("暂无记录（不代表没有风险）。")
        st.caption(f"证据：{s.evidence.summary_text}")
        st.caption(
            "研究状态："
            + ("已有已核验证据" if s.evidence.verified_claims else "尚无已核验证据")
            + f"；未登记来源 {s.evidence.unregistered_sources} 个"
            + f"；适用 2028 的已核验声明 {s.evidence.verified_2028_claims} 条"
        )
        # Phase 6.1｜M7：历史研究信息（第一层）与 2028 正式资格（第二层）分开
        dossier = view_service.build_research_dossier(
            session, list(s.paths), title=f"{s.name} 历史研究档案"
        )
        render_research_dossier(
            dossier,
            layer2_lines=(
                f"2028 正式资格：{s.qualification_2028}",
                f"适用 2028 的已核验声明：{s.evidence.verified_2028_claims} 条",
            ),
            layer2_state=s.qualification_2028,
        )


def _path_detail(session, p: PathSummary) -> None:
    render_path_facts(p)
    st.markdown("**资格与硬约束**")
    render_qualification(p)
    render_path_research(p.legacy_id, key=f"explore_research_{p.path_id}")

    with st.expander("招生名额（分口径）", expanded=False):
        render_quotas(p)
    with st.expander("证据声明", expanded=False):
        render_evidence_list(p)
    with st.expander("尚未取得数据的指标", expanded=False):
        render_unknown(p)
    if p.key_risk or p.notes:
        with st.expander("已记录的风险与备注", expanded=False):
            st.markdown(show_value(p.key_risk))
            if p.notes:
                st.caption(show_value(p.notes))
    render_archive_actions(p, key_prefix="explore_")


def render(session, rows, *, threshold: float = 0.8, profile_code: str = "phase37c_demo") -> None:
    st.subheader("院校探索")
    summaries = view_service.load_path_summaries(session, rows)
    if not summaries:
        st.info("数据库中暂无招生路径。")
        return

    schools = view_service.build_school_summaries(session, summaries, threshold=threshold)
    render_demo_weight_notice(profile_code)
    st.caption(
        "浏览的是**事实与证据**，不是推荐结果。"
        "系统不会替你指定唯一目标，也不会给出录取概率。"
    )

    filtered = _filter_bar(summaries)
    st.caption(f"筛选结果：{len(filtered)} / {len(summaries)} 条路径")
    if not filtered:
        st.warning("当前筛选条件下没有路径。")
        render_disclaimer()
        return

    codes = {p.school_code for p in filtered}
    shown = [s for s in schools if s.code in codes]
    st.caption(
        "学校排列顺序仅为展示便利（已核验证据多的在前），**不构成院校排名**。"
    )
    for s in shown:
        _school_card(session, s)
        paths = [p for p in s.paths if p.path_id in {x.path_id for x in filtered}]
        if not paths:
            continue
        labels = [path_label(p) for p in paths]
        chosen = st.selectbox(
            f"查看 {s.name} 的路径",
            labels,
            key=f"explore_path_{s.code}",
        )
        p = paths[labels.index(chosen)]
        st.markdown(
            f"考试科目：{show_value(p.exam_unit4)}　|　"
            f"有效覆盖率：{pct(p.coverage)}　|　{evidence_counts_text(p)}"
        )
        _path_detail(session, p)
        st.markdown("---")

    render_disclaimer()
