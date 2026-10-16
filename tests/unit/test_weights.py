"""三级动态权重测试（Task E 9-15）。"""

from __future__ import annotations

import math

import pytest

from decision_system.engine.scenarios import ScenarioDef, default_scenarios, scenario_weights
from decision_system.engine.weights import NegativeWeightError, WeightError

from ..fixtures import PHASE37C_ROWS

L1_CAREER = "L1-职业发展"
L1_ADMISSION = "L1-报考可行性"
L2_CAREER_JOB = "L2-职业发展|AI工程就业"
L3_JOB_OPP = "L3-职业发展|AI工程就业|岗位与实习机会"
L3_LIFE = "L3-地域生态|生活适配|地域与气候"
L2_LIFE = "L2-地域生态|生活适配"


def test_14_global_weight_normalized(tree):
    """全局三级权重合计为 100%。"""
    weights = tree.global_weights()
    assert len(weights) == 18
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12)
    assert tree.validate() == []


def test_09_level1_weight_change_propagates(tree):
    """一级权重修改应在全局权重中正确传播，且仍归一。"""
    before = tree.global_weights()
    new_tree = tree.with_updated_weight(L1_CAREER, 70.0)
    after = new_tree.global_weights()

    # 职业发展组权重翻倍（相对其它组）
    career_codes = [c for c in before if new_tree.level1_of(c) == L1_CAREER]
    other_codes = [c for c in before if new_tree.level1_of(c) == L1_ADMISSION]
    for c in career_codes:
        assert after[c] > before[c]
    for c in other_codes:
        assert after[c] < before[c]
    assert math.isclose(sum(after.values()), 1.0, abs_tol=1e-12)
    # 组内相对关系不变
    ratio_before = before[career_codes[0]] / before[career_codes[1]]
    ratio_after = after[career_codes[0]] / after[career_codes[1]]
    assert math.isclose(ratio_before, ratio_after, rel_tol=1e-9)


def test_10_level2_weight_change_propagates(tree):
    """二级组内权重修改只影响该二级组，且组内重新归一。"""
    before = tree.global_weights()
    new_tree = tree.with_updated_weight(L2_CAREER_JOB, 100.0)  # AI工程就业 50 -> 100
    after = new_tree.global_weights()

    in_group = [c for c in before if new_tree.node(c).parent_code == L2_CAREER_JOB]
    out_group = [c for c in before if new_tree.node(c).parent_code == "L2-职业发展|长期成长"]
    for c in in_group:
        assert after[c] > before[c]
    for c in out_group:
        assert after[c] < before[c]
    assert math.isclose(sum(after.values()), 1.0, abs_tol=1e-12)


def test_11_level3_weight_change_propagates(tree):
    """三级组内权重修改只影响同组兄弟，组总权重不变。"""
    before = tree.global_weights()
    sibling = "L3-职业发展|AI工程就业|产业合作可参与性"
    group_total_before = before[L3_JOB_OPP] + before[sibling]
    new_tree = tree.with_updated_weight(L3_JOB_OPP, 75.0)
    after = new_tree.global_weights()
    group_total_after = after[L3_JOB_OPP] + after[sibling]
    assert math.isclose(group_total_before, group_total_after, rel_tol=1e-9)
    assert after[L3_JOB_OPP] > before[L3_JOB_OPP]
    assert after[sibling] < before[sibling]


def test_12_negative_weight_rejected(tree):
    """负权重一律拒绝（构造期与修改期）。"""
    with pytest.raises(NegativeWeightError):
        tree.with_updated_weight(L1_CAREER, -1.0)
    with pytest.raises(NegativeWeightError):
        tree.with_updated_weight(L3_JOB_OPP, -0.0001)
    with pytest.raises(WeightError):
        type(tree)(
            tuple(
                n.__class__(**{**n.__dict__, "raw_weight": -5.0})
                if n.code == L1_CAREER
                else n
                for n in tree.nodes
            )
        )


def test_13_zero_weight_group_handled(tree):
    """零权重分组：不做除法、权重按 0 处理、登记空组，不抛异常、不产生 NaN。"""
    new_tree = tree.with_updated_weight(L3_LIFE, 0.0)
    assert math.isclose(new_tree.global_weight(L3_LIFE), 0.0, abs_tol=1e-15)
    assert L2_LIFE in new_tree.empty_groups
    issues = new_tree.validate()
    assert any("组内权重合计为 0" in i for i in issues)
    total = new_tree.total_global_weight()
    assert not math.isnan(total)
    assert math.isclose(total, 1.0 - tree.global_weight(L3_LIFE), rel_tol=1e-9)


def test_15_scenario_weights_independently_normalized(tree):
    """情景权重独立归一化，且与基础权重不同。"""
    base = tree.global_weights()
    for code, sc in default_scenarios().items():
        weights = scenario_weights(tree, sc)
        assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12), code
        assert len(weights) == 18
        # 情景权重确实改变了分布
        assert any(not math.isclose(weights[c], base[c], rel_tol=1e-6) for c in base)


def test_scenario_negative_multiplier_rejected(tree):
    with pytest.raises(WeightError):
        scenario_weights(tree, ScenarioDef(code="bad", name="bad", multipliers={"职业发展": -1.0}))


def test_scenario_degenerate_all_zero_multiplier(tree):
    """全部倍率为 0 时，防止除零：返回全 0 而不是 NaN。"""
    weights = scenario_weights(
        tree, ScenarioDef(code="zero", name="zero", multipliers={"职业发展": 0.0})
    )
    assert all(not math.isnan(v) for v in weights.values())


def test_weight_profile_is_demo_config():
    """默认权重配置必须标记为演示配置，不得冒充用户最终偏好。"""
    for sc in default_scenarios().values():
        assert sc.is_demo is True
    assert PHASE37C_ROWS[0]["w1"] == 35
