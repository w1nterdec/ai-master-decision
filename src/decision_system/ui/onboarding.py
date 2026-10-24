"""User-facing feature inventory and first-run guidance; no decision calculations."""

from __future__ import annotations

import streamlit as st

FEATURES = (
    ("① 决策驾驶舱", "可用", "查看当前状态、优先缺口和关注路径的解释。"),
    ("② 院校探索", "可用", "筛选具体路径，查看来源、历史资料和风险，加入对比。"),
    ("③ 多校对比", "可用", "最多四条路径并列比较；评分取决于有效证据。"),
    ("④ 动态决策树", "可用", "调整相对权重、观察情景、派生和确认自己的偏好。"),
    (
        "⑤ 风险与路径规划",
        "部分可用",
        "缺口与准备事项可用；R7 调剂算法、直接就业评分尚未实现。",
    ),
    ("⑥ 我的决策档案", "可用", "记录个人条件、人工备考分层、关注、理由并导出。"),
    (
        "⑦ 择校结果总览",
        "历史研究意见",
        "查看原案例人工分析；不是针对新用户自动生成的结论。",
    ),
    ("⑧ 研究资料库", "可用", "检索全部底稿映射，按主题筛选并导出、回查原件。"),
    (
        "⚙️ 高级功能",
        "管理入口",
        "五个子页：证据管理、路径查看、模型参数、决策分析、系统状态。",
    ),
)


def navigate(page: str) -> None:
    st.session_state["nav_page"] = page


def render() -> None:
    with st.expander("新手入门与功能状态", expanded=False):
        st.markdown(
            "**第一次使用：看资料 → 记个人条件 → 比路径 → 核验证据 → 看解释与缺口。**"
        )
        st.caption(
            "这是证据化择校决策系统，不会自动抓取高校官网，也不会自动产出冲稳保。人工分层只是你的备考假设。"
        )
        c1, c2 = st.columns(2)
        c1.button(
            "先浏览研究样本",
            on_click=navigate,
            args=("⑧ 研究资料库",),
            key="onboard_research",
            width="stretch",
        )
        c2.button(
            "填写个人条件与备考分层",
            on_click=navigate,
            args=("⑥ 我的决策档案",),
            key="onboard_profile",
            width="stretch",
        )
        for name, status, purpose in FEATURES:
            st.markdown(f"**{name} · {status}**：{purpose}")
        st.markdown(
            "**高级功能状态**：证据登记/关联/人工核验、权重管理、分析和状态查看可用；路径维护目前只读，新增路径通过原始 Excel 导入。评分录入尚无独立网页表单。"
        )
        st.markdown(
            "**术语速查**：证据闸门＝检查来源、年份、路径是否匹配；覆盖率＝有有效证据支持的权重占比，不是录取把握；三级权重＝先大类再细项；情景＝换一种重视程度观察结论；phase＝开发历史标记。"
        )
        st.caption(
            "首次安装：python scripts/start.py --demo。缺少正式数据时可先看研究资料库，不要降低覆盖率门槛来制造评分。"
        )
