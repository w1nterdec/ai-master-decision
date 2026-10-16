"""与 Phase 3.7C Excel 对照的黄金测试样例。

方法：
    使用「历史兼容闸门」复现 Phase 3.7C 的"格式有效"语义（评分∈{1..5}整数 且 来源非空），
    在共同支持的计算规则上与 Excel/LibreOffice 实测结果逐格比对。

重要说明：
    Python 引擎的默认闸门是**严格证据闸门**（校验来源登记存在性、核验状态、
    路径/指标适用性、证据年份），因此比旧 Excel 更严格。
    本文件使用 Legacy 闸门做数值对齐；严格闸门与 Excel 的差异在
    test_strict_gate_is_stricter_than_excel 中显式验证。
"""

from __future__ import annotations

import json
import math

import pytest

from decision_system.engine.constraints import HardConstraintFacts
from decision_system.engine.pipeline import DecisionEngine, EngineConfig, PathContext
from decision_system.engine.scenarios import ScenarioDef
from decision_system.engine.weights import build_tree_from_rows
from decision_system.evidence.gate import LegacyPhase37CGate, ScoreInput
from decision_system.models.enums import TriState, Verification2028

from ..fixtures import PHASE37C_MULTIPLIERS, PHASE37C_ROWS, raw_excel_rows

TOL = 1e-6
PATH_KEY = "GOLDEN|P01|005|085410|全日制|方向01|2028|统考|一志愿"


@pytest.fixture(scope="module")
def golden_tree():
    return build_tree_from_rows(PHASE37C_ROWS)


@pytest.fixture(scope="module")
def scenarios():
    return {
        code: ScenarioDef(code=code, name=code, multipliers=dict(m), is_demo=True)
        for code, m in PHASE37C_MULTIPLIERS.items()
    }


def test_golden_constant_matches_excel():
    """测试常量必须与原始 Excel 一致，防止常量漂移。"""
    excel_rows = raw_excel_rows()
    assert len(excel_rows) == 18
    for got, want in zip(excel_rows, PHASE37C_ROWS):
        assert got == want


def _run_case(tree, scenarios, indices, value, gate):
    scores = tuple(
        ScoreInput(
            indicator_code=tree.codes(3)[i],
            raw_score=value,
            source_id="TEST_SOURCE",
            path_key=PATH_KEY,
        )
        for i in indices
    )
    if gate == "yes":
        facts = HardConstraintFacts(
            full_time_ok=TriState.YES,
            program_code_acceptable=TriState.YES,
            other_constraints_ok=TriState.YES,
            verification_2028=Verification2028.PENDING,
        )
    else:
        facts = HardConstraintFacts(
            full_time_ok=TriState.YES,
            program_code_acceptable=TriState.YES,
            other_constraints_ok=TriState.NO,
        )
    engine = DecisionEngine(
        tree,
        config=EngineConfig(coverage_threshold=0.8, evaluation_year=2028),
        gate=LegacyPhase37CGate(),
        scenarios=scenarios,
    )
    return engine.evaluate(PathContext(path_key=PATH_KEY, label="P01", facts=facts, scores=scores))


def test_golden_full(golden_tree, scenarios, golden_baseline):
    """18 项均为有效 4 分、硬约束满足。"""
    expected = golden_baseline["cases"]["full"]
    d = _run_case(golden_tree, scenarios, range(18), 4, "yes")

    assert math.isclose(d.base.weight_coverage, expected["D2"], abs_tol=TOL)
    assert math.isclose(d.base.weighted_score, expected["E2"], abs_tol=TOL)
    assert d.base.status.value == expected["I2"]

    mapping = {"career": ("F2", "K2", "P2"), "admission": ("G2", "L2", "Q2"), "research": ("H2", "M2", "R2")}
    for code, (skey, ckey, stkey) in mapping.items():
        assert math.isclose(d.scenarios[code].weighted_score, expected[skey], abs_tol=TOL), code
        assert math.isclose(d.scenarios[code].weight_coverage, expected[ckey], abs_tol=TOL), code
        assert d.scenarios[code].status.value == expected[stkey], code


