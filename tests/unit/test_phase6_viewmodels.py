"""Phase 6.0｜只读展示模型（ViewModel）单元测试。

纪律检查点：V4.0 维度顺序、未知不补零、对比永不宣布赢家、档案往返序列化。
"""

from __future__ import annotations

import pytest

from decision_system.services.view_service import _eval_state
from decision_system.ui.viewmodels import (
    CONFLICT,
    NOT_APPLICABLE,
    NOT_EVALUATED,
    PARTIAL,
    PENDING,
    QUAL_CONFIRMED,
    QUAL_UNCONFIRMED,
    UNJUDGEABLE,
    UNKNOWN,
    VERIFIED,
    ComparisonCell,
    ComparisonSummary,
    DecisionArchive,
    EvidenceSummary,
    PathSummary,
    RiskGap,
    V4_DIMENSION_MAP,
    COMPARE_DIMENSIONS,
    v4_label,
    v4_order,
)

ALL_L1 = ("L1-职业发展", "L1-报考可行性", "L1-研究培养", "L1-地域生态", "L1-成本安排")


def test_v4_order_matches_v4_sequence():
    assert v4_order(list(ALL_L1)) == [
        "L1-地域生态",
        "L1-成本安排",
        "L1-研究培养",
        "L1-报考可行性",
        "L1-职业发展",
    ]


def test_v4_label_covers_all_level1():
    for code in ALL_L1:
        assert v4_label(code).startswith(("01", "02", "03", "04", "05")), code


def test_v4_map_has_five_dimensions():
    assert len(V4_DIMENSION_MAP) == 5


def test_compare_dimensions_are_ten():
    assert len(COMPARE_DIMENSIONS) == 10


def test_comparison_never_declares_winner():
    comp = ComparisonSummary(
        paths=(),
        rows=(("维度A", (ComparisonCell("维度A", "高", True), ComparisonCell("维度A", "低", True))),),
    )
    assert comp.has_winner is False
    assert comp.judgeable_rows == 1


def test_unjudgeable_rows_not_counted():
    comp = ComparisonSummary(
        paths=(),
        rows=(("维度A", (ComparisonCell("维度A", UNJUDGEABLE, False),)),),
    )
    assert comp.judgeable_rows == 0


def test_unknown_constants_are_not_zero_like():
    """未知状态文案不得是 0 / 空串 / '0'。"""
    for s in (UNKNOWN, PENDING, VERIFIED, CONFLICT, NOT_APPLICABLE, UNJUDGEABLE):
        assert s not in ("", "0", 0, None)
        assert isinstance(s, str) and s.strip()


def test_eval_state_unknown_is_not_evaluated():
    assert _eval_state(None) == NOT_EVALUATED
    assert _eval_state(0.0) == NOT_EVALUATED
    assert _eval_state(0.5) == PARTIAL
    assert _eval_state(0.9) == "已评估"


def test_risk_gap_priority_text():
    g = RiskGap("t", "r", True, True, True, False)
    g.score = 2 + 1 + 1
    assert g.priority_text == "高"
    g2 = RiskGap("t", "r", False, False, False, False)
    g2.score = 0
    assert g2.priority_text == "低"


def test_archive_roundtrip():
    a = DecisionArchive(
        candidate_path_ids=[1, 2],
        favorite_path_ids=[3],
        active_profile_code="my_v1",
        is_demo_profile=False,
        scenario_code="career",
        notes=["备注一"],
    )
    b = DecisionArchive.from_dict(a.to_dict())
    assert b.candidate_path_ids == [1, 2]
    assert b.favorite_path_ids == [3]
    assert b.active_profile_code == "my_v1"
    assert b.is_demo_profile is False
    assert b.scenario_code == "career"
    assert b.notes == ["备注一"]


def test_archive_default_is_demo():
    """默认档案必须标记为演示配置，避免被误当用户已确认偏好。"""
    assert DecisionArchive().is_demo_profile is True


def test_path_summary_qualification_flag():
    def make(qual: str) -> PathSummary:
        return PathSummary(
            path_id=1,
            path_key="K",
            legacy_id="P01",
            school_name="X",
            school_code="X",
            college_name="",
            college_code="",
            program_code="085410",
            program_name=None,
            study_mode="全日制",
            direction=None,
            exam_unit4=None,
            admission_year=2028,
            admission_method="统考",
            path_kind="一志愿",
            training_location=None,
            qualification_2028=qual,
            eligibility="硬约束待确认-不可比较",
            key_risk=None,
            notes=None,
            evidence=EvidenceSummary(),
        )

    assert make(QUAL_CONFIRMED).qualification_is_confirmed is True
    assert make(QUAL_UNCONFIRMED).qualification_is_confirmed is False
    assert make(UNKNOWN).qualification_is_confirmed is False


@pytest.mark.parametrize(
    "year_text,expected",
    [(2028, True), (2027, False)],
)
def test_claim_year_flag(year_text: int, expected: bool):
    from decision_system.ui.viewmodels import ClaimItem

    item = ClaimItem(
        statement="s",
        topic=None,
        status=VERIFIED,
        applicable_years=(year_text,),
        source_title="t",
        source_status=VERIFIED,
        source_type=None,
        url_or_file=None,
        is_candidate=False,
    )
    assert item.is_2028 is expected
