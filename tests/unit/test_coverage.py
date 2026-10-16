"""覆盖率与缺失处理测试（Task E 16、17、24）。"""

from __future__ import annotations

import math

from decision_system.engine.coverage import ScoreCell, aggregate
from decision_system.engine.scenarios import default_scenarios, scenario_weights
from decision_system.engine.weights import WeightTree
from decision_system.models.enums import ComparisonStatus, ScoreValidity

from ..fixtures import code_of

# Phase 3.7C 回归中构造的"跨阈值子集"：基础 ≥80% 但职业情景 <80%
DIVERGENT_SUBSET = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 13]


def _cells(tree: WeightTree, indices, score=4, source="SRC-X") -> list[ScoreCell]:
    codes = tree.codes(3)
    result = []
    for i, code in enumerate(codes):
        if i in set(indices):
            result.append(ScoreCell(code, score, ScoreValidity.VALID, ("ok",)))
        else:
            result.append(ScoreCell(code, None, ScoreValidity.UNKNOWN, ("未评分",)))
    return result


def test_16_scenario_coverage_judged_independently(tree: WeightTree):
    """每个情景用自身覆盖率判断；基础达标不得让其它情景输出评分。"""
    base_w = tree.global_weights()
    cells = _cells(tree, DIVERGENT_SUBSET)

    base = aggregate(base_w, cells, 0.8)
    assert base.status is ComparisonStatus.COMPARABLE
    assert math.isclose(base.weight_coverage, 0.80275, abs_tol=1e-9)

    results = {}
    for code, sc in default_scenarios().items():
        results[code] = aggregate(scenario_weights(tree, sc), cells, 0.8)

    assert math.isclose(results["career"].weight_coverage, 0.7954148, abs_tol=1e-6)
    assert results["career"].status is ComparisonStatus.INSUFFICIENT
    assert results["career"].weighted_score is None
    assert "证据不足" in [r for r in results["career"].reasons][0]

    assert math.isclose(results["admission"].weight_coverage, 0.8460307, abs_tol=1e-6)
    assert results["admission"].status is ComparisonStatus.COMPARABLE
    assert math.isclose(results["research"].weight_coverage, 0.8340888, abs_tol=1e-6)
    assert results["research"].status is ComparisonStatus.COMPARABLE


def test_16b_base_pass_does_not_license_other_scenarios(tree: WeightTree):
    """覆盖率恰好跨阈值的另一侧：基础不足但某情景达标时，基础仍不得输出。"""
    subset = DIVERGENT_SUBSET[:4]
    cells = _cells(tree, subset)
    base = aggregate(tree.global_weights(), cells, 0.8)
    assert base.weight_coverage < 0.8
    assert base.status is ComparisonStatus.INSUFFICIENT
    assert base.weighted_score is None


def test_17_low_coverage_outputs_insufficient(tree: WeightTree):
    cells = _cells(tree, [0])
    result = aggregate(tree.global_weights(), cells, 0.8)
    assert result.status is ComparisonStatus.INSUFFICIENT
    assert result.weighted_score is None


def test_17b_zero_valid_cells_no_score(tree: WeightTree):
    cells = _cells(tree, [])
    result = aggregate(tree.global_weights(), cells, 0.8)
    assert result.weight_coverage == 0.0
    assert result.weighted_score is None
    assert result.status is ComparisonStatus.INSUFFICIENT


def test_17c_threshold_configurable(tree: WeightTree):
    cells = _cells(tree, DIVERGENT_SUBSET)
    assert aggregate(tree.global_weights(), cells, 0.7).status is ComparisonStatus.COMPARABLE
    assert aggregate(tree.global_weights(), cells, 0.9).status is ComparisonStatus.INSUFFICIENT


def test_24_missing_scores_are_not_zero(tree: WeightTree):
    """缺失数据不得按 0 分计入：分母只含已评分权重。"""
    codes = tree.codes(3)
    cells = [
        ScoreCell(codes[0], 5, ScoreValidity.VALID),
        ScoreCell(codes[1], 1, ScoreValidity.VALID),
        *[ScoreCell(c, None, ScoreValidity.UNKNOWN) for c in codes[2:]],
    ]
    result = aggregate(tree.global_weights(), cells, 0.01)
    w = tree.global_weights()
    expected = (5 * w[codes[0]] + 1 * w[codes[1]]) / (w[codes[0]] + w[codes[1]])
    assert math.isclose(result.weighted_score, expected, rel_tol=1e-12)
    # 若把缺失当 0 分，结果会被稀释到接近 0；此处必须显著高于 1
    assert result.weighted_score > 1.0


def test_24b_invalid_scores_excluded_from_coverage(tree: WeightTree):
    codes = tree.codes(3)
    cells = [ScoreCell(c, 4, ScoreValidity.VALID) for c in codes]
    cells[0] = ScoreCell(codes[0], 4, ScoreValidity.INVALID, ("来源未登记",))
    cells[1] = ScoreCell(codes[1], None, ScoreValidity.UNKNOWN)
    result = aggregate(tree.global_weights(), cells, 0.8)
    assert result.valid_count == 16
    assert result.weight_coverage < 1.0


def test_24c_na_marker_is_unknown_not_zero():
    from decision_system.evidence.gate import ScoreInput, StrictEvidenceGate
    from decision_system.evidence.gate import InMemoryEvidenceResolver

    gate = StrictEvidenceGate(InMemoryEvidenceResolver(), None)
    result = gate.validate(ScoreInput(indicator_code="X", raw_score="不适用"))
    assert result.validity is ScoreValidity.UNKNOWN
    assert result.score is None


def test_indicator_count_coverage_reported(tree: WeightTree):
    cells = _cells(tree, DIVERGENT_SUBSET)
    result = aggregate(tree.global_weights(), cells, 0.8)
    assert result.total_count == 18
    assert result.valid_count == len(DIVERGENT_SUBSET)
    assert math.isclose(result.indicator_count_coverage, len(DIVERGENT_SUBSET) / 18)
