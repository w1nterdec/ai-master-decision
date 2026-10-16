"""Phase 6.0｜2028 AI 硕士动态择校决策助手 · Streamlit 入口。

启动：
    pip install -e ".[dev]"
    streamlit run app.py

说明：本文件只负责导航与装配，**不含**任何决策算法；
      所有计算由 src/decision_system/engine 与 services 提供。
      Phase 4.1 的全部页面保留在「高级功能」中，未删除。
"""

from __future__ import annotations

import streamlit as st

from decision_system.engine.pipeline import EngineConfig
from decision_system.ui import (
    pages_analysis,
    pages_compare,
    pages_cockpit,
    pages_evidence,
    pages_explore,
    pages_model,
    pages_overview,
    pages_paths,
    pages_profile,
    pages_result,
    pages_risk,
    pages_tree,
)
from decision_system.ui.db_access import db_session, resolve_db_path
from decision_system.ui.decision_view import load_path_rows

DEFAULT_PROFILE = "phase37c_demo"

# --- 六个主页面（决策主线） -------------------------------------------------
PAGE_COCKPIT = "① 决策驾驶舱"
PAGE_EXPLORE = "② 院校探索"
PAGE_COMPARE = "③ 多校对比"
PAGE_TREE = "④ 动态决策树"
PAGE_RISK = "⑤ 风险与路径规划"
PAGE_PROFILE = "⑥ 我的决策档案"
PAGE_RESULT = "⑦ 择校结果总览"

# --- 高级功能（Phase 4.1 原页面，全部保留） ---------------------------------
PAGE_ADVANCED = "⚙️ 高级功能"
ADV_EVIDENCE = "证据管理"
ADV_PATHS = "数据维护 · 招生路径"
ADV_MODEL = "模型参数"
ADV_ANALYSIS = "决策分析"
ADV_OVERVIEW = "系统状态"

MAIN_PAGES = [
    PAGE_COCKPIT,
    PAGE_EXPLORE,
    PAGE_COMPARE,
    PAGE_TREE,
    PAGE_RISK,
    PAGE_PROFILE,
    PAGE_RESULT,
    PAGE_ADVANCED,
]
ADV_PAGES = [ADV_EVIDENCE, ADV_PATHS, ADV_MODEL, ADV_ANALYSIS, ADV_OVERVIEW]


def _active_profile() -> str:
    return st.session_state.get("active_profile", DEFAULT_PROFILE)


def _config() -> EngineConfig:
    return EngineConfig(profile_code=_active_profile(), coverage_threshold=0.8)


def render_current_page() -> None:
    page = st.session_state.get("nav_page", PAGE_COCKPIT)
    profile = _active_profile()
    threshold = _config().coverage_threshold

    if page == PAGE_RESULT:
        # 择校结果总览：只读整合 JSON，不依赖数据库会话
        pages_result.render(profile_code=profile)
        return

    with db_session() as session:
        if page == PAGE_TREE:
            pages_tree.render(session, (), profile_code=profile)
            return
        if page == PAGE_ADVANCED:
            _render_advanced(session, threshold)
            return

        rows = load_path_rows(session, _config(), profile_code=profile)
        if page == PAGE_COCKPIT:
            pages_cockpit.render(session, rows, profile_code=profile, threshold=threshold)
        elif page == PAGE_EXPLORE:
            pages_explore.render(
                session, rows, threshold=threshold, profile_code=profile
            )
        elif page == PAGE_COMPARE:
            pages_compare.render(
                session, rows, threshold=threshold, profile_code=profile
            )
        elif page == PAGE_RISK:
            pages_risk.render(
                session, rows, threshold=threshold, profile_code=profile
            )
        elif page == PAGE_PROFILE:
            pages_profile.render(session, rows, profile_code=profile)
        else:  # pragma: no cover - 兜底
            pages_cockpit.render(session, rows, profile_code=profile, threshold=threshold)


def _render_advanced(session, threshold: float) -> None:
    sub = st.session_state.get("adv_page", ADV_EVIDENCE)
    st.caption("以下为 Phase 4.1 原始数据维护与模型管理页面，供核对与维护使用。")
    if sub == ADV_EVIDENCE:
        pages_evidence.render(session)
        return
    if sub == ADV_MODEL:
        pages_model.render(session)
        return
    rows = load_path_rows(session, _config(), profile_code=_active_profile())
    if sub == ADV_PATHS:
        pages_paths.render(session, rows)
    elif sub == ADV_ANALYSIS:
        pages_analysis.render(session, rows, threshold=threshold)
    elif sub == ADV_OVERVIEW:
        pages_overview.render(session, rows)


def main() -> None:
    st.set_page_config(
        page_title="2028 AI 硕士动态择校决策助手",
        page_icon="🎓",
        layout="wide",
    )
    st.sidebar.title("2028 AI 硕士动态择校")
    st.sidebar.caption(f"数据库：{resolve_db_path()}")
    st.sidebar.radio("决策主线", MAIN_PAGES, key="nav_page")
    if st.session_state.get("nav_page") == PAGE_ADVANCED:
        st.sidebar.radio("高级功能", ADV_PAGES, key="adv_page")
    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"权重配置：`{_active_profile()}`（默认演示配置，待确认）\n\n"
        "输出不含录取概率，不构成录取预测或院校排名。"
    )

    st.title("2028 AI 硕士动态择校决策助手")
    st.caption(
        "面向「只有一次考研机会」的 2028 年 AI 相关全日制硕士择校："
        "先看证据，再看偏好，最后才谈比较。"
    )
    render_current_page()
    st.markdown("---")
    st.caption(
        "历史研究信息 ≠ 2028 正式决策依据；未知值一律显示为"
        "「暂无数据 / 待核验 / 证据不足 / 无法判断」，绝不补 0。"
    )


main()
