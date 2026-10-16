"""展示格式化：统一「未知」的表达，禁止把缺失渲染成 0 或默认分。"""

from __future__ import annotations

from typing import Any

import streamlit as st

MISSING_TEXT = "暂无数据"
PENDING_TEXT = "待核验"
INSUFFICIENT_TEXT = "证据不足"

# 状态 → (语义色, 语义)
_STATUS_KIND = {
    "已核验": "ok",
    "已核验2028": "ok",
    "2028正式资格已确认": "ok",
    "可比较（非录取预测）": "ok",
    "可输出": "ok",
    "是": "ok",
    "有效": "ok",
    "待核验": "warn",
    "待2028核验": "warn",
    "2028资格未确认": "warn",
    "硬约束待确认-不可比较": "warn",
    "暂无法判断": "warn",
    "待补充证据": "warn",
    "待确认": "warn",
    "未知": "warn",
    "候选": "warn",
    "候选映射": "warn",
    "证据不足": "warn",
    "来源冲突": "error",
    "排除": "error",
    "已失效": "error",
    "硬约束不符-排除": "error",
    "无法核验": "error",
    "未登记": "error",
    "未满足": "error",
    "否": "error",
    "无效": "error",
    # --- Phase 6.0 展示层统一状态 ---
    "已确认": "ok",
    "已评估": "ok",
    "未确认": "warn",
    "部分评估": "warn",
    "待评估": "warn",
    "暂无数据": "warn",
    "不适用": "warn",
    "无法判断": "warn",
    "存在冲突": "error",
}

_KIND_COLOR = {"ok": "green", "warn": "orange", "error": "red", "": "gray"}


def status_kind(text: Any) -> str:
    return _STATUS_KIND.get(str(text), "")


def render_status(text: Any) -> str:
    """以彩色文本渲染状态（Markdown）。未知状态显示为灰色原文。"""
    s = str(text) if text is not None else MISSING_TEXT
    kind = _STATUS_KIND.get(s, "")
    return f":{_KIND_COLOR[kind]}-background[{s}]"


def st_status(text: Any) -> None:
    st.markdown(render_status(text))


def show_value(value: Any, *, missing: str = MISSING_TEXT) -> str:
    """把可能为 None 的值转成展示文本；None 绝不显示为 0。"""
    if value is None:
        return missing
    if isinstance(value, str) and not value.strip():
        return missing
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return missing
    return str(value)


def quota_text(planned: Any, actual: Any) -> str:
    """招生人数展示：没有任何实际数字时显示「暂无数据」，绝不显示 0 人。"""
    if planned is None and actual is None:
        return MISSING_TEXT
    parts = []
    parts.append(f"计划 {planned} 人" if planned is not None else "计划 暂无数据")
    parts.append(f"实际录取 {actual} 人" if actual is not None else "实际录取 暂无数据")
    return " / ".join(parts)


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return MISSING_TEXT
    return f"{value * 100:.{digits}f}%"


def score_text(score: Any) -> str:
    """评分展示：无评分显示「暂无评分」，绝不显示默认分。"""
    if score is None:
        return "暂无评分"
    return str(score)
