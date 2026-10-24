"""【招生路径】工作台（Task B）。"""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import streamlit as st

from decision_system.ui.theme import data_table

from decision_system.services.evidence_service import claims_of_path
from decision_system.ui.decision_view import (
    PathRow,
    filter_path_rows,
    missing_indicators,
    row_to_dict,
)
from decision_system.ui.formatting import (
    MISSING_TEXT,
    quota_text,
    render_status,
    show_value,
)


def _options(rows: Sequence[PathRow]) -> tuple[list[str], list[str], list[str]]:
    schools = sorted({r.school_name for r in rows if r.school_name})
    colleges = sorted(
        {(f"{r.college_name}（{r.college_code}）" if r.college_name else r.college_code) for r in rows}
    )
    programs = sorted({r.program_code for r in rows if r.program_code})
    return schools, colleges, programs


def render(session, rows: Sequence[PathRow]) -> None:
    st.subheader("招生路径")
    st.caption("功能状态：本页提供只读筛选与核对；新增或修改招生路径需编辑原始 Excel，再运行初始化导入。网页尚无路径编辑表单。")
    if not rows:
        st.info("数据库中暂无招生路径。请先用 `python3 scripts/import_excel.py` 导入 Excel。")
        return

    schools, colleges, programs = _options(rows)
    c1, c2, c3 = st.columns(3)
    school = c1.selectbox("按学校筛选", ["全部"] + schools)
    college = c2.selectbox("按学院筛选", ["全部"] + colleges)
    program = c3.selectbox("按专业代码筛选", ["全部"] + programs)

    filtered = filter_path_rows(
        rows,
        school=None if school == "全部" else school,
        college=None if college == "全部" else college,
        program_code=None if program == "全部" else program,
    )
    st.caption(f"筛选结果：{len(filtered)} / {len(rows)} 条路径")

    if filtered:
        df = pd.DataFrame([row_to_dict(r) for r in filtered])
        data_table(df, hide_index=True, width="stretch")
    else:
        st.warning("当前筛选条件下没有路径。")

    st.markdown("---")
    st.markdown("#### 路径详情")
    if not filtered:
        return
    labels = [f"{r.path.legacy_path_id or r.path_key} · {r.school_name} · {r.program_code}" for r in filtered]
    idx = st.selectbox("选择路径查看详细信息", range(len(filtered)), format_func=lambda i: labels[i])
    row: PathRow = filtered[idx]
    _render_detail(session, row)


def _render_detail(session, row: PathRow) -> None:
    p = row.path
    d = row.decision

    st.markdown(f"**{p.legacy_path_id or p.path_key}　{p.school.name if p.school else ''}**")
    st.caption(f"path_key：`{p.path_key}`")

    left, right = st.columns(2)
    with left:
        st.markdown("**基本字段**")
        st.markdown(
            f"""
- 学校名称：{show_value(p.school.name if p.school else None)}
- 学院名称及代码：{show_value((p.college.name if p.college else None))}（{show_value(p.college.college_code if p.college else None)}）
- 专业代码：{show_value(p.program.program_code if p.program else None)}
- 学习方式：{show_value(str(p.study_mode))}
- 招生方向：{show_value(p.direction)}
- 招生年份：{show_value(p.admission_year)}
- 招生方式：{show_value(str(p.admission_method))}
- 路径角色：{show_value(str(p.path_kind))}
"""
        )
    with right:
        st.markdown("**资格与硬约束**")
        st.markdown(
            f"""
- 2028 资格核验状态：{render_status(p.verification_2028)}
- 硬约束状态：{render_status(d.eligibility)}
- 2028 正式资格：{render_status(d.qualification_2028)}
- 全日制约束：{render_status(p.full_time_ok)}
- 专业代码可接受：{render_status(p.program_code_acceptable)}
- 其他约束：{render_status(p.other_constraints_ok)}
"""
        )
        if d.constraint_reasons:
            st.markdown("判定理由：")
            for reason in d.constraint_reasons:
                st.markdown(f"- {reason}")

    st.warning(
        "注意：**历史候选路径 ≠ 2028 正式招生资格**。"
        "仅当「2028 正式资格」一栏显示为「已确认」时才可视作已取得 2028 正式资格；"
        "显示为「2028资格未确认」或「待2028核验」时，一律按**未确认**处理。"
    )

    st.markdown("**数据完整度**")
    st.markdown(
        f"- 有效证据指标：{d.base.valid_count} / {d.base.total_count}"
        f"（加权覆盖率 {d.base.weight_coverage:.4f}，门槛 {0.8}）"
    )
    st.markdown(f"- 当前计算状态：{render_status(d.base.status)}")

    with st.expander("该路径对应的证据（全部状态，含候选映射）", expanded=False):
        claims = claims_of_path(session, p.id)
        if not claims:
            st.info("暂无关联证据。")
        else:
            for c in claims:
                st.markdown(
                    f"- #{c.id} ｜来源 `{c.source_ref_id}` ｜状态 {render_status(c.status)}"
                    f"｜候选映射：{'是' if c.is_candidate else '否'}"
                )
                st.caption(show_value(c.statement, missing="（声明内容为空）"))

    with st.expander("缺失数据（尚无有效评分的三级指标）", expanded=False):
        miss = missing_indicators(session, p)
        if not miss:
            st.success("该路径的全部三级指标均有评分记录。")
        else:
            st.markdown(f"共 {len(miss)} 项待补充：")
            for m in miss:
                st.markdown(f"- {m}")

    with st.expander("历史招生记录", expanded=False):
        recs = list(p.records)
        if not recs:
            st.info("暂无招生记录（**不显示为 0 人**）。")
        else:
            for r in recs:
                st.markdown(
                    f"- {r.year} 年 ｜{r.admission_method} ｜{r.quota_basis} ｜{quota_text(r.planned_quota, r.actual_admitted)}"
                )

    if p.key_risk or p.notes:
        with st.expander("风险与备注", expanded=False):
            st.markdown(show_value(p.key_risk, missing=MISSING_TEXT))
            if p.notes:
                st.caption(show_value(p.notes))
