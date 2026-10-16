"""独立决策引擎（对外门面）。

输入：路径上下文（硬约束事实 + 原始评分）。
输出：PathDecision（硬约束状态 / 2028 资格 / 基础与情景聚合 / 双目标结论）。

不变量：
    * 不含任何录取概率字段（由 `assert_no_admission_probability` 强制自检）。
    * 不做网络请求、不读 Excel、不依赖 UI。
    * 缺失数据不补零；未知保持未知。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from decision_system.engine.constraints import (
    ConstraintOutcome,
    HardConstraintFacts,
    evaluate_hard_constraints,
    forced_status_for,
)
from decision_system.engine.coverage import (
    AggregateResult,
    CoverageReport,
    ScoreCell,
    aggregate,
)
from decision_system.engine.objectives import (
    FIRST_CHOICE_VALUE,
    TRAINING_VALUE,
    ObjectiveDef,
    ObjectiveOutcome,
    default_objectives,
    evaluate_objective,
)
from decision_system.engine.scenarios import ScenarioDef, default_scenarios, scenario_weights
from decision_system.engine.weights import WeightTree
from decision_system.evidence.gate import (
    LegacyPhase37CGate,
    ScoreInput,
    ScoreValidation,
    StrictEvidenceGate,
)
from decision_system.models.enums import ComparisonStatus, PathEligibility, ScoreValidity

PROHIBITED_KEY_TOKENS = (
    "probability",
    "prob",
    "录取概率",
    "录取率",
    "上岸率",
    "admit_rate",
    "admission_rate",
    "chance",
)


class DecisionEngineError(RuntimeError):
    pass


def assert_no_admission_probability(payload: Any, path: str = "") -> None:
    """递归检查输出结构中不存在录取概率类字段。"""
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            key = str(k).lower()
            for token in PROHIBITED_KEY_TOKENS:
                if token.lower() in key:
                    raise DecisionEngineError(
                        f"决策输出包含禁止的录取概率字段：{path}{k}"
                    )
            assert_no_admission_probability(v, f"{path}{k}.")
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_no_admission_probability(v, f"{path}[{i}].")


@dataclass
class EngineConfig:
    coverage_threshold: float = 0.8  # Phase 3.7C 演示门槛，可配置
    scenario_threshold: float | None = None  # None = 沿用 coverage_threshold
    objective_group_threshold: float | None = None
    evaluation_year: int = 2028
    profile_code: str = "phase37c_demo"
    strict_evidence: bool = True
    label: str = "Phase 3.7C 演示配置（非用户最终偏好）"

    def __post_init__(self) -> None:
        if not 0.0 <= self.coverage_threshold <= 1.0:
            raise ValueError("覆盖率门槛必须位于 [0,1]")
        if self.scenario_threshold is None:
            self.scenario_threshold = self.coverage_threshold
        if self.objective_group_threshold is None:
            self.objective_group_threshold = self.coverage_threshold


@dataclass(frozen=True)
class PathContext:
    path_key: str
    label: str = ""
    school_name: str = ""
    facts: HardConstraintFacts = field(default_factory=HardConstraintFacts)
    scores: tuple[ScoreInput, ...] = ()


@dataclass
class PathDecision:
    path_key: str
    label: str
    eligibility: PathEligibility
    qualification_2028: Any
    constraint_reasons: tuple[str, ...]
    base: AggregateResult
    scenarios: dict[str, AggregateResult]
    objective_a: ObjectiveOutcome
    objective_b: ObjectiveOutcome
    coverage: CoverageReport
    cells: list[ScoreCell]
    validations: list[ScoreValidation]
    limitations: list[str]
    profile_code: str
    evaluation_year: int

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path_key": self.path_key,
            "label": self.label,
            "evaluation_year": self.evaluation_year,
            "weight_profile": self.profile_code,
            "hard_constraint": {
                "eligibility": self.eligibility.value,
                "qualification_2028": self.qualification_2028.value,
                "reasons": list(self.constraint_reasons),
            },
            "coverage": {
                "indicator_count_coverage": round(self.coverage.indicator_count_coverage, 6),
                "base_weight_coverage": round(self.coverage.base_weight_coverage, 6),
                "scenario_weight_coverage": {
                    k: round(v, 6) for k, v in self.coverage.scenario_weight_coverage.items()
                },
                "threshold": self.coverage.threshold,
            },
            "base": _agg_to_dict(self.base),
            "scenarios": {k: _agg_to_dict(v) for k, v in self.scenarios.items()},
            "objective_A_training_value": _obj_to_dict(self.objective_a),
            "objective_B_first_choice_value": _obj_to_dict(self.objective_b),
            "unknown_indicators": [c.indicator_code for c in self.cells if c.is_unknown],
            "invalid_indicators": [
                {"code": c.indicator_code, "reasons": list(c.reasons)}
                for c in self.cells
                if c.validity is ScoreValidity.INVALID
            ],
            "limitations": list(self.limitations),
            "disclaimer": "本输出不含录取概率，不构成录取预测或院校排名",
        }
        assert_no_admission_probability(payload)
        return payload


def _agg_to_dict(a: AggregateResult) -> dict[str, Any]:
    return {
        "weight_coverage": round(a.weight_coverage, 6),
        "indicator_count_coverage": round(a.indicator_count_coverage, 6),
        "score": None if a.weighted_score is None else round(a.weighted_score, 6),
        "status": a.status.value,
        "valid_count": a.valid_count,
        "total_count": a.total_count,
        "reasons": list(a.reasons),
    }


def _obj_to_dict(o: ObjectiveOutcome) -> dict[str, Any]:
    return {
        "code": o.code,
        "name": o.name,
        "status": o.status.value,
        "score": None if o.score is None else round(o.score, 6),
        "weight_coverage": round(o.weight_coverage, 6),
        "group_coverage": {k: round(v, 6) for k, v in o.group_coverage.items()},
        "reasons": list(o.reasons),
    }


class DecisionEngine:
    """决策引擎：把权重树、证据闸门、硬约束、情景与双目标组合起来。"""

    def __init__(
        self,
        tree: WeightTree,
        *,
        config: EngineConfig | None = None,
        gate: StrictEvidenceGate | LegacyPhase37CGate | None = None,
        scenarios: Mapping[str, ScenarioDef] | None = None,
        objectives: Mapping[str, ObjectiveDef] | None = None,
    ) -> None:
        self.tree = tree
        self.config = config or EngineConfig()
        self.gate = gate
        self.scenarios = dict(scenarios) if scenarios else default_scenarios()
        self.objectives = dict(objectives) if objectives else default_objectives()
        self._base_weights = tree.global_weights()
        self._scenario_weights = {
            code: scenario_weights(tree, sc) for code, sc in self.scenarios.items()
        }
        self._objective_weights = {
            code: None for code in self.objectives
        }  # 惰性计算见 objective_weights

    # ---------- 单条评分校验 ----------
    def validate_scores(
        self, scores: Sequence[ScoreInput], path_key: str
    ) -> tuple[list[ScoreCell], list[ScoreValidation]]:
        evaluations: list[ScoreValidation] = []
        for item in scores:
            if self.gate is None:
                evaluation = ScoreValidation(
                    item.indicator_code, ScoreValidity.UNKNOWN, None, ("未配置证据闸门",)
                )
            else:
                evaluation = self.gate.validate(item, evaluation_year=self.config.evaluation_year)
            evaluations.append(evaluation)

        cells = [
            ScoreCell(
                indicator_code=e.indicator_code,
                raw_score=e.score,
                validity=e.validity,
                reasons=e.reasons,
            )
            for e in evaluations
        ]
        return cells, evaluations

    # ---------- 主流程 ----------
    def evaluate(self, path: PathContext) -> PathDecision:
        outcome: ConstraintOutcome = evaluate_hard_constraints(path.facts)
        forced = forced_status_for(outcome)

        cells, validations = self.validate_scores(path.scores, path.path_key)

        base = aggregate(
            self._base_weights, cells, self.config.coverage_threshold, forced_status=forced
        )
        scenario_results: dict[str, AggregateResult] = {}
        for code in self.scenarios:
            scenario_results[code] = aggregate(
                self._scenario_weights[code],
                cells,
                self.config.scenario_threshold or self.config.coverage_threshold,
                forced_status=forced,
            )

        obj_a = evaluate_objective(
            self.tree,
            self.objectives[TRAINING_VALUE],
            cells,
            self.config.coverage_threshold,
            eligibility_excluded=outcome.eligibility is PathEligibility.EXCLUDED,
            eligibility_pending=outcome.eligibility is PathEligibility.PENDING,
            qualification_2028=outcome.qualification_2028,
            group_threshold=self.config.objective_group_threshold,
        )
        obj_b = evaluate_objective(
            self.tree,
            self.objectives[FIRST_CHOICE_VALUE],
            cells,
            self.config.coverage_threshold,
            eligibility_excluded=outcome.eligibility is PathEligibility.EXCLUDED,
            eligibility_pending=outcome.eligibility is PathEligibility.PENDING,
            qualification_2028=outcome.qualification_2028,
            group_threshold=self.config.objective_group_threshold,
        )

        coverage = CoverageReport(
            indicator_count_coverage=(
                sum(1 for c in cells if c.is_valid) / len(cells) if cells else 0.0
            ),
            base_weight_coverage=base.weight_coverage,
            scenario_weight_coverage={k: v.weight_coverage for k, v in scenario_results.items()},
            threshold=self.config.coverage_threshold,
        )

        limitations = self._limitations(outcome, base, scenario_results)
        decision = PathDecision(
            path_key=path.path_key,
            label=path.label or path.path_key,
            eligibility=outcome.eligibility,
            qualification_2028=outcome.qualification_2028,
            constraint_reasons=outcome.reasons,
            base=base,
            scenarios=scenario_results,
            objective_a=obj_a,
            objective_b=obj_b,
            coverage=coverage,
            cells=cells,
            validations=validations,
            limitations=limitations,
            profile_code=self.config.profile_code,
            evaluation_year=self.config.evaluation_year,
        )
        decision.to_dict()  # 触发禁止字段自检
        return decision

    def evaluate_many(self, paths: Sequence[PathContext]) -> list[PathDecision]:
        return [self.evaluate(p) for p in paths]

    # ---------- 辅助 ----------
    def _limitations(
        self,
        outcome: ConstraintOutcome,
        base: AggregateResult,
        scenarios: Mapping[str, AggregateResult],
    ) -> list[str]:
        notes: list[str] = [
            "覆盖率达标≠结论可靠：未评分权重仍可能改变排序",
            "80% 为可配置演示门槛，非可靠性证明",
            "输出不含录取概率，不构成录取预测",
        ]
        if not outcome.confirmed_2028:
            notes.append(f"2028 资格状态：{outcome.qualification_2028.value}；历史候选≠2028 正式资格")
        for code, agg in scenarios.items():
            if agg.status is ComparisonStatus.INSUFFICIENT:
                notes.append(f"情景 {code} 自身覆盖率不足，输出「证据不足」")
        if base.status is ComparisonStatus.INSUFFICIENT:
            notes.append("基础口径覆盖率不足，输出「证据不足」")
        return notes

    @property
    def base_weights(self) -> dict[str, float]:
        return dict(self._base_weights)

    def scenario_weight_map(self, code: str) -> dict[str, float]:
        return dict(self._scenario_weights[code])
