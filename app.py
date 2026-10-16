"""Phase 4.1｜2028 AI 硕士动态择校系统 · Streamlit MVP 入口。

启动：
    pip install -e ".[dev]"
    streamlit run app.py

说明：本文件只负责导航与装配，**不含**任何决策算法；
      所有计算由 src/decision_system/engine 与 services 提供。
"""

from __future__ import annotations

import streamlit as st

from decision_system.engine.pipeline import EngineConfig
from decision_system.ui import (
    pages_analysis,
    pages_evidence,
    pages_model,
    pages_overview,
    pages_paths,
)
from decision_system.ui.db_access import db_session, resolve_db_path
from decision_system.ui.decision_view import load_path_rows

DEFAULT_PROFILE = "phase37c_demo"

PAGE_OVERVIEW = "① 项目总览"
PAGE_PATHS = "② 招生路径"
PAGE_EVIDENCE = "③ 证据管理"
PAGE_MODEL = "④ 决策模型"
PAGE_ANALYSIS = "⑤ 决策分析"

PAGES = [PAGE_OVERVIEW, PAGE_PATHS, PAGE_EVIDENCE, PAGE_MODEL, PAGE_ANALYSIS]


def _active_profile() -> str:
    return st.session_state.get("active_profile", DEFAULT_PROFILE)


def _config() -> EngineConfig:
    return EngineConfig(profile_code=_active_profile(), coverage_threshold=0.8)


def render_current_page() -> None:
    page = st.session_state.get("nav_page", PAGE_OVERVIEW)
    with db_session() as session:
        if page == PAGE_EVIDENCE:
            pages_evidence.render(session)
            return
        if page == PAGE_MODEL:
            pages_model.render(session)
            return
        rows = load_path_rows(session, _config(), profile_code=_active_profile())
        if page == PAGE_OVERVIEW:
            pages_overview.render(session, rows)
        elif page == PAGE_PATHS:
            pages_paths.render(session, rows)
        elif page == PAGE_ANALYSIS:
            pages_analysis.render(session, rows, threshold=_config().coverage_threshold)


def main() -> None:
    st.set_page_config(page_title="2028 AI 硕士动态择校系统", page_icon="🎓", layout="wide")
    st.sidebar.title("2028 AI 硕士动态择校系统")
    st.sidebar.caption(f"数据库：{resolve_db_path()}")
    st.sidebar.radio("导航", PAGES, key="nav_page")
    st.sidebar.markdown("---")
    st.sidebar.caption("输出不含录取概率，不构成录取预测或院校排名。")
    st.title("2028 AI 硕士动态择校系统（Phase 4.1 MVP）")
    render_current_page()


main()
