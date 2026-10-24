"""【决策模型】三级动态权重（Task D）。

所有计算调用 Phase 4.0 的 WeightTree / weight_service / profile_service，
本页不实现任何权重算法。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from decision_system.ui.theme import data_table

from decision_system.engine.weights import WeightTree
from decision_system.services.decision_service import build_weight_tree
from decision_system.services.profile_service import (
    ProfileServiceError,
    apply_weight_change,
    clone_profile,
    confirm_as_user_preference,
    list_profiles,
    restore_from_base,
)
from decision_system.services.weight_service import weight_change_history

DEMO_PROFILE = "phase37c_demo"


def render(session) -> None:
    st.subheader("决策模型 · 三级动态权重")
    profiles = list_profiles(session)
    if not profiles:
        st.info("数据库中暂无权重配置。")
        return

    codes = [p.code for p in profiles]
    if DEMO_PROFILE not in codes:
        st.error(f"缺少演示配置 {DEMO_PROFILE}，页面无法工作。")
        return

    active = st.selectbox(
        "当前权重配置",
        codes,
        index=codes.index(st.session_state.get("active_profile", DEMO_PROFILE))
        if st.session_state.get("active_profile", DEMO_PROFILE) in codes
        else 0,
        format_func=lambda c: f"{c}（{'演示配置' if next((p.is_demo for p in profiles if p.code == c), True) else '用户配置'}）",
    )
    st.session_state["active_profile"] = active
    is_demo = bool(next((p.is_demo for p in profiles if p.code == active), True))

    if is_demo:
        st.warning("当前为**演示权重**，尚未确认为用户正式偏好。")
    else:
        st.info("当前为用户配置版本（仍建议在有充分证据后再用于正式比较）。")

    col_new, col_confirm, col_restore = st.columns(3)
    with col_new:
        new_code = st.text_input("派生新配置代码", value="user_profile_v1")
        if st.button("从演示配置派生用户配置", key="btn_clone_profile"):
            try:
                clone_profile(
                    session,
                    base_code=DEMO_PROFILE,
                    new_code=new_code.strip(),
                    name=f"用户配置 {new_code.strip()}",
                    actor="user",
                )
                st.success(f"已创建配置 `{new_code.strip()}`，演示配置未被修改。")
                st.session_state["active_profile"] = new_code.strip()
            except ProfileServiceError as exc:
                st.error(f"创建失败：{exc}")
    with col_confirm:
        if not is_demo:
            if st.button("标记为我的正式偏好", key="btn_confirm_profile"):
                confirm_as_user_preference(session, active, actor="user", note="用户在界面确认")
                st.success(f"配置 `{active}` 已标记为正式偏好（权重数值未变）。")
        else:
            st.caption("演示配置不能直接标记为正式偏好，请先派生用户配置。")
    with col_restore:
        if st.button("恢复为演示配置数值", key="btn_restore_profile"):
            n = restore_from_base(session, active, base_code=DEMO_PROFILE, actor="user")
            st.warning(f"已恢复 {n} 个节点的数值（历史修改记录保留，未被删除）。")

    tree = build_weight_tree(session, active)
    _render_tree(session, tree, active)

    st.markdown("---")
    st.markdown("#### 权重修改记录")
    hist = weight_change_history(session, active)
    if not hist:
        st.info("该配置尚无修改记录。")
    else:
        df = pd.DataFrame(
            [
                {
                    "时间": h.get("at"),
                    "操作者": h.get("actor"),
                    "指标": h.get("indicator_code") or h.get("entity"),
                    "修改前": h.get("old_raw_weight"),
                    "修改后": h.get("new_raw_weight"),
                    "全局权重前": h.get("global_weight_before"),
                    "全局权重后": h.get("global_weight_after"),
                    "理由": h.get("reason"),
                }
                for h in hist
            ]
        )
        data_table(df, hide_index=True, width="stretch")


def _render_tree(session, tree: WeightTree, profile_code: str) -> None:
    st.markdown("#### 指标树（一级 → 二级 → 三级）")
    st.caption(
        "「组内权重」= 同级归一化后的相对权重；「全局权重」= 沿父链相乘后的最终权重。"
        "三级全局权重合计 = "
        f"{tree.total_global_weight():.6f}"
    )
    for l1 in _sorted_codes(tree, 1):
        n1 = tree.node(l1)
        with st.expander(
            f"【一级】{n1.name}　组内 {tree.group_normalized(l1):.2%}　全局 {tree.global_weight(l1):.2%}",
            expanded=True,
        ):
            _weight_editor(session, tree, l1, profile_code, level=1)
            for l2 in _sorted_codes(tree, 2, parent=l1):
                n2 = tree.node(l2)
                st.markdown(
                    f"&nbsp;&nbsp;**【二级】{n2.name}**　组内 {tree.group_normalized(l2):.2%}　全局 {tree.global_weight(l2):.2%}"
                )
                _weight_editor(session, tree, l2, profile_code, level=2, indent=True)
                for l3 in _sorted_codes(tree, 3, parent=l2):
                    n3 = tree.node(l3)
                    st.markdown(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;· 【三级】{n3.name}　组内 {tree.group_normalized(l3):.2%}　**全局 {tree.global_weight(l3):.4%}**"
                    )
                    _weight_editor(session, tree, l3, profile_code, level=3, indent=True)


def _sorted_codes(tree: WeightTree, level: int, parent: str | None = None) -> list[str]:
    codes = tree.children(parent) if parent is not None else tree.codes(level)
    return sorted(codes, key=lambda c: (tree.node(c).sort_order, c))


def _weight_editor(
    session, tree: WeightTree, code: str, profile_code: str, *, level: int, indent: bool = False
) -> None:
    node = tree.node(code)
    key_w = f"w::{profile_code}::{code}"
    current = float(node.raw_weight)
    col1, col2, col3 = st.columns([1.2, 1.2, 2.4])
    with col1:
        new_val = st.number_input(
            f"{'　' * (level - 1)}原始权重 · {code}",
            min_value=0.0,
            value=current,
            step=1.0,
            key=key_w,
        )
    with col2:
        st.caption("组内归一化（当前）")
        st.markdown(f"**{tree.group_normalized(code):.2%}**")
    with col3:
        if abs(float(new_val) - current) > 1e-9:
            try:
                preview = tree.with_updated_weight(code, float(new_val))
                st.caption("调整后预览（未保存）")
                st.markdown(
                    f"组内 {preview.group_normalized(code):.2%}　全局 {preview.global_weight(code):.4%}"
                )
            except Exception as exc:  # 负权重等
                st.error(str(exc))
        else:
            st.caption("调整数值后可预览变化")

    if abs(float(new_val) - current) > 1e-9:
        actor = st.text_input(
            f"{'　' * (level - 1)}操作者（保存 {code}）",
            value="user",
            key=f"actor::{profile_code}::{code}",
        )
        if st.button(f"{'　' * (level - 1)}保存 {node.name}", key=f"save::{profile_code}::{code}"):
            try:
                apply_weight_change(
                    session,
                    profile_code=profile_code,
                    indicator_code=code,
                    new_raw_weight=float(new_val),
                    actor=actor or "user",
                    reason="界面调整",
                )
                st.success(f"已保存 {node.name}：{current} → {new_val}（已写审计日志）")
                # Phase 6.1｜M8：此处原本调用 st 的 rerun 接口，它会抛出 RerunException
                # 并被 db_session() 的 except 分支捕获执行 rollback，
                # 导致「提示已保存但改动被静默回滚」。改为依赖按钮点击自身的重跑。
            except Exception as exc:
                st.error(f"保存失败：{exc}")
