"""页面六｜我的决策档案。

职责：沉淀「我自己的判断过程」，可导出为 Markdown 复盘。
纪律：
    * 档案只存**用户标记与备注**，不改数据库结构（独立 JSON 文件）；
    * 演示权重与用户确认偏好**分开显示**，不混淆；
    * 导出内容同样不含录取概率、不含院校排名。
"""

from __future__ import annotations

import datetime as _dt
from typing import Sequence

import streamlit as st

from decision_system.ui.theme import data_table
from sqlalchemy import select

from decision_system.models.entities import WeightProfile
from decision_system.services import view_service
from decision_system.ui.blocks import (
    get_archive,
    path_label,
    persist_archive,
    render_disclaimer,
)
from decision_system.ui.formatting import pct, render_status
from decision_system.ui.viewmodels import (
    EXAMPLE_BACKGROUND,
    PathSummary,
)


def _profile_rows(session) -> list[dict[str, str]]:
    profiles = (
        session.execute(select(WeightProfile).order_by(WeightProfile.id))
        .scalars()
        .all()
    )
    return [
        {
            "配置代码": p.code,
            "名称": p.name,
            "性质": "用户确认偏好" if not p.is_demo else "演示配置（待确认）",
        }
        for p in profiles
    ]


def _build_markdown(
    summaries: Sequence[PathSummary],
    archive,
    profile_rows,
    *,
    profile_code: str,
) -> str:
    by_id = {p.path_id: p for p in summaries}
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# 我的决策档案（2028 AI 硕士动态择校）")
    lines.append("")
    lines.append(f"> 导出时间：{now}　|　当前权重配置：`{profile_code}`")
    lines.append(">")
    lines.append("> 本档案**不含录取概率**，也**不构成院校排名**。")
    lines.append("")

    lines.append("## 一、决策前提（本人录入，仅作上下文）")
    lines.append("")
    if not archive.personal_conditions:
        lines.append("尚未录入个人条件；原始案例背景不代表当前使用者。")
    for k, v in archive.personal_conditions.items():
        lines.append(f"- **{k}**：{v}")
    lines.append("> 个人条件仅作记录，不自动改写引擎约束、权重或原案例政策。")
    lines.append("")

    lines.append("## 二、候选路径")
    lines.append("")
    if archive.candidate_path_ids:
        for pid in archive.candidate_path_ids:
            p = by_id.get(pid)
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid} 已不在库中）'}")
            if p is not None:
                lines.append(
                    f"  - 2028 资格：{p.qualification_2028}　|　硬约束：{p.eligibility}　|　"
                    f"有效覆盖率：{pct(p.coverage)}　|　证据：{p.evidence.state}"
                )
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 三、关注路径")
    lines.append("")
    if archive.favorite_path_ids:
        for pid in archive.favorite_path_ids:
            p = by_id.get(pid)
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid} 已不在库中）'}")
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 三·补、暂不考虑的路径")
    lines.append("")
    if archive.excluded_path_ids:
        for pid in archive.excluded_path_ids:
            p = by_id.get(pid)
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid} 已不在库中）'}")
            note = archive.note_of(pid)
            if note:
                lines.append(f"  - 我的理由：{note}")
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 三·补二、我对具体路径的判断与理由")
    lines.append("")
    if archive.path_notes:
        for pid, note in archive.path_notes.items():
            p = by_id.get(int(pid)) if str(pid).isdigit() else None
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid}）'}：{note}")
    else:
        lines.append("- （暂无）")
    lines.append("")
    lines.append(
        "> 以上理由为用户自己的判断，**不改变任何证据的真实性，也不自动修改任何评分**。"
    )
    lines.append("")

    lines.append("## 四、权重配置状态")
    lines.append("")
    for r in profile_rows:
        lines.append(f"- `{r['配置代码']}`：{r['名称']}　（{r['性质']}）")
    lines.append("")
    lines.append(
        "> 演示配置仅代表示例权重结构；未点击「确认为我的正式偏好」之前，"
        "不得视为用户真实偏好。"
    )
    lines.append("")

    lines.append("## 五、我的备注")
    lines.append("")
    if archive.notes:
        for i, n in enumerate(archive.notes, 1):
            lines.append(f"{i}. {n}")
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 六、当前结论状态")
    lines.append("")
    confirmed = [p for p in summaries if p.qualification_is_confirmed]
    comparable = [
        p
        for p in summaries
        if p.decision is not None
        and str(p.decision.base.status).startswith("可比较")
        and p.decision.base.weighted_score is not None
    ]
    lines.append(f"- 在库路径：{len(summaries)} 条")
    lines.append(f"- 已确认 2028 正式资格：{len(confirmed)} 条")
    lines.append(f"- 当前可比较路径：{len(comparable)} 条")
    lines.append("")
    lines.append(
        "> 可比较路径为 0 是当前证据状态下的**正确结果**："
        "本地快照可能缺少已核验的 2028 资料或有效评分，系统不会强行给出排序。"
    )
    lines.extend(
        [
            "",
            "## 七、个人备考分层（人工假设）",
            "",
            "> 冲稳保为本人记录，非系统推荐；保不代表保证录取，不参与评分或资格判定。",
        ]
    )
    for pid, tier in archive.planning_tiers.items():
        path = by_id.get(int(pid))
        lines.append(
            f"- {path_label(path) if path else f'路径 #{pid}'}：{tier}；理由：{archive.note_of(int(pid))}"
        )
    if not archive.planning_tiers:
        lines.append("- 尚未进行人工分层。")
    lines.append("")
    return "\n".join(lines)


