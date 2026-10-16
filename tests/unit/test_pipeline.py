"""独立决策引擎端到端（纯内存）测试。"""

from __future__ import annotations

import math

import pytest

from decision_system.engine.pipeline import (
    DecisionEngine,
    DecisionEngineError,
    EngineConfig,
    PathContext,
    assert_no_admission_probability,
)
from decision_system.engine.weights import WeightTree
from decision_system.evidence.gate import (
    LegacyPhase37CGate,
    ScoreInput,
    StrictEvidenceGate,
)
from decision_system.models.enums import (
    ComparisonStatus,
    ObjectiveStatus,
    PathEligibility,
    Qualification2028,
    TriState,
    Verification2028,
)

from ..conftest import PATH_KEY, SOURCE_ID, VERIFICATION_YEAR


def _scores(tree: WeightTree, indices=None, value=4) -> tuple[ScoreInput, ...]:
    codes = tree.codes(3)
    if indices is None:
        indices = range(len(codes))
    return tuple(
        ScoreInput(indicator_code=codes[i], raw_score=value, source_id=SOURCE_ID, path_key=PATH_KEY)
        for i in indices
    )


def _facts(**kw) -> "object":
    from decision_system.engine.constraints import HardConstraintFacts

    defaults = dict(
        full_time_ok=TriState.YES,
        program_code_acceptable=TriState.YES,
        other_constraints_ok=TriState.YES,
    )
    defaults.update(kw)
    return HardConstraintFacts(**defaults)


def _engine(tree: WeightTree, gate, **cfg) -> DecisionEngine:
    return DecisionEngine(tree, config=EngineConfig(**cfg), gate=gate)


def test_full_valid_scoring(tree: WeightTree, strict_gate):
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(
        PathContext(path_key=PATH_KEY, label="测试路径", facts=_facts(), scores=_scores(tree))
    )
    assert decision.base.status is ComparisonStatus.COMPARABLE
    assert math.isclose(decision.base.weighted_score, 4.0)
    assert math.isclose(decision.base.weight_coverage, 1.0)
    for code, agg in decision.scenarios.items():
        assert agg.status is ComparisonStatus.COMPARABLE, code
        assert math.isclose(agg.weighted_score, 4.0), code
    assert decision.objective_a.status is ObjectiveStatus.AVAILABLE
    assert decision.objective_b.status is ObjectiveStatus.UNDECIDABLE  # 2028 未确认


def test_full_valid_with_2028_confirmed(tree: WeightTree, strict_gate):
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(
        PathContext(
            path_key=PATH_KEY,
            facts=_facts(
                verification_2028=Verification2028.VERIFIED, has_verified_2028_evidence=True
            ),
            scores=_scores(tree),
        )
    )
    assert decision.qualification_2028 is Qualification2028.CONFIRMED
    assert decision.objective_b.status is ObjectiveStatus.AVAILABLE
    assert math.isclose(decision.objective_b.score, 4.0)


def test_excluded_path_no_scores(tree: WeightTree, strict_gate):
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(
        PathContext(
            path_key=PATH_KEY,
            facts=_facts(other_constraints_ok=TriState.NO),
            scores=_scores(tree),
        )
    )
    assert decision.eligibility is PathEligibility.EXCLUDED
    assert decision.base.weighted_score is None
    assert decision.base.status is ComparisonStatus.EXCLUDED
    for agg in decision.scenarios.values():
        assert agg.weighted_score is None
        assert agg.status is ComparisonStatus.EXCLUDED
    assert decision.objective_a.status is ObjectiveStatus.EXCLUDED
    assert decision.objective_b.status is ObjectiveStatus.EXCLUDED


def test_pending_hard_constraint_no_scores(tree: WeightTree, strict_gate):
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(
        PathContext(
            path_key=PATH_KEY,
            facts=_facts(other_constraints_ok=TriState.UNKNOWN),
            scores=_scores(tree),
        )
    )
    assert decision.eligibility is PathEligibility.PENDING
    assert decision.base.weighted_score is None
    assert decision.base.status is ComparisonStatus.PENDING


