"""【证据管理】工作台（Task C，本阶段最高优先级）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from decision_system.ui.theme import data_table
from sqlalchemy import select

from decision_system.evidence.registry import EvidenceGovernanceError
from decision_system.models.entities import (
    AdmissionPath,
    EvidenceClaim,
    EvidenceSource,
    Indicator,
)
from decision_system.models.enums import (
    ClaimStatus,
    SourceType,
    VerificationStatus,
)
from decision_system.services.evidence_service import (
    approve_claim,
    attach_claim_by_codes,
    create_claim,
    evidence_gap_stats,
    is_registered_source,
    is_placeholder_record,
    list_sources,
    mark_conflict,
    mark_source_unverifiable,
    register_source_strict,
    reject_claim,
    submit_for_verification,
    verification_history,
    verify_source,
)
from decision_system.ui.formatting import render_status, show_value

TAB_REGISTER, TAB_LINK, TAB_VERIFY, TAB_GAP = "① 来源登记", "② 证据关联", "③ 人工核验", "④ 缺口统计"


def render(session) -> None:
    st.subheader("证据管理")
    st.caption(
        "所有写操作均经 `services/evidence_service.py`，页面不直接修改 ORM 字段；"
        "候选证据映射不会自动升级为已核验证据。"
    )
    tabs = st.tabs([TAB_REGISTER, TAB_LINK, TAB_VERIFY, TAB_GAP])
    with tabs[0]:
        _render_register(session)
    with tabs[1]:
        _render_link(session)
    with tabs[2]:
        _render_verify(session)
    with tabs[3]:
        _render_gap(session)


# ---------------------------------------------------------------------------
def _render_register(session) -> None:
    st.markdown("#### 登记新来源")
    st.caption("登记后的来源状态为「待核验」。若要标记为已核验，必须在下方填写操作者与核验依据。")

    with st.form("register_source_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        source_id = c1.text_input("source_id（唯一，必填）")
        title = c2.text_input("来源标题（必填）")
        c3, c4 = st.columns(2)
        publisher = c3.text_input("发布机构")
        url_or_file = c4.text_input("官方 URL 或文件标识（登记真实来源必填其一）")
        c5, c6, c7 = st.columns(3)
        published_year = c5.number_input("发布年份", min_value=1990, max_value=2035, value=2025, step=1)
        source_type = c6.selectbox("来源类型", [s.value for s in SourceType])
        applicable = c7.multiselect("适用招生年份", [2026, 2027, 2028], default=[2028])
        note = st.text_input("备注（可选）")
        submitted = st.form_submit_button("登记来源")

    if submitted:
        try:
            src = register_source_strict(
                session,
                source_id=source_id,
                title=title,
                publisher=publisher or None,
                url_or_file=url_or_file or None,
                source_type=SourceType(source_type),
                published_year=int(published_year),
                applicable_years=sorted(applicable),
                verification_status=VerificationStatus.PENDING,
                verification_note=note or None,
                is_placeholder=False,
                actor="user",
            )
            st.success(f"已登记来源 `{src.source_id}`（状态：{src.verification_status}，尚未核验）")
        except EvidenceGovernanceError as exc:
            st.error(f"登记失败：{exc}")

    st.markdown("---")
    st.markdown("#### 已登记来源核验 / 失效")
    sources = list_sources(session)
    registered = [s for s in sources if is_registered_source(s)]
    if not registered:
        st.info("当前没有已登记本体的来源，无法执行来源核验。")
    else:
        sid = st.selectbox(
            "选择来源", [s.source_id for s in registered], format_func=lambda x: f"{x}"
        )
        actor = st.text_input("操作者", value="user", key="src_actor")
        basis = st.text_input("核验依据（必填）", key="src_basis")
        c1, c2 = st.columns(2)
        if c1.button("核验通过", key="btn_source_verify"):
            try:
                s = verify_source(session, sid, actor=actor, basis=basis)
                st.success(f"来源 `{sid}` 已核验：{s.verification_status}")
            except EvidenceGovernanceError as exc:
                st.error(f"操作被拒绝：{exc}")
        if c2.button("标记无法核验", key="btn_source_unverifiable"):
            try:
                s = mark_source_unverifiable(session, sid, actor=actor, note=basis)
                st.warning(f"来源 `{sid}` 已标记为：{s.verification_status}")
            except EvidenceGovernanceError as exc:
                st.error(f"操作被拒绝：{exc}")

    st.markdown("---")
    st.markdown("#### 来源清单")
    only_unreg = st.checkbox("只看未登记本体的来源", value=True)
    kw = st.text_input("关键字过滤（source_id / 标题）")
    rows = list_sources(session, only_unregistered=only_unreg, keyword=kw or None)
    st.caption(f"共 {len(rows)} 条")
    if rows:
        df = pd.DataFrame(
            [
                {
                    "source_id": s.source_id,
                    "标题": s.title,
                    "发布机构": show_value(s.publisher),
                    "URL/文件": show_value(s.url_or_file),
                    "类型": str(s.source_type),
                    "适用年份": show_value(",".join(str(y) for y in (s.applicable_years or []))),
                    "核验状态": str(s.verification_status),
                    "本体登记": "已登记" if is_registered_source(s) else ("占位符" if is_placeholder_record(s) else "未登记"),
                }
                for s in rows[:200]
            ]
        )
        data_table(df, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
def _render_link(session) -> None:
    st.markdown("#### 登记事实声明并关联")
    sources = list_sources(session)
    if not sources:
        st.info("暂无来源，请先登记来源。")
        return
    with st.form("claim_form", clear_on_submit=True):
        source_id = st.selectbox("所属来源", [s.source_id for s in sources])
        statement = st.text_area("事实声明内容（必填）")
        topic = st.text_input("主题（可选）")
        years = st.multiselect("适用招生年份", [2026, 2027, 2028], default=[2028])
        submitted = st.form_submit_button("登记声明")
    if submitted:
        try:
            claim = create_claim(
                session,
                source_id=source_id,
                statement=statement,
                topic=topic or None,
                applicable_years=sorted(years),
                actor="user",
            )
            st.success(f"已登记声明 #{claim.id}（状态：{claim.status}，候选映射）")
        except EvidenceGovernanceError as exc:
            st.error(f"登记失败：{exc}")

    st.markdown("---")
    st.markdown("#### 关联到路径 / 指标")
    claims = session.execute(select(EvidenceClaim).order_by(EvidenceClaim.id)).scalars().all()
    if not claims:
        st.info("暂无事实声明。")
        return
    claim_id = st.selectbox(
        "选择声明",
        [c.id for c in claims],
        format_func=lambda i: f"#{i} ｜{next((c.source_ref_id for c in claims if c.id == i), '')} ｜{next((c.statement[:40] for c in claims if c.id == i), '')}",
    )
    paths = session.execute(select(AdmissionPath).order_by(AdmissionPath.id)).scalars().all()
    indicators = session.execute(
        select(Indicator).where(Indicator.level == 3).order_by(Indicator.sort_order)
    ).scalars().all()
    c1, c2 = st.columns(2)
    path_key = c1.selectbox("关联招生路径（可不选）", ["（不关联）"] + [p.path_key for p in paths])
    ind_code = c2.selectbox(
        "关联三级指标（可不选）",
        ["（不关联）"] + [i.code for i in indicators],
        format_func=lambda x: x,
    )
    if st.button("执行关联", key="btn_link_claim"):
        try:
            done = attach_claim_by_codes(
                session,
                int(claim_id),
                path_key=None if path_key == "（不关联）" else path_key,
                indicator_code=None if ind_code == "（不关联）" else ind_code,
                actor="user",
            )
            st.success(f"关联完成：{'、'.join(done) if done else '未选择目标'}")
        except EvidenceGovernanceError as exc:
            st.error(f"关联失败：{exc}")


# ---------------------------------------------------------------------------
def _render_verify(session) -> None:
    st.markdown("#### 人工核验")
    st.caption("核验通过必须记录操作者、核验时间与核验依据；候选映射不会自动升级。")
    claims = session.execute(select(EvidenceClaim).order_by(EvidenceClaim.id)).scalars().all()
    if not claims:
        st.info("暂无事实声明。")
        return
    status_filter = st.multiselect(
        "按状态过滤",
        [s.value for s in ClaimStatus],
        default=[ClaimStatus.CANDIDATE.value, ClaimStatus.PENDING.value],
    )
    visible = [c for c in claims if str(c.status) in status_filter]
    st.caption(f"共 {len(visible)} 条")
    if not visible:
        return
    claim_id = st.selectbox(
        "选择声明",
        [c.id for c in visible],
        format_func=lambda i: f"#{i} ｜{next((c.source_ref_id for c in visible if c.id == i), '')} ｜状态 {next((str(c.status) for c in visible if c.id == i), '')}",
    )
    cur = session.get(EvidenceClaim, int(claim_id))
    if cur is not None:
        st.markdown(f"当前状态：{render_status(cur.status)}（候选映射：{'是' if cur.is_candidate else '否'}）")
        st.caption(show_value(cur.statement, missing="（声明内容为空）"))

    actor = st.text_input("操作者（必填）", value="user", key="verify_actor")
    basis = st.text_input("核验依据 / 理由（通过、驳回、冲突均必填）", key="verify_basis")
    years = st.multiselect("适用招生年份（核验通过时可指定）", [2026, 2027, 2028], default=[2028])

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("提交核验", key="btn_claim_submit"):
        try:
            c = submit_for_verification(session, int(claim_id), actor=actor, note=basis or None)
            st.info(f"已提交核验，状态：{c.status}")
        except EvidenceGovernanceError as exc:
            st.error(f"操作被拒绝：{exc}")
    if c2.button("核验通过", key="btn_claim_approve"):
        try:
            c = approve_claim(
                session, int(claim_id), actor=actor, basis=basis, applicable_years=sorted(years)
            )
            st.success(f"核验通过：状态 {c.status}，候选映射：{'是' if c.is_candidate else '否'}")
        except EvidenceGovernanceError as exc:
            st.error(f"操作被拒绝：{exc}")
    if c3.button("核验驳回", key="btn_claim_reject"):
        try:
            c = reject_claim(session, int(claim_id), actor=actor, reason=basis)
            st.warning(f"已驳回，状态：{c.status}")
        except EvidenceGovernanceError as exc:
            st.error(f"操作被拒绝：{exc}")
    if c4.button("标记冲突", key="btn_claim_conflict"):
        try:
            cf = mark_conflict(session, int(claim_id), actor=actor, description=basis)
            st.error(f"已登记冲突 #{cf.id}（未解决；旧事实未被覆盖）")
        except EvidenceGovernanceError as exc:
            st.error(f"操作被拒绝：{exc}")

    st.markdown("---")
    st.markdown("#### 核验历史")
    hist = verification_history(session, int(claim_id)) if claim_id else []
    if not hist:
        st.info("该声明暂无核验历史。")
    else:
        df = pd.DataFrame(
            [
                {
                    "时间": h["at"],
                    "操作者": h["actor"],
                    "动作": h["action"],
                    "对象": f"{h['entity_type']}#{h['entity_id']}",
                    "详情": str(h["detail"]),
                }
                for h in hist
            ]
        )
        data_table(df, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
def _render_gap(session) -> None:
    st.markdown("#### 证据缺口统计（全部来自数据库实查）")
    g = evidence_gap_stats(session)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("来源总数", g["source_total"])
    c2.metric("已登记来源", g["source_registered"])
    c3.metric("已核验来源", g["source_verified"])
    c4.metric("待核验数", g["pending_verification"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("候选证据声明", g["claim_candidate"])
    c2.metric("已核验证据声明", g["claim_verified"])
    c3.metric("冲突数（未解决）", f'{g["conflict_unresolved"]} / {g["conflict_total"]}')
    c4.metric("占位符来源", g["source_placeholder"])

    st.markdown("**统计口径（避免与 Phase 4.0 的 84 / 83 歧义混淆）**")
    df = pd.DataFrame(
        [
            {"指标": "来源记录总数", "数值": g["source_total"], "口径": g["definitions"]["source_total"]},
            {"指标": "已登记来源", "数值": g["source_registered"], "口径": g["definitions"]["source_registered"]},
            {"指标": "已核验来源", "数值": g["source_verified"], "口径": g["definitions"]["source_verified"]},
            {"指标": "占位符来源", "数值": g["source_placeholder"], "口径": "is_placeholder=True 或标题为占位模板或缺失 URL/机构"},
            {"指标": "待核验数", "数值": g["pending_verification"], "口径": g["definitions"]["pending_verification"]},
            {"指标": "状态为已核验但本体未登记", "数值": g["source_status_verified_only"] - g["source_verified"], "口径": "非法态计数，应为 0"},
        ]
    )
    data_table(df, hide_index=True, width="stretch")
    st.info(
        "说明：Phase 4.0 导入的 84 条来源中，83 条为「（引用自 Phase 3.2 候选映射）」式记录、"
        "1 条为 SRC-NA 占位符，**均无本体登记**，因此「已登记来源」为 0。"
    )