def render(session, rows, *, profile_code: str) -> None:
    st.subheader("我的决策档案")
    summaries = view_service.load_path_summaries(session, rows)
    archive = get_archive()
    by_id = {p.path_id: p for p in summaries}

    st.caption(
        f"档案文件：`{view_service.ARCHIVE_PATH}`"
        "　|　仅保存你的标记与备注，**不修改数据库结构**。"
    )

    st.markdown("### 我的个人条件")
    st.info(
        "个人条件用于记录与复盘，不会自动改写引擎硬约束、偏好权重或原案例政策。修改权重请到动态决策树；路径资格仍须逐条核验。"
    )
    with st.form("personal_conditions_form"):
        conditions = {}
        for field_name in (
            "本科专业",
            "目标方向",
            "意向城市",
            "可接受专业代码",
            "预算与其他限制",
        ):
            conditions[field_name] = st.text_input(
                field_name,
                value=archive.personal_conditions.get(field_name, ""),
                max_chars=1000,
                key=f"personal_{field_name}",
            )
        if st.form_submit_button("保存个人条件"):
            archive.personal_conditions = {
                k: v.strip() for k, v in conditions.items() if v.strip()
            }
            persist_archive()
            st.success("个人条件已保存，仅作决策上下文。")
    with st.expander("示例背景（仅供参照，不代表新用户）", expanded=False):
        for k, v in EXAMPLE_BACKGROUND:
            st.markdown(f"- **{k}**：{v}")

    st.markdown("### 个人备考分层（人工记录）")
    st.caption(
        "当前没有自动冲稳保算法。你可按已读证据记录自己的备考假设；“保”不代表保证录取。所有标签都不参与资格判定或评分。"
    )
    if summaries:
        pid = st.selectbox(
            "选择要记录分层的路径",
            list(by_id),
            format_func=lambda value: path_label(by_id[value]),
            key="planning_path",
        )
        tiers = ["未分层", "冲", "稳", "保"]
        with st.form(f"planning_form_{pid}"):
            tier = st.selectbox(
                "个人备考分层",
                tiers,
                index=tiers.index(archive.planning_tiers.get(str(pid), "未分层")),
                key=f"planning_tier_{pid}",
            )
            reason = st.text_area(
                "分层理由与待核验前提",
                value=archive.note_of(pid),
                max_chars=5000,
                key=f"planning_reason_{pid}",
            )
            if st.form_submit_button("保存人工分层"):
                try:
                    archive.set_planning_tier(pid, tier, reason)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    persist_archive()
                    st.success("已保存人工假设，未改变任何引擎结论。")
    else:
        st.info("暂无招生路径。可用 python scripts/start.py --demo 启动独立演示。")

    st.markdown("### 候选路径")
    if archive.candidate_path_ids:
        for pid in list(archive.candidate_path_ids):
            p = by_id.get(pid)
            name = path_label(p) if p else f"（路径 #{pid} 已不在库中）"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {name}")
            if c2.button("移除", key=f"prof_del_c_{pid}"):
                archive.candidate_path_ids.remove(pid)
                persist_archive()
    else:
        st.caption("暂无候选。可在「院校探索」中加入。")

    st.markdown("### 重点关注路径")
    if archive.favorite_path_ids:
        for pid in list(archive.favorite_path_ids):
            p = by_id.get(pid)
            name = path_label(p) if p else f"（路径 #{pid} 已不在库中）"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {name}")
            if c2.button("移除", key=f"prof_del_f_{pid}"):
                archive.favorite_path_ids.remove(pid)
                persist_archive()
    else:
        st.caption("暂无重点关注。可在「院校探索」中加入。")

    st.markdown("### 暂不考虑的路径")
    if archive.excluded_path_ids:
        for pid in list(archive.excluded_path_ids):
            p = by_id.get(pid)
            name = path_label(p) if p else f"（路径 #{pid} 已不在库中）"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {name}")
            if c2.button("移除", key=f"prof_del_x_{pid}"):
                archive.excluded_path_ids.remove(pid)
                persist_archive()
    else:
        st.caption("暂无「暂不考虑」的路径。")
    st.caption(
        "标记只表达**你自己的判断**，不会改变证据真实性，也不会自动修改任何评分。"
    )

    st.markdown("### 我对具体路径的判断与理由")
    if archive.path_notes:
        for pid, note in list(archive.path_notes.items()):
            p = by_id.get(int(pid)) if str(pid).isdigit() else None
            name = path_label(p) if p else f"（路径 #{pid}）"
            st.markdown(f"- **{name}**：{note}")
    else:
        st.caption("尚未对任何路径写下你的判断。可在「院校探索」的路径详情中填写。")

    st.markdown("### 权重配置状态")
    profile_rows = _profile_rows(session)
    data_table(profile_rows, hide_index=True, width="stretch")
    st.caption("演示配置 ≠ 你的偏好。确认动作在「动态决策树 → 配置管理」中完成。")

    st.markdown("### 备注")
    note = st.text_area("新增一条备注", key="prof_note", height=80)
    if st.button("保存备注", key="prof_note_save"):
        if note.strip():
            archive.notes.append(note.strip())
            persist_archive()
            st.success("已保存。")
    if archive.notes:
        for i, n in enumerate(archive.notes, 1):
            st.markdown(f"{i}. {n}")
        if st.button("清空备注", key="prof_note_clear"):
            archive.notes = []
            persist_archive()

    st.markdown("### 导出")
    md = _build_markdown(summaries, archive, profile_rows, profile_code=profile_code)
    st.download_button(
        "下载决策档案（Markdown）",
        data=md,
        file_name="我的决策档案.md",
        mime="text/markdown",
        width="stretch",
    )
    with st.expander("预览导出内容", expanded=False):
        st.code(md, language="markdown")

    st.caption(f"上次更新：{archive.updated_at or '（尚未保存）'}")
    render_disclaimer()
