"""双目标决策测试（Task E：A/B 独立、不得虚构、证据不足可判定）。"""

from __future__ import annotations

import math

import pytest

from decision_system.engine.coverage import ScoreCell
from decision_system.engine.objectives import (
    FIRST_CHOICE_VALUE,
    TRAINING_VALUE,
    ObjectiveDef,
    default_objectives,
    evaluate_objective,
    group_coverage,
    objective_weights,
)
from decision_system.engine.weights import WeightTree
from decision_system.models.enums import (
    ObjectiveStatus,
    Qualification2028,
    ScoreValidity,
)


def _cells(tree: WeightTree, score_by_group: dict[str, int] | None = None):
    score_by_group = score_by_group or {}
    result = []
    for code in tree.codes(3):
        group = tree.node(tree.level1_of(code)).name
        if group in score_by_group:
            result.append(ScoreCell(code, score_by_group[group], ScoreValidity.VALID))
        else:
            result.append(ScoreCell(code, None, ScoreValidity.UNKNOWN))
    return result


def test_objective_weights_are_different(tree: WeightTree):
    a = objective_weights(tree, default_objectives()[TRAINING_VALUE])
    b = objective_weights(tree, default_objectives()[FIRST_CHOICE_VALUE])
    assert math.isclose(sum(a.values()), 1.0, abs_tol=1e-12)
    assert math.isclose(sum(b.values()), 1.0, abs_tol=1e-12)
    diffs = [c for c in a if not math.isclose(a[c], b[c], rel_tol=1e-9)]
    assert len(diffs) >= 10


def test_objective_a_excludes_admission_feasibility_from_denominator(tree: WeightTree):
    a = objective_weights(tree, default_objectives()[TRAINING_VALUE])
    admission_codes = [c for c in tree.codes(3) if tree.node(tree.level1_of(c)).name == "报考可行性"]
    assert all(a[c] == 0.0 for c in admission_codes)
    # 这些指标对 A 而言不在评价范围内，而不是被打了 0 分
    assert sum(a[c] for c in admission_codes) == 0.0


def test_dual_objective_outputs_are_not_the_same_score(tree: WeightTree):
    """同一组评分下，A 与 B 必须得到不同结果（禁止复制综合分）。"""
    cells = _cells(tree, {"职业发展": 5, "研究培养": 5, "报考可行性": 1, "成本安排": 3, "地域生态": 3})
    objs = default_objectives()
    a = evaluate_objective(
        tree, objs[TRAINING_VALUE], cells, 0.5,
        qualification_2028=Qualification2028.CONFIRMED, group_threshold=0.5,
    )
    b = evaluate_objective(
        tree, objs[FIRST_CHOICE_VALUE], cells, 0.5,
        qualification_2028=Qualification2028.CONFIRMED, group_threshold=0.5,
    )
    assert a.status is ObjectiveStatus.AVAILABLE
    assert b.status is ObjectiveStatus.AVAILABLE
    assert a.score is not None and b.score is not None
    assert not math.isclose(a.score, b.score, rel_tol=1e-6)
    assert a.score > b.score  # 报考可行性得分低，B 应显著低于 A


def test_objective_b_requires_confirmed_2028(tree: WeightTree):
    cells = _cells(tree, {"职业发展": 5, "研究培养": 5, "报考可行性": 5, "成本安排": 3, "地域生态": 3})
    b = evaluate_objective(
        tree, default_objectives()[FIRST_CHOICE_VALUE], cells, 0.5,
        qualification_2028=Qualification2028.NOT_CONFIRMED,
    )
    assert b.status is ObjectiveStatus.UNDECIDABLE
    assert b.score is None
    assert any("2028" in r for r in b.reasons)


def test_objective_a_does_not_require_2028(tree: WeightTree):
    cells = _cells(tree, {"职业发展": 5, "研究培养": 5, "成本安排": 3, "地域生态": 3})
    a = evaluate_objective(
        tree, default_objectives()[TRAINING_VALUE], cells, 0.5,
        qualification_2028=Qualification2028.NOT_CONFIRMED, group_threshold=0.5,
    )
    assert a.status is ObjectiveStatus.AVAILABLE


def test_objective_b_requires_admission_group_evidence(tree: WeightTree):
    """缺少报考可行性证据时，B 输出「暂无法判断」。"""
    cells = _cells(tree, {"职业发展": 5, "研究培养": 5, "成本安排": 3, "地域生态": 3})
    b = evaluate_objective(
        tree, default_objectives()[FIRST_CHOICE_VALUE], cells, 0.5,
        qualification_2028=Qualification2028.CONFIRMED, group_threshold=0.5,
    )
    assert b.status is ObjectiveStatus.UNDECIDABLE
    assert b.group_coverage["报考可行性"] == 0.0


def test_objective_a_requires_research_group_evidence(tree: WeightTree):
    cells = _cells(tree, {"职业发展": 5, "报考可行性": 5, "成本安排": 3, "地域生态": 3})
    a = evaluate_objective(
        tree, default_objectives()[TRAINING_VALUE], cells, 0.5,
        qualification_2028=Qualification2028.CONFIRMED, group_threshold=0.5,
    )
    assert a.status is ObjectiveStatus.UNDECIDABLE
    assert a.group_coverage["研究培养"] == 0.0


def test_insufficient_evidence_outputs_pending(tree: WeightTree):
    cells = _cells(tree, {"研究培养": 4})
    a = evaluate_objective(
        tree, default_objectives()[TRAINING_VALUE], cells, 0.8, group_threshold=0.5
    )
    assert a.status is ObjectiveStatus.INSUFFICIENT_EVIDENCE
    assert a.score is None
    assert "待补充证据" == a.status.value


def test_excluded_path_not_evaluated(tree: WeightTree):
    cells = _cells(tree, {"职业发展": 5, "研究培养": 5})
    a = evaluate_objective(
        tree, default_objectives()[TRAINING_VALUE], cells, 0.5, eligibility_excluded=True
    )
    assert a.status is ObjectiveStatus.EXCLUDED
    assert a.score is None


def test_pending_hard_constraint_blocks_objectives(tree: WeightTree):
    cells = _cells(tree, {"职业发展": 5, "研究培养": 5})
    a = evaluate_objective(
        tree, default_objectives()[TRAINING_VALUE], cells, 0.5, eligibility_pending=True
    )
    assert a.status is ObjectiveStatus.PENDING_VERIFICATION


def test_group_coverage_helper(tree: WeightTree):
    weights = tree.global_weights()
    cells = _cells(tree, {"研究培养": 4})
    assert math.isclose(
        group_coverage(tree, weights, cells, "研究培养"),
        sum(v for c, v in weights.items() if tree.node(tree.level1_of(c)).name == "研究培养")
        / sum(v for c, v in weights.items() if tree.node(tree.level1_of(c)).name == "研究培养"),
    )


def test_negative_relevance_rejected(tree: WeightTree):
    with pytest.raises(ValueError):
        objective_weights(tree, ObjectiveDef(code="x", name="x", relevance={"职业发展": -1.0}))


def test_objective_defs_are_demo_configs():
    for obj in default_objectives().values():
        assert obj.is_demo is True