def test_golden_divergence(golden_tree, scenarios, golden_baseline):
    """基础覆盖率达标但职业情景未达标：职业必须输出「证据不足」。"""
    subset = golden_baseline["subset"]
    expected = golden_baseline["cases"]["divergence"]
    d = _run_case(golden_tree, scenarios, subset, 4, "yes")

    assert math.isclose(d.base.weight_coverage, expected["D2"], abs_tol=TOL)
    assert math.isclose(d.base.weighted_score, expected["E2"], abs_tol=TOL)
    assert d.base.status.value == expected["I2"]

    assert math.isclose(d.scenarios["career"].weight_coverage, expected["K2"], abs_tol=TOL)
    assert d.scenarios["career"].weighted_score is None
    assert d.scenarios["career"].status.value == expected["P2"] == "证据不足"

    assert math.isclose(d.scenarios["admission"].weight_coverage, expected["L2"], abs_tol=TOL)
    assert math.isclose(d.scenarios["admission"].weighted_score, expected["G2"], abs_tol=TOL)
    assert d.scenarios["admission"].status.value == expected["Q2"]

    assert math.isclose(d.scenarios["research"].weight_coverage, expected["M2"], abs_tol=TOL)
    assert math.isclose(d.scenarios["research"].weighted_score, expected["H2"], abs_tol=TOL)
    assert d.scenarios["research"].status.value == expected["R2"]


def test_golden_excluded(golden_tree, scenarios, golden_baseline):
    """硬约束不符：所有分数为空，状态为「硬约束不符-排除」。"""
    expected = golden_baseline["cases"]["excluded"]
    d = _run_case(golden_tree, scenarios, range(18), 4, "no")

    assert d.base.weighted_score is None
    assert d.base.status.value == expected["I2"]
    for code, stkey in (("career", "P2"), ("admission", "Q2"), ("research", "R2")):
        assert d.scenarios[code].weighted_score is None
        assert d.scenarios[code].status.value == expected[stkey]
    # 覆盖率仍然照常计算（与 Excel 一致）
    assert math.isclose(d.base.weight_coverage, expected["D2"], abs_tol=TOL)


def test_golden_invalid_scores(golden_tree, scenarios, golden_baseline):
    """18 项均为非法 99 分：覆盖率 0，全部输出证据不足。"""
    expected = golden_baseline["cases"]["invalid"]
    d = _run_case(golden_tree, scenarios, range(18), 99, "yes")

    assert math.isclose(d.base.weight_coverage, expected["D2"], abs_tol=TOL)
    assert d.base.weighted_score is None
    assert d.base.status.value == expected["I2"]
    for code, ckey, stkey in (
        ("career", "K2", "P2"),
        ("admission", "L2", "Q2"),
        ("research", "M2", "R2"),
    ):
        assert math.isclose(d.scenarios[code].weight_coverage, expected[ckey], abs_tol=TOL)
        assert d.scenarios[code].weighted_score is None
        assert d.scenarios[code].status.value == expected[stkey]


def test_golden_db_weights_match_excel(db, golden_tree):
    """导入后的数据库权重树必须与 Excel 计算口径完全一致。"""
    from decision_system.services.decision_service import build_weight_tree

    db_tree = build_weight_tree(db, "phase37c_demo")
    assert db_tree.codes(3) == golden_tree.codes(3)
    for code in golden_tree.codes(3):
        assert math.isclose(
            db_tree.global_weight(code), golden_tree.global_weight(code), rel_tol=1e-12
        ), code
    assert math.isclose(db_tree.total_global_weight(), 1.0, abs_tol=1e-12)


def test_strict_gate_is_stricter_than_excel(golden_tree, scenarios):
    """严格闸门下，Excel 视为"有效"的评分会因来源未登记而被拒绝。"""
    from decision_system.evidence.gate import InMemoryEvidenceResolver, StrictEvidenceGate

    scores = tuple(
        ScoreInput(indicator_code=c, raw_score=4, source_id="TEST_SOURCE", path_key=PATH_KEY)
        for c in golden_tree.codes(3)
    )
    facts = HardConstraintFacts(
        full_time_ok=TriState.YES,
        program_code_acceptable=TriState.YES,
        other_constraints_ok=TriState.YES,
    )
    legacy = DecisionEngine(
        golden_tree, config=EngineConfig(), gate=LegacyPhase37CGate(), scenarios=scenarios
    ).evaluate(PathContext(path_key=PATH_KEY, facts=facts, scores=scores))
    strict = DecisionEngine(
        golden_tree,
        config=EngineConfig(),
        gate=StrictEvidenceGate(InMemoryEvidenceResolver()),
        scenarios=scenarios,
    ).evaluate(PathContext(path_key=PATH_KEY, facts=facts, scores=scores))

    assert math.isclose(legacy.base.weight_coverage, 1.0)
    assert strict.base.weight_coverage == 0.0
    assert strict.base.status.value == "证据不足"
