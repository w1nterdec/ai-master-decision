"""【项目总览】状态看板（Task F）。全部数字来自数据库实查。"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from decision_system.models.entities import (
    AdmissionPath,
    AdmissionRecord,
    Indicator,
    Mentor,
    ResearchResource,
    School,
    ScoreRecord,
    WeightProfile,
)
from decision_system.models.enums import Verification2028
from decision_system.services.evidence_service import evidence_gap_stats
from decision_system.ui.decision_view import PathRow, comparable_count


def render(session, rows: Sequence[PathRow]) -> None:
    st.subheader("项目总览")
    g = evidence_gap_stats(session)

    school_n = session.execute(select(func.count(School.id))).scalar_one()
    path_n = session.execute(select(func.count(AdmissionPath.id))).scalar_one()
    score_total = session.execute(select(func.count(ScoreRecord.id))).scalar_one()
    score_filled = session.execute(
        select(func.count(ScoreRecord.id)).where(ScoreRecord.raw_score.is_not(None))
    ).scalar_one()
    y2028_ok = session.execute(
        select(func.count(AdmissionPath.id)).where(
            AdmissionPath.verification_2028 == Verification2028.VERIFIED
        )
    ).scalar_one()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("学校数量", school_n)
    c2.metric("招生路径数量", path_n)
    c3.metric("可比较路径数量", comparable_count(rows))
    c4.metric("待处理证据冲突", g["conflict_unresolved"])

    st.markdown("#### 进度")
    reg_ratio = g["source_registered"] / g["source_total"] if g["source_total"] else 0.0
    ver_ratio = g["source_verified"] / g["source_total"] if g["source_total"] else 0.0
    score_ratio = score_filled / score_total if score_total else 0.0
    y2028_ratio = y2028_ok / path_n if path_n else 0.0

    p1, p2 = st.columns(2)
    with p1:
        st.markdown(f"证据来源登记进度：{g['source_registered']}/{g['source_total']}")
        st.progress(reg_ratio)
        st.markdown(f"证据核验进度：{g['source_verified']}/{g['source_total']}（来源）")
        st.progress(ver_ratio)
    with p2:
        st.markdown(f"评分完成度：{score_filled}/{score_total}")
        st.progress(score_ratio)
        st.markdown(f"2028 招生资格核验进度：{y2028_ok}/{path_n}")
        st.progress(y2028_ratio)

    st.markdown("#### 下一步待办（根据真实数据库状态生成）")
    todos = _build_todos(
        session,
        gap=g,
        school_n=school_n,
        path_n=path_n,
        y2028_ok=y2028_ok,
        score_total=score_total,
        score_filled=score_filled,
    )
    if not todos:
        st.success("当前没有待办事项。")
    else:
        for t in todos:
            st.markdown(f"- [ ] {t}")

    st.caption("待办依据数据库实时计算，演示数据不计入研究进度。")


def _build_todos(
    session,
    *,
    gap: dict,
    school_n: int,
    path_n: int,
    y2028_ok: int,
    score_total: int,
    score_filled: int,
) -> list[str]:
    todos: list[str] = []
    unregistered = gap["source_total"] - gap["source_registered"]
    if unregistered > 0:
        todos.append(f"补充缺失来源本体登记：{unregistered} 条来源仍无 URL/文件标识或发布机构")
    if gap["claim_candidate"] > 0:
        todos.append(f"核验候选证据映射：{gap['claim_candidate']} 条声明仍为「候选映射」，不可用于评分")
    if gap["conflict_unresolved"] > 0:
        todos.append(f"处理未解决证据冲突：{gap['conflict_unresolved']} 条")
    if path_n and y2028_ok < path_n:
        todos.append(f"完成 2028 招生资格核验：{path_n - y2028_ok}/{path_n} 条路径仍为「待2028核验」")
    if score_total and score_filled < score_total:
        todos.append(f"补充指标评分：{score_filled}/{score_total} 个评分格已有有效评分")

    mentor_n = session.execute(select(func.count(Mentor.id))).scalar_one()
    resource_n = session.execute(select(func.count(ResearchResource.id))).scalar_one()
    record_n = session.execute(select(func.count(AdmissionRecord.id))).scalar_one()
    if mentor_n == 0:
        todos.append("完善导师数据：当前 0 条导师记录")
    if resource_n == 0:
        todos.append("完善科研资源数据：当前 0 条记录")
    if record_n == 0:
        todos.append("补充招生记录：当前 0 条（计划人数与实际录取需分别登记）")

    profiles = session.execute(select(WeightProfile)).scalars().all()
    if profiles and all(p.is_demo for p in profiles):
        todos.append("确认权重配置：当前仅有演示配置，尚未派生并确认用户正式偏好")
    return todos
