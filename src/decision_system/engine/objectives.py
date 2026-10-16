"""双目标决策：A 培养与职业价值 / B 一志愿报考价值。

两个目标必须**独立**输出，禁止把同一个综合分复制成两个结论。

    A. 这条硕士路径是否值得读？        -> ObjectiveCode.TRAINING_VALUE
    B. 这条路径是否值得投入唯一一次考研机会？ -> ObjectiveCode.FIRST_CHOICE_VALUE

差异来源（可审计、可配置）：
    1. 相关性矩阵不同：不同一级指标对两个目标的相关度不同（0 表示不在该目标评价范围内，
       **不代表给 0 分**，而是从该目标的权重分母中剔除）。
    2. 必备分组门槛不同：A 必须具备「研究培养」证据，B 必须具备「报考可行性」证据；
       必备分组自身覆盖率不足时输出「暂无法判断」。
    3. B 额外要求 2028 正式资格已确认；否则输出「暂无法判断」。

默认相关性矩阵是**演示配置**，不是用户最终偏好，可由 WeightProfile 覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from decision_system.engine.coverage import AggregateResult, ScoreCell, aggregate
from decision_system.engine.weights import EPS, WeightTree
from decision_system.models.enums import ObjectiveStatus, Qualification2028

TRAINING_VALUE = "training_value"
FIRST_CHOICE_VALUE = "first_choice_value"

# 相关性矩阵：一级指标名称 -> 相关度（0~1）
DEFAULT_RELEVANCE_A: Mapping[str, float] = {
    "职业发展": 1.0,
    "研究培养": 1.0,
    "地域生态": 0.6,
    "成本安排": 0.5,
    "报考可行性": 0.0,  # 与"读了值不值"无直接关系，不计入 A 的权重分母
}

DEFAULT_RELEVANCE_B: Mapping[str, float] = {
    "报考可行性": 1.0,  # 名额/科目/复试规则：决定唯一一次机会的风险
    "职业发展": 0.8,
    "成本安排": 0.6,
    "研究培养": 0.3,
    "地域生态": 0.2,
}


@dataclass(frozen=True)
class ObjectiveDef:
    code: str
    name: str
    relevance: Mapping[str, float] = field(default_factory=dict)
    required_groups: tuple[str, ...] = ()
    require_confirmed_2028: bool = False
    is_demo: bool = True
    description: str = ""


def default_objectives() -> dict[str, ObjectiveDef]:
    return {
        TRAINING_VALUE: ObjectiveDef(
            code=TRAINING_VALUE,
            name="A. 培养与职业价值评估（是否值得读）",
            relevance=dict(DEFAULT_RELEVANCE_A),
            required_groups=("研究培养",),
            require_confirmed_2028=False,
            description="回答「这条硕士路径是否值得读」；不要求 2028 资格已确认，但排除路径一律不适用。",
        ),
        FIRST_CHOICE_VALUE: ObjectiveDef(
            code=FIRST_CHOICE_VALUE,
            name="B. 一志愿报考价值评估（是否值得投入唯一一次考研机会）",
            relevance=dict(DEFAULT_RELEVANCE_B),
            required_groups=("报考可行性",),
            require_confirmed_2028=True,
            description="回答「是否值得押上唯一一次考研机会」；2028 资格未确认时输出暂无法判断。",
        ),
    }


def _relevance_for(objective: ObjectiveDef, tree: WeightTree, code: str) -> float:
    l1 = tree.level1_of(code)
    l1_name = tree.node(l1).name
    if l1_name in objective.relevance:
        return float(objective.relevance[l1_name])
    if l1 in objective.relevance:
        return float(objective.relevance[l1])
    return 1.0


def objective_weights(tree: WeightTree, objective: ObjectiveDef, level: int = 3) -> dict[str, float]:
    """目标口径下的归一化权重。"""
    for k, v in objective.relevance.items():
        if v < 0:
            raise ValueError(f"目标 {objective.code} 的相关度为负：{k}={v}")
    raw = {
        c: tree.global_weight(c) * _relevance_for(objective, tree, c) for c in tree.codes(level)
    }
    total = sum(raw.values())
    if total <= EPS:
        return {c: 0.0 for c in raw}
    return {c: v / total for c, v in raw.items()}


def group_coverage(
    tree: WeightTree,
    weights: Mapping[str, float],
    cells: list[ScoreCell],
    group_name: str,
) -> float:
    """指定一级分组在给定权重口径下的有效权重覆盖率。"""
    valid = {c.indicator_code for c in cells if c.is_valid}
    covered = 0.0
    total = 0.0
    for code, w in weights.items():
        if tree.node(tree.level1_of(code)).name != group_name:
            continue
        total += w
        if code in valid:
            covered += w
    return covered / total if total > EPS else 0.0


@dataclass(frozen=True)
class ObjectiveOutcome:
    code: str
    name: str
    status: ObjectiveStatus
    score: float | None = None
    weight_coverage: float = 0.0
    group_coverage: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    detail: AggregateResult | None = None

    @property
    def decidable(self) -> bool:
        return self.status is ObjectiveStatus.AVAILABLE


def evaluate_objective(
    tree: WeightTree,
    objective: ObjectiveDef,
    cells: list[ScoreCell],
    threshold: float,
    *,
    eligibility_excluded: bool = False,
    eligibility_pending: bool = False,
    qualification_2028: Qualification2028 = Qualification2028.NOT_CONFIRMED,
    group_threshold: float | None = None,
) -> ObjectiveOutcome:
    gt = threshold if group_threshold is None else group_threshold
    weights = objective_weights(tree, objective)

    if eligibility_excluded:
        return ObjectiveOutcome(
            objective.code, objective.name, ObjectiveStatus.EXCLUDED,
            reasons=("路径已被硬约束排除，不参与双目标评估",),
        )
    if eligibility_pending:
        return ObjectiveOutcome(
            objective.code, objective.name, ObjectiveStatus.PENDING_VERIFICATION,
            reasons=("硬约束待核验，双目标评估暂不可用",),
        )
    if objective.require_confirmed_2028 and qualification_2028 is not Qualification2028.CONFIRMED:
        return ObjectiveOutcome(
            objective.code,
            objective.name,
            ObjectiveStatus.UNDECIDABLE,
            reasons=(
                f"2028 正式资格状态为「{qualification_2028.value}」，"
                "无法判断唯一一次考研机会是否值得投入",
            ),
        )

    agg = aggregate(weights, cells, threshold)
    group_cov = {
        g: group_coverage(tree, weights, cells, g)
        for g in objective.required_groups
    }
    failed = [g for g, v in group_cov.items() if v + 1e-12 < gt]

    reasons = list(agg.reasons)
    if agg.status is not None and not agg.comparable:
        status = ObjectiveStatus.INSUFFICIENT_EVIDENCE
    elif failed:
        status = ObjectiveStatus.UNDECIDABLE
        reasons.append(
            "必备分组证据不足：" + "、".join(f"{g}({group_cov[g]:.4f}<{gt:.4f})" for g in failed)
        )
    else:
        status = ObjectiveStatus.AVAILABLE

    return ObjectiveOutcome(
        code=objective.code,
        name=objective.name,
        status=status,
        score=agg.weighted_score if status is ObjectiveStatus.AVAILABLE else None,
        weight_coverage=agg.weight_coverage,
        group_coverage=group_cov,
        reasons=tuple(reasons),
        detail=agg,
    )
