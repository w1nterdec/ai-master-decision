"""Search, inspect and export all research without turning candidates into verified facts."""

from __future__ import annotations

import math

import streamlit as st

from decision_system.services.research_catalog import ROOT, csv_export
from decision_system.ui.research_blocks import get_catalog, render_record

PAGE_SIZE = 8


def render() -> None:
    st.subheader("研究资料库")
    st.caption("从问题找到资料，从资料回到原件。所有筛选与下载在手机和桌面均可使用。")
    catalog = get_catalog()
    if catalog is None:
        return
    paths = {p["path_id"]: p for p in catalog.paths}
    c1, c2, c3 = st.columns(3)
    c1.metric("研究映射", len(catalog.records))
    c2.metric("招生路径", len(paths))
    c3.metric("研究主题", len(catalog.themes))
    st.info(
        "这是历史研究底稿，含候选映射和跨学院线索；不等于已核验事实，也不确认 2028 资格。来源编号缺少原文链接时，需回到底稿核验。"
    )

    def reset_filters():
        for key, value in {
            "research_query": "",
            "research_schools": [],
            "research_theme": "全部主题",
            "research_grade": "全部层级",
            "research_paths": [],
            "research_page": 1,
        }.items():
            st.session_state[key] = value

    st.button("重置资料筛选", on_click=reset_filters, key="research_reset")
    query = st.text_input(
        "搜索研究资料",
        placeholder="例如：具身  导师、408、统考、华为",
        key="research_query",
    )
    c1, c2 = st.columns(2)
    schools = c1.multiselect(
        "学校筛选",
        sorted({p["school"] for p in paths.values()}),
        key="research_schools",
    )
    themes = c2.selectbox(
        "主题筛选", ["全部主题", *catalog.themes], key="research_theme"
    )
    c1, c2 = st.columns(2)
    grade = c1.selectbox(
        "来源层级", ["全部层级", "S1", "S2", "S3", "S4"], key="research_grade"
    )
    available = [
        pid for pid, p in paths.items() if not schools or p["school"] in schools
    ]
    if "research_paths" in st.session_state:
        st.session_state["research_paths"] = [
            pid for pid in st.session_state["research_paths"] if pid in available
        ]
    selected_paths = c2.multiselect(
        "路径筛选",
        available,
        format_func=lambda pid: (
            f"{pid} · {paths[pid]['school']} · {paths[pid]['college']} · {paths[pid].get('direction') or paths[pid]['program']}"
        ),
        key="research_paths",
    )
    records = catalog.search(
        query=query,
        path_ids=selected_paths or available,
        theme=None if themes == "全部主题" else themes,
        grade=None if grade == "全部层级" else grade,
    )
    st.markdown(f"### 找到 {len(records)} 条研究资料")
    st.download_button(
        "下载筛选结果 CSV",
        csv_export(records),
        file_name="research-selection.csv",
        mime="text/csv",
        disabled=not records,
        key="research_download",
    )
    if not records:
        st.info("没有匹配资料。可减少搜索词或放宽学校、主题和层级筛选。")
    else:
        count = math.ceil(len(records) / PAGE_SIZE)
        signature = (query, tuple(schools), themes, grade, tuple(selected_paths))
        if st.session_state.get("_research_filter") != signature:
            st.session_state["research_page"] = 1
            st.session_state["_research_filter"] = signature
        page = st.selectbox(
            "资料页码",
            list(range(1, count + 1)),
            key="research_page",
            format_func=lambda value: f"第 {value} / {count} 页",
        )
        for record in records[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]:
            p = paths[record["path_id"]]
            with st.container(border=True):
                st.caption(
                    f"{record['path_id']} / {p['school']} / {p['college']} / {record.get('theme') or '未分类'}"
                )
                render_record(record)
    with st.expander("数据版本与研究原件"):
        st.write(catalog.data.get("source_year_note", "年份未注明"))
        st.caption(f"数据指纹 SHA-256：{catalog.digest}")
        st.caption(
            "资料为本地快照，不会自动联网更新。更新原件后运行初始化命令重新生成；核验仍需人工确认。"
        )
        st.link_button("研招网 · 硕士专业目录", "https://yz.chsi.com.cn/zsml/")
        st.link_button(
            "研招网 · 招生信息公开",
            "https://yzst.chsi.com.cn/zsgs/zsjz/queryall.action",
        )
        source = (ROOT / catalog.data.get("source_file", "")).resolve()
        raw_dir = (ROOT / "data" / "raw").resolve()
        if source.is_relative_to(raw_dir) and source.is_file():
            st.download_button(
                "下载完整研究底稿 Excel",
                source.read_bytes(),
                file_name=source.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="research_workbook",
            )