def test_strict_gate_rejects_unregistered_source(tree: WeightTree, strict_gate):
    """真实存在但未登记/未核验的来源一律拒绝（严格于旧 Excel）。"""
    scores = tuple(
        ScoreInput(indicator_code=c, raw_score=4, source_id="S-BUPT-J1", path_key=PATH_KEY)
        for c in tree.codes(3)
    )
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(
        PathContext(path_key=PATH_KEY, facts=_facts(), scores=scores)
    )
    assert decision.base.weight_coverage == 0.0
    assert decision.base.status is ComparisonStatus.INSUFFICIENT
    assert decision.base.weighted_score is None
    assert len(decision.cells) == 18
    assert all(not c.is_valid for c in decision.cells)


def test_legacy_gate_reproduces_excel_semantics(tree: WeightTree):
    """历史闸门仅做格式校验，用于黄金比对（不得用于生产决策）。"""
    scores = tuple(
        ScoreInput(indicator_code=c, raw_score=4, source_id="ANY-TEXT", path_key=PATH_KEY)
        for c in tree.codes(3)
    )
    engine = _engine(tree, LegacyPhase37CGate(), evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(PathContext(path_key=PATH_KEY, facts=_facts(), scores=scores))
    assert math.isclose(decision.base.weighted_score, 4.0)


def test_25_output_contains_no_admission_probability(tree: WeightTree, strict_gate):
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(
        PathContext(path_key=PATH_KEY, facts=_facts(), scores=_scores(tree))
    )
    payload = decision.to_dict()

    # 1) 结构性检查：不得存在任何录取概率类字段（键名层面）
    assert_no_admission_probability(payload)

    # 2) 键名扫描
    def _keys(node, prefix=""):
        if isinstance(node, dict):
            for k, v in node.items():
                yield f"{prefix}{k}"
                yield from _keys(v, f"{prefix}{k}.")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                yield from _keys(v, f"{prefix}[{i}].")

    all_keys = list(_keys(payload))
    for key in all_keys:
        for token in ("概率", "录取率", "上岸率", "probability", "admit_rate", "chance"):
            assert token.lower() not in key.lower(), key

    assert payload["disclaimer"]


def test_25b_prohibited_field_detected():
    with pytest.raises(DecisionEngineError):
        assert_no_admission_probability({"scores": {"admission_probability": 0.3}})
    with pytest.raises(DecisionEngineError):
        assert_no_admission_probability({"x": [{"录取率": 0.2}]})


def test_threshold_configurable(tree: WeightTree, strict_gate):
    partial = _scores(tree, range(12))
    engine = _engine(tree, strict_gate, coverage_threshold=0.5, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(PathContext(path_key=PATH_KEY, facts=_facts(), scores=partial))
    assert decision.base.status is ComparisonStatus.COMPARABLE
    strict_engine = _engine(tree, strict_gate, coverage_threshold=0.9, evaluation_year=VERIFICATION_YEAR)
    strict_decision = strict_engine.evaluate(
        PathContext(path_key=PATH_KEY, facts=_facts(), scores=partial)
    )
    assert strict_decision.base.status is ComparisonStatus.INSUFFICIENT


def test_limitations_always_present(tree: WeightTree, strict_gate):
    engine = _engine(tree, strict_gate, evaluation_year=VERIFICATION_YEAR)
    decision = engine.evaluate(PathContext(path_key=PATH_KEY, facts=_facts(), scores=_scores(tree)))
    assert any("录取概率" in x for x in decision.limitations)
    assert any("2028" in x for x in decision.limitations)


def test_engine_has_no_gate_marks_unknown(tree: WeightTree):
    engine = DecisionEngine(tree, config=EngineConfig(evaluation_year=VERIFICATION_YEAR))
    decision = engine.evaluate(PathContext(path_key=PATH_KEY, facts=_facts(), scores=_scores(tree)))
    assert all(c.is_unknown for c in decision.cells)
    assert decision.base.weight_coverage == 0.0
