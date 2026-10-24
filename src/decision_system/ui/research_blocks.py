"""Research evidence shared by discovery, comparison, and the research workbench."""

from __future__ import annotations

import streamlit as st

from decision_system.services.research_catalog import (
    CatalogError,
    csv_export,
    load_catalog,
)

GRADE_LABELS = {
    "S1": "官方/目录级",
    "S2": "学院级",
    "S3": "实验室/研究院级",
    "S4": "全校级线索",
}


def get_catalog():
    try:
        return load_catalog()
    except CatalogError as exc:
        st.error(str(exc))
        return None


def render_record(record: dict) -> None:
    st.markdown(f"**{record.get('indicator') or record.get('theme') or '研究资料'}**")
    st.write(record["statement"])
    grade = record.get("grade") or "未分级"
    st.caption(
        f"{grade} · {GRADE_LABELS.get(grade, '未分级')} ｜ 原始状态：{record.get('verify_status') or '待核验'}"
    )
    st.caption(
        f"来源编号：{record.get('source_id') or '未登记'} ｜ 底稿：{record.get('source_sheet') or '3_2证据映射候选'} · 第 {record.get('source_row') or '未知'} 行"
    )
    if record.get("match_limit"):
        st.caption("适用限制：" + record["match_limit"])


def render_path_research(legacy_id: str | None, *, key: str) -> None:
    catalog = get_catalog()
    if catalog is None:
        return
    records = catalog.for_path(legacy_id)
    with st.expander(f"历史研究资料 · {len(records)} 条（按主题查看）", expanded=False):
        st.caption(
            "研究线索不参与正式评分；来源等级不等于已核验状态。保留原文、来源编号与匹配限制。"
        )
        if not records:
            st.info("该路径尚未关联研究材料。")
            return
        themes = sorted({r.get("theme") or "未分类" for r in records})
        theme = st.selectbox("研究主题", themes, key=f"{key}_theme")
        selected = [r for r in records if (r.get("theme") or "未分类") == theme]
        for record in selected:
            render_record(record)
            st.divider()
        st.download_button(
            "导出这条路径的全部研究资料",
            csv_export(records),
            file_name=f"research-{legacy_id}.csv",
            mime="text/csv",
            key=f"{key}_csv",
        )
