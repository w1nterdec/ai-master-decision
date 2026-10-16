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
    USER_CONFIRMED_BACKGROUND,
    PathSummary,
)


def _profile_rows(session) -> list[dict[str, str]]:
    profiles = session.execute(select(WeightProfile).order_by(WeightProfile.id)).scalars().all()
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

    lines.append("## 一、决策前提（用户已确认，非系统推断）")
    lines.append("")
    for k, v in USER_CONFIRMED_BACKGROUND:
        lines.append(f"- **{k}**：{v}")
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
        "2028 目录未发布，且尚无有效评分，系统不会强行给出排序。"
    )
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

    st.markdown("### 决策前提（用户已确认，非系统推断）")
    for k, v in USER_CONFIRMED_BACKGROUND:
        st.markdown(f"- **{k}**：{v}")

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

    st.markdown("### 关注路径")
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
        st.caption("暂无关注。")

    st.markdown("### 权重配置状态")
    profile_rows = _profile_rows(session)
    st.dataframe(profile_rows, hide_index=True, width="stretch")
    st.caption(
        "演示配置 ≠ 你的偏好。确认动作在「动态决策树 → 配置管理」中完成。"
    )

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
