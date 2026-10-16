"""Phase 6.0｜页面共享渲染块。

职责：把 ViewModel 渲染成一致的页面片段，避免六个页面各写一套。
纪律：
    * 只做展示，**不做任何计算**；状态与数值全部来自 ViewModel / engine。
    * 未知一律显示「暂无数据 / 待核验 / 证据不足 / 无法判断」，绝不补 0。
    * 不做院校排名、不输出录取概率。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from decision_system.services.view_service import load_archive, save_archive
from decision_system.ui.formatting import (
    MISSING_TEXT,
    quota_text,
    render_status,
    show_value,
)
from decision_system.ui.viewmodels import (
    NOT_APPLICABLE,
    UNKNOWN,
    UNJUDGEABLE,
    PathSummary,
)

ARCHIVE_KEY = "_phase6_archive"


# ---------------------------------------------------------------------------
# 档案读写（session 内缓存 + 轻量落盘，不改数据库结构）
# ---------------------------------------------------------------------------
def get_archive():
    if ARCHIVE_KEY not in st.session_state:
        st.session_state[ARCHIVE_KEY] = load_archive()
    return st.session_state[ARCHIVE_KEY]


def persist_archive() -> None:
    save_archive(get_archive())


def toggle_candidate(path_id: int) -> None:
    a = get_archive()
    if path_id in a.candidate_path_ids:
        a.candidate_path_ids.remove(path_id)
    else:
        a.candidate_path_ids.append(path_id)
    persist_archive()


def toggle_favorite(path_id: int) -> None:
    a = get_archive()
    if path_id in a.favorite_path_ids:
        a.favorite_path_ids.remove(path_id)
    else:
        a.favorite_path_ids.append(path_id)
    persist_archive()


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------
def path_label(p: PathSummary) -> str:
    """用户可读路径标签：学校 · 学院 · 专业代码 · 方向（不暴露 path_key）。"""
    bits = [p.school_name]
    if p.college_name:
        bits.append(p.college_name)
    if p.program_code and p.program_code != UNKNOWN:
        bits.append(p.program_code)
    if p.direction:
        bits.append(p.direction)
    return " · ".join(bits)


def path_short(p: PathSummary) -> str:
    extra = f"（{p.direction}）" if p.direction else ""
    return f"{p.school_name} {p.program_code}{extra}"


def evidence_counts_text(p: PathSummary) -> str:
    e = p.evidence
    if e.total_claims == 0:
        return "暂无关联证据"
    return (
        f"声明 {e.total_claims} 条：已核验 {e.verified_claims}、"
        f"候选 {e.candidate_claims}、待核验 {e.pending_claims}"
    )


# ---------------------------------------------------------------------------
# 渲染块
# ---------------------------------------------------------------------------
def render_path_header(p: PathSummary) -> None:
    st.markdown(f"#### {path_label(p)}")
    st.caption(
        f"{p.study_mode} · {p.admission_method} · {p.path_kind} · "
        f"{p.admission_year} 年 · 培养地点 {show_value(p.training_location)}"
    )


def render_qualification(p: PathSummary) -> None:
    """2028 资格 + 硬约束：两者分开显示，不互相替代。"""
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**2028 正式资格**：{render_status(p.qualification_2028)}")
    c2.markdown(f"**硬约束状态**：{render_status(p.eligibility)}")
    c3.markdown(f"**证据状态**：{render_status(p.evidence.state)}")
    if not p.qualification_is_confirmed:
        st.caption(
            "未确认即按**未取得 2028 正式资格**处理："
            "历史招生事实不得冒充 2028，2028 目录发布前任何结论都只是候选判断。"
        )


def render_path_facts(p: PathSummary) -> None:
    rows = [
        {"项目": "考试科目（第四单元）", "内容": show_value(p.exam_unit4)},
        {"项目": "招生方向", "内容": show_value(p.direction)},
        {"项目": "学习方式", "内容": show_value(p.study_mode)},
        {"项目": "招生方式", "内容": show_value(p.admission_method)},
        {"项目": "路径角色", "内容": show_value(p.path_kind)},
        {"项目": "培养地点", "内容": show_value(p.training_location)},
        {"项目": "招生年份", "内容": str(p.admission_year)},
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_quotas(p: PathSummary) -> None:
    """名额分口径展示：目录计划 / 统考计划 / 实际录取，绝不合并。"""
    if not p.quotas:
        st.info("暂无招生名额记录（三种口径均无数据，**不显示为 0**）。")
        return
    rows = [
        {
            "年份": q.year,
            "口径": q.basis,
            "招生方式": q.method,
            "计划": q.planned if q.planned is not None else MISSING_TEXT,
            "实际录取": q.actual if q.actual is not None else MISSING_TEXT,
            "声明状态": show_value(q.claim_status),
        }
        for q in p.quotas
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("三种口径含义不同，不得互相换算或合并。")


def render_evidence_list(p: PathSummary, *, limit: int | None = 8) -> None:
    items = p.evidence.items
    if not items:
        st.info("暂无关联证据声明。")
        return
    shown = items if limit is None else items[:limit]
    for it in shown:
        year_tag = "🟢 2028" if it.is_2028 else f"🕓 {it.year_text}"
        st.markdown(
            f"- {year_tag} ｜状态 {render_status(it.status)}｜来源 {render_status(it.source_status)}"
        )
        st.caption(f"　{show_value(it.statement)}（来源：{it.source_title}）")
    if limit is not None and len(items) > limit:
        st.caption(f"（仅显示前 {limit} 条，共 {len(items)} 条）")
    st.caption("仅「已核验」且适用年份含 2028 的声明，才可能支撑 2028 正式资格判断。")


def render_unknown(p: PathSummary) -> None:
    if not p.unknown_indicators:
        st.caption("当前路径无「未知指标」记录。")
        return
    st.markdown(f"**尚未取得有效数据的指标（{len(p.unknown_indicators)} 项）**")
    st.dataframe(
        pd.DataFrame({"指标": list(p.unknown_indicators)}),
        hide_index=True,
        width="stretch",
    )
    st.caption("未知不按 0 参与计算，也不参与覆盖率分母之外的推断。")


def render_archive_actions(p: PathSummary, *, key_prefix: str = "") -> None:
    a = get_archive()
    in_cand = p.path_id in a.candidate_path_ids
    in_fav = p.path_id in a.favorite_path_ids
    c1, c2 = st.columns(2)
    if c1.button(
        "★ 取消候选" if in_cand else "☆ 加入候选",
        key=f"{key_prefix}cand_{p.path_id}",
        width="stretch",
    ):
        toggle_candidate(p.path_id)
    if c2.button(
        "♥ 取消关注" if in_fav else "♡ 加入关注",
        key=f"{key_prefix}fav_{p.path_id}",
        width="stretch",
    ):
        toggle_favorite(p.path_id)


def render_disclaimer() -> None:
    st.caption(
        "本系统**不输出录取概率**、**不做院校排名**。"
        "所有「无法判断」均为证据不足时的正确系统行为，不是界面故障。"
    )


def render_comparison_legend() -> None:
    st.caption(
        f"图例：{UNKNOWN}＝数据库无该字段；{UNJUDGEABLE}＝有字段但证据不足以判断；"
        f"{NOT_APPLICABLE}＝该维度对此路径不适用。三者**均不是 0**。"
    )
