"""Phase 6.0｜页面共享渲染块。

职责：把 ViewModel 渲染成一致的页面片段，避免六个页面各写一套。
纪律：
    * 只做展示，**不做任何计算**；状态与数值全部来自 ViewModel / engine。
    * 未知一律显示「暂无数据 / 待核验 / 证据不足 / 无法判断」，绝不补 0。
    * 不做院校排名、不输出录取概率。
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st

from decision_system.services.view_service import load_archive, save_archive
from decision_system.services.decision_policy import DecisionExplanation
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
    FactItem,
    PathSummary,
    ResearchDossier,
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


def toggle_excluded(path_id: int) -> None:
    """暂不考虑（用户自己的标记，不改证据真实性、不改评分）。"""
    a = get_archive()
    if path_id in a.excluded_path_ids:
        a.excluded_path_ids.remove(path_id)
    else:
        a.excluded_path_ids.append(path_id)
        # 与「候选/关注」互斥：标记暂不同时不列入候选与关注
        if path_id in a.candidate_path_ids:
            a.candidate_path_ids.remove(path_id)
        if path_id in a.favorite_path_ids:
            a.favorite_path_ids.remove(path_id)
    persist_archive()


def save_path_note(path_id: int, text: str) -> None:
    """保存用户对某条路径的判断与理由。"""
    a = get_archive()
    a.set_note(path_id, text)
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
    """用户标记：候选 / 重点关注 / 暂不考虑。

    纪律：用户标记只影响「我怎么看」，**不改变证据真实性、不自动修改任何评分**。
    """
    a = get_archive()
    in_cand = p.path_id in a.candidate_path_ids
    in_fav = p.path_id in a.favorite_path_ids
    in_exc = p.path_id in a.excluded_path_ids
    c1, c2, c3 = st.columns(3)
    if c1.button(
        "★ 取消候选" if in_cand else "☆ 加入候选",
        key=f"{key_prefix}cand_{p.path_id}",
        width="stretch",
    ):
        toggle_candidate(p.path_id)
    if c2.button(
        "♥ 取消重点关注" if in_fav else "♡ 重点关注",
        key=f"{key_prefix}fav_{p.path_id}",
        width="stretch",
    ):
        toggle_favorite(p.path_id)
    if c3.button(
        "↩ 撤销『暂不考虑』" if in_exc else "✕ 暂不考虑",
        key=f"{key_prefix}exc_{p.path_id}",
        width="stretch",
    ):
        toggle_excluded(p.path_id)

    existing = a.note_of(p.path_id)
    note = st.text_area(
        "我对这条路径的判断与理由（仅存于你的档案，不改证据、不改评分）",
        value=existing,
        key=f"{key_prefix}note_{p.path_id}",
        height=70,
    )
    if st.button(
        "保存我的理由",
        key=f"{key_prefix}note_save_{p.path_id}",
        width="stretch",
    ):
        save_path_note(p.path_id, note)
        st.success("已保存到你的决策档案。")

    if in_exc:
        st.caption("你已把这条路径标记为「暂不考虑」。这只是你的标记，不影响证据真实性。")
    if existing:
        st.caption(f"已保存的理由：{existing}")


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


# ---------------------------------------------------------------------------
# Phase 6.1｜M7 双层展示：历史研究信息 / 2028 正式决策
# ---------------------------------------------------------------------------
def render_demo_weight_notice(profile_code: str, *, is_demo: bool = True) -> None:
    """修复审计项 A-01：驾驶舱/探索/对比/风险页此前完全没有演示权重提示。"""
    if is_demo:
        st.warning(
            f"当前权重配置 `{profile_code}` 是**演示配置（待确认）**，"
            "不是你确认过的偏好。在「动态决策树 → 配置管理」中派生并确认之前，"
            "任何基于权重的排序与评分都只能作为演示。"
        )
    else:
        st.caption(f"当前权重配置：`{profile_code}`（用户已确认偏好）")


def _render_facts(title: str, facts: Sequence[FactItem], *, icon: str, note: str) -> None:
    st.markdown(f"**{icon} {title}（{len(facts)} 条）**")
    if not facts:
        st.caption("（暂无）")
        return
    for f in facts:
        tag = "🟢 2028" if f.is_2028 else f"🕓 {f.year_text}"
        st.markdown(f"- {tag}｜{show_value(f.statement)}")
        st.caption(f"　来源：{f.source_title}（{render_status(f.source_status)}）")
        if f.limitation:
            st.caption(f"　⚠️ {f.limitation}")
    st.caption(note)


def render_research_dossier(
    dossier: ResearchDossier,
    *,
    layer2_lines: Sequence[str] = (),
    layer2_state: str | None = None,
    expanded: bool = False,
) -> None:
    """双层展示：第一层历史研究信息；第二层 2028 正式资格与决策评分。

    两层**不合并、不互相替代**：即使第二层全为「无法判断 / 未确认」，
    第一层仍然可读、有信息量。
    """
    st.markdown(f"**历史研究档案**（{dossier.counts_text}）")
    with st.expander("展开历史研究档案详情（A/B/C/D 四类）", expanded=expanded):
        st.caption(
            "第一层＝历史研究信息（A/B/C/D 四类）；"
            "第二层＝2028 正式资格与决策评分。两层不合并，历史信息不得冒充 2028。"
        )
        _render_facts(
            "A 已核实事实",
            dossier.grade_a,
            icon="✅",
            note="仅「已核验」且来源已核验的声明；可展示，但须注意其**适用年份**。",
        )
        st.markdown("")
        _render_facts(
            "B 待核验研究资料",
            dossier.grade_b,
            icon="🕓",
            note="候选映射 / 来源未登记 / 待核验。**不参与评分，不参与 2028 资格判定。**",
        )
        st.markdown("")
        _render_facts(
            "C 推断或主观评价",
            dossier.grade_c,
            icon="💭",
            note="由 A/B 推导的判断，**不是事实**。",
        )
        st.markdown("")
        st.markdown(f"**❓ D 未知（{len(dossier.unknown_topics)} 项）**")
        if dossier.unknown_topics:
            st.dataframe(
                pd.DataFrame({"尚未取得数据的指标": list(dossier.unknown_topics)}),
                hide_index=True,
                width="stretch",
            )
        st.caption("未知一律显示「未知」，**不补 0、不默认填充、不降低覆盖率要求**。")

    st.markdown("**2028 正式资格与决策评分（第二层）**")
    if layer2_state is not None:
        st.markdown(f"当前状态：{render_status(layer2_state)}")
    for line in layer2_lines:
        st.markdown(f"- {line}")
    st.caption(
        "第二层继续沿用严格证据闸门：年份不匹配即拒、候选声明不算、"
        "历史事实不得冒充 2028。"
    )


# ---------------------------------------------------------------------------
# Phase 7.0｜四层决策解释渲染（修复审计 A-02 / A-03 / A-04）
# ---------------------------------------------------------------------------
_LAYER_ICON = {
    "L1 是否值得读": "①",
    "L2 是否值得考": "②",
    "L3 失败后备路径": "③",
    "L4 动态偏好比较": "④",
}


def render_decision_explanation(expl: DecisionExplanation, *, expanded: bool = True) -> None:
    """把四层决策解释渲染为可核查的分层卡片。

    每一层都给出结论 + 依据；「不二战」作为全局政策贯穿 L3；
    演示权重在 L4 显式标注（A-01 / A-10）。
    """
    st.markdown("#### 四层决策解释")
    st.caption("结论均可核查：每一层列出判断依据，不编造综合评分或录取概率。")

    layers = [
        expl.layer1_worth_reading,
        expl.layer2_worth_testing,
        expl.layer3_fallback,
        expl.layer4_preference,
    ]
    for ly in layers:
        icon = _LAYER_ICON.get(ly.layer, "•")
        blocked = " ⛔" if ly.blocked else ""
        st.markdown(f"**{icon} {ly.layer} → {ly.verdict}{blocked}**")
        for r in ly.reasons:
            st.markdown(f"&nbsp;&nbsp;- {r}")

    with st.expander("查看全局决策政策（用户已确认，非系统推断）", expanded=False):
        for g in expl.global_policy:
            st.markdown(f"- {g}")
    if expl.gaps:
        st.markdown("**最该补充的证据（按影响排序）**")
        for g in expl.gaps[:5]:
            st.markdown(f"- {g}")
