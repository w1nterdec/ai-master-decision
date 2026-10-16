"""页面四｜动态决策树（权重结构 + 情景切换）。

职责：把「我到底在看重什么」显式化、可调整、可留痕。
纪律：
    * 权重读写全部走 `weight_service` / `profile_service`（写库 + 审计），**不在页面里算**；
    * 演示配置一律标注「演示配置，未经用户确认」，**不得**冒充用户偏好；
    * 只改权重，不改指标树结构与数据库表结构；
    * 页面名「决策树」= 展示指标树与权重，**不做决策判定**。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from decision_system.models.entities import Indicator, WeightProfile
from decision_system.services.decision_service import build_weight_tree, load_scenarios
from decision_system.services import profile_service, weight_service
from decision_system.engine.scenarios import scenario_weights
from decision_system.ui.formatting import render_status
from decision_system.ui.viewmodels import V4_DIMENSION_MAP, v4_label, v4_order

SLIDER_MAX = 100.0


def _profile_state(session, profile_code: str) -> WeightProfile | None:
    return session.execute(
        select(WeightProfile).where(WeightProfile.code == profile_code)
    ).scalar_one_or_none()


def _tree_table(session, profile_code: str) -> pd.DataFrame:
    tree = build_weight_tree(session, profile_code)
    rows = []
    for l1 in v4_order(sorted(tree.codes(1))):
        rows.append(
            {
                "层级": "一级",
                "V4.0 维度": v4_label(l1),
                "指标": tree.node(l1).name,
                "组内权重": round(tree.node(l1).raw_weight, 2),
                "组内占比": round(tree.group_normalized(l1) * 100, 2),
                "全局权重(%)": round(tree.global_weight(l1) * 100, 2),
                "code": l1,
            }
        )
        for l2 in tree.children(l1):
            rows.append(
                {
                    "层级": "二级",
                    "V4.0 维度": v4_label(l1),
                    "指标": f"　└ {tree.node(l2).name}",
                    "组内权重": round(tree.node(l2).raw_weight, 2),
                    "组内占比": round(tree.group_normalized(l2) * 100, 2),
                    "全局权重(%)": round(tree.global_weight(l2) * 100, 2),
                    "code": l2,
                }
            )
            for l3 in tree.children(l2):
                rows.append(
                    {
                        "层级": "三级",
                        "V4.0 维度": v4_label(l1),
                        "指标": f"　　　└ {tree.node(l3).name}",
                        "组内权重": round(tree.node(l3).raw_weight, 2),
                        "组内占比": round(tree.group_normalized(l3) * 100, 2),
                        "全局权重(%)": round(tree.global_weight(l3) * 100, 2),
                        "code": l3,
                    }
                )
    return pd.DataFrame(rows)


def _render_adjust(session, profile_code: str, profile: WeightProfile) -> None:
    st.markdown("### 调整权重")
    st.caption(
        "修改的是**组内相对权重**；全局权重由引擎自动重算。"
        "每次修改都会写入审计日志并保留修改前后数值。"
    )
    tree = build_weight_tree(session, profile_code)
    leaves = sorted(tree.codes(3))
    names = {c: f"{tree.node(c).name}（{c}）" for c in leaves}
    code = st.selectbox(
        "选择三级指标",
        leaves,
        format_func=lambda c: names[c],
        key="tree_indicator",
    )
    current = float(tree.node(code).raw_weight)
    new_raw = st.slider(
        "组内相对权重",
        min_value=0.0,
        max_value=SLIDER_MAX,
        value=current,
        step=1.0,
        key="tree_slider",
    )
    if abs(new_raw - current) > 1e-9:
        try:
            preview = tree.with_updated_weight(code, float(new_raw))
        except Exception as exc:  # 负权重等非法值
            st.error(f"预览失败：{exc}")
            return
        before = tree.global_weights().get(code, 0.0)
        after = preview.global_weights().get(code, 0.0)
        c1, c2 = st.columns(2)
        c1.metric("全局权重（当前）", f"{before * 100:.2f}%")
        c2.metric("全局权重（调整后）", f"{after * 100:.2f}%", f"{(after - before) * 100:+.2f} pct")
        st.caption("以上为**未落库预览**；点击下方按钮才会写入。")

        reason = st.text_input("修改理由（写入审计日志，可留空）", key="tree_reason")
        if st.button("应用修改（写入数据库并记录审计）", key="tree_apply"):
            try:
                weight_service.update_weight(
                    session,
                    profile_code=profile_code,
                    indicator_code=code,
                    new_raw_weight=float(new_raw),
                    actor="user",
                    reason=reason or None,
                )
            except Exception as exc:
                st.error(f"修改失败：{exc}")
            else:
                st.success("已写入数据库并记录审计。")
                if profile.is_demo:
                    st.warning(
                        "注意：被修改的是**演示配置**，`is_demo` 仍为 True，"
                        "不会自动变成你的正式偏好。请在下方「配置管理」中派生并确认。"
                    )
    else:
        st.caption("拖动滑块后可预览全局权重变化。")


def _render_scenarios(session, profile_code: str) -> None:
    st.markdown("### 情景切换")
    scenarios = load_scenarios(session)
    if not scenarios:
        st.info("暂无情景配置。")
        return
    tree = build_weight_tree(session, profile_code)
    codes = sorted(scenarios.keys())
    code = st.radio(
        "情景",
        codes,
        format_func=lambda c: f"{scenarios[c].name}（{c}）",
        horizontal=True,
        key="tree_scenario",
    )
    sc = scenarios[code]
    if sc.is_demo:
        st.warning("情景倍率为**演示配置**（未经用户确认），仅用于观察权重敏感性。")
    if sc.description:
        st.caption(sc.description)
    base = tree.global_weights()
    applied = scenario_weights(tree, sc)
    rows = []
    for c in sorted(base.keys()):
        rows.append(
            {
                "指标": tree.node(c).name,
                "基础全局权重(%)": round(base[c] * 100, 2),
                f"{sc.name} 权重(%)": round(applied.get(c, 0.0) * 100, 2),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("情景只改变权重分布，**不改变**任何证据事实与 2028 资格判定。")


def _render_profile_admin(session, profile_code: str) -> None:
    st.markdown("### 配置管理")
    profiles = profile_service.list_profiles(session)
    rows = [
        {
            "配置代码": p.code,
            "名称": p.name,
            "性质": "用户确认" if not p.is_demo else "演示配置（待确认）",
        }
        for p in profiles
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with st.expander("从当前配置派生一个用户版本", expanded=False):
        new_code = st.text_input("新配置代码", value="my_preference_v1", key="tree_new_code")
        new_name = st.text_input("新配置名称", value="我的偏好（待确认）", key="tree_new_name")
        if st.button("派生", key="tree_clone"):
            try:
                profile_service.clone_profile(
                    session,
                    base_code=profile_code,
                    new_code=new_code,
                    name=new_name,
                    actor="user",
                )
            except Exception as exc:
                st.error(f"派生失败：{exc}")
            else:
                st.success(f"已派生 `{new_code}`（仍需在下方确认为正式偏好）。")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("把当前配置恢复为演示基准值", key="tree_restore"):
            try:
                n = profile_service.restore_from_base(
                    session, profile_code, base_code="phase37c_demo", actor="user"
                )
            except Exception as exc:
                st.error(f"恢复失败：{exc}")
            else:
                st.success(f"已恢复 {n} 个节点（审计日志保留）。")
    with c2:
        if st.button("确认当前配置为我的正式偏好", key="tree_confirm"):
            try:
                profile_service.confirm_as_user_preference(
                    session, profile_code, actor="user", note="用户在决策树页面确认"
                )
            except Exception as exc:
                st.error(f"确认失败：{exc}")
            else:
                st.success(f"`{profile_code}` 已标记为用户正式偏好（权重数值不变）。")

    st.markdown("### 权重修改记录")
    history = weight_service.weight_change_history(session, profile_code)
    if not history:
        st.caption("暂无权重修改记录。")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "时间": h.get("at"),
                        "操作者": h.get("actor"),
                        "指标": h.get("indicator_code"),
                        "原值": h.get("old_raw_weight"),
                        "新值": h.get("new_raw_weight"),
                        "理由": h.get("reason") or "",
                        "仍为演示配置": h.get("still_demo_config"),
                    }
                    for h in history
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def render(session, rows, *, profile_code: str) -> None:
    st.subheader("动态决策树")
    profile = _profile_state(session, profile_code)
    if profile is None:
        st.error(f"权重配置不存在：{profile_code}")
        return

    if profile.is_demo:
        st.warning(
            f"当前配置 `{profile_code}` 为**演示配置（is_demo=True）**，"
            "代表一种示例权重结构，**不是**你的正式偏好。"
            "在确认之前，任何基于它的输出都只能作为演示。"
        )
    else:
        st.success(f"当前配置 `{profile_code}` 已标记为用户正式偏好。")

    st.caption(
        "维度顺序按千问 V4.0 五维排列；库内指标 code / 名称 / 层级**未做任何改动**。"
    )

    st.markdown("### 指标树与当前权重")
    df = _tree_table(session, profile_code)
    st.dataframe(df.drop(columns=["code"]), hide_index=True, width="stretch")
    with st.expander("指标 code 对照（用于内部核对）", expanded=False):
        st.dataframe(df[["层级", "指标", "code"]], hide_index=True, width="stretch")

    st.markdown("---")
    _render_adjust(session, profile_code, profile)
    st.markdown("---")
    _render_scenarios(session, profile_code)
    st.markdown("---")
    _render_profile_admin(session, profile_code)
    st.caption(
        "调整权重只改变**你看重什么**，不会凭空产生证据；"
        "证据不足时，任何权重配置下结果仍然是「无法判断」。"
    )
