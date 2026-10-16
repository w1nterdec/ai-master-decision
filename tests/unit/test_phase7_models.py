"""Phase 7.0｜纯函数单元测试：A/B/C/D 分类与四层决策解释。

不依赖数据库，只验证分类与解释逻辑的正确性（P2 / P3 核心）。
"""

from __future__ import annotations

import pytest

from decision_system.ui.viewmodels import (
    GRADE_A,
    GRADE_B,
    GRADE_C,
    ClaimItem,
    QUAL_CONFIRMED,
)
from decision_system.ui.viewmodels import _is_explicit_inference
from decision_system.services.decision_policy import build_decision_explanation


def _item(
    *,
    statement: str,
    status: str = "已核验",
    source_status: str = "已核验",
    is_candidate: bool = False,
    years: tuple[int, ...] = (2027,),
) -> ClaimItem:
    return ClaimItem(
        statement=statement,
        topic=None,
        status=status,
        applicable_years=years,
        source_title="SRC",
        source_status=source_status,
        source_type="官方招生目录",
        url_or_file=None,
        is_candidate=is_candidate,
    )


# ---------------------------------------------------------------------------
# P2｜A/B/C/D 分类
# ---------------------------------------------------------------------------
def test_verified_claim_with_verified_source_is_A():
    it = _item(statement="2027 年目录计划 132 人")
    assert grade_A(it) == GRADE_A


def test_candidate_never_A():
    it = _item(statement="候选映射：疑似招生", is_candidate=True)
    assert grade_A(it) == GRADE_B


def test_unverified_source_downgrades_to_B():
    it = _item(statement="某声明", status="已核验", source_status="待核验")
    assert grade_A(it) == GRADE_B


def test_scope_mismatch_downgrades_to_B():
    it = _item(statement="事实", status="已核验", source_status="已核验")
    # scope_ok=False 表示适用范围不正确 → 即便已核验也降级为 B（不冒充 A）
    assert grade_A(it, scope_ok=False) == GRADE_B


def test_conflict_downgrades_to_B():
    it = _item(statement="事实", status="已核验", source_status="已核验")
    assert grade_A(it, has_conflict=True) == GRADE_B


def test_inference_only_via_explicit_prefix():
    # 正文中间出现"推断"二字（且声明为待核验），不应触发 C 类（P2 明确禁止仅凭关键词）
    it = _item(
        statement="该方向招生计划含推免，推断其统考名额偏紧",
        status="待核验", source_status="待核验",
    )
    assert grade_A(it) == GRADE_B  # 仍是 B（待核验研究资料），不是 C
    # 显式结构化前缀才归 C
    it2 = _item(
        statement="【推断】该方向就业偏向通信产业",
        status="待核验", source_status="待核验",
    )
    assert grade_A(it2) == GRADE_C


def test_is_explicit_inference_prefixes():
    assert _is_explicit_inference("【推断】x")
    assert _is_explicit_inference("（推断）x")
    assert not _is_explicit_inference("这里推断一下")
    assert not _is_explicit_inference(None)


def grade_A(item, *, scope_ok=True, has_conflict=False):
    from decision_system.ui.viewmodels import grade_claim

    return grade_claim(item, scope_ok=scope_ok, has_conflict=has_conflict)


# ---------------------------------------------------------------------------
# P3｜四层决策解释
# ---------------------------------------------------------------------------
def test_layer1_worth_reading_with_verified_facts():
    expl = build_decision_explanation(
        path_key="K", title="北邮 085410", subtitle="全日制 · 一志愿 · 2028",
        verified_facts=["2027 目录计划 132 人（含推免）", "考试科目 408"],
        evidence_state="已核实", qualification_text=QUAL_CONFIRMED,
        qualification_reasons=(), exam_unit4="408 计算机学科专业基础",
        key_risk=None, quota_state="暂无分口径记录", has_verified_2028=True,
        is_demo_profile=False, confirmed_profile=True,
    )
    assert expl.layer1_worth_reading.verdict in ("重点研究", "保留候选")
    assert not expl.layer1_worth_reading.blocked


def test_layer2_blocked_when_2028_unconfirmed():
    expl = build_decision_explanation(
        path_key="K", title="T", subtitle="s",
        verified_facts=[], evidence_state="待核验",
        qualification_text="未确认", qualification_reasons=("声明仅适用 2027",),
        exam_unit4="408", key_risk=None, quota_state="无",
        has_verified_2028=False, is_demo_profile=True, confirmed_profile=False,
    )
    assert expl.layer2_worth_testing.blocked is True
    assert expl.layer2_worth_testing.verdict == "资格尚未确认"


def test_layer3_carries_no_second_try_policy():
    expl = build_decision_explanation(
        path_key="K", title="T", subtitle="s", verified_facts=[],
        evidence_state="待核验", qualification_text="未确认",
        qualification_reasons=(), exam_unit4="408", key_risk=None,
        quota_state="无", has_verified_2028=False,
        is_demo_profile=True, confirmed_profile=False,
    )
    policy_text = " ".join(expl.global_policy)
    assert "不二战" in policy_text
    assert "一志愿" in expl.layer3_fallback.verdict or "后备" in expl.layer3_fallback.verdict


def test_layer4_demo_flagged_explicitly():
    expl = build_decision_explanation(
        path_key="K", title="T", subtitle="s", verified_facts=[],
        evidence_state="待核验", qualification_text="未确认",
        qualification_reasons=(), exam_unit4="408", key_risk=None,
        quota_state="无", has_verified_2028=False,
        is_demo_profile=True, confirmed_profile=False,
    )
    assert "演示配置" in expl.layer4_preference.verdict
    joined = " ".join(expl.layer4_preference.reasons)
    assert "演示" in joined
