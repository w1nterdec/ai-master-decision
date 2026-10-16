"""证据覆盖率与加权评分。

核心规则：
    * 只有"有效评分"计入覆盖率；空白（未知）保持未知，**不计 0 分**、也不计入分子分母。
    * 加权分的分母为"已有效评分指标的权重之和"，即缺失项被排除，而不是按 0 计入。
    * 加权分为 0 有效项时不产生数值（None），避免除零。
    * 覆盖率 = 已有效评分指标权重之和 / 全部指标权重之和（按指定权重口径）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from decision_system.engine.weights import EPS
from decision_system.models.enums import ComparisonStatus, ScoreValidity


@dataclass(frozen=True)
class ScoreCell:
    indicator_code: str
    raw_score: int | None = None
    validity: ScoreValidity = ScoreValidity.UNKNOWN
    reasons: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.validity is ScoreValidity.VALID and self.raw_score is not None

    @property
    def is_unknown(self) -> bool:
        return self.validity is ScoreValidity.UNKNOWN


@dataclass(frozen=True)
class AggregateResult:
    """某一权重口径（基础 / 情景 / 目标）下的聚合结果。"""

    weight_coverage: float
    indicator_count_coverage: float
    weighted_score: float | None
    valid_count: int
    total_count: int
    covered_weight: float
    total_weight: float
    status: ComparisonStatus
    reasons: tuple[str, ...] = ()

    @property
    def comparable(self) -> bool:
        return self.status is ComparisonStatus.COMPARABLE


def aggregate(
    weights: Mapping[str, float],
    cells: Sequence[ScoreCell],
    threshold: float = 0.8,
    *,
    forced_status: ComparisonStatus | None = None,
    extra_reasons: Sequence[str] = (),
) -> AggregateResult:
    """按给定权重口径聚合。

    forced_status：硬约束层面的强制状态（如"排除"），优先级高于覆盖率判断。
    """
    by_code = {c.indicator_code: c for c in cells}
    total_weight = sum(weights.values())
    covered_weight = 0.0
    score_weighted = 0.0
    valid_count = 0

    for code, w in weights.items():
        cell = by_code.get(code)
        if cell is None or not cell.is_valid:
            continue
        covered_weight += w
        score_weighted += float(cell.raw_score or 0) * w
        valid_count += 1

    count_cov = valid_count / len(by_code) if by_code else 0.0
    weight_cov = covered_weight / total_weight if total_weight > EPS else 0.0
    score = score_weighted / covered_weight if covered_weight > EPS else None

    if forced_status is not None:
        status = forced_status
    elif covered_weight <= EPS:
        status = ComparisonStatus.INSUFFICIENT
    elif weight_cov + 1e-12 < threshold:
        status = ComparisonStatus.INSUFFICIENT
    else:
        status = ComparisonStatus.COMPARABLE

    reasons: list[str] = list(extra_reasons)
    if status is ComparisonStatus.INSUFFICIENT and forced_status is None:
        reasons.append(
            f"有效权重覆盖率 {weight_cov:.4f} 低于门槛 {threshold:.4f}，输出「证据不足」"
        )
    return AggregateResult(
        weight_coverage=weight_cov,
        indicator_count_coverage=count_cov,
        weighted_score=None if status is not ComparisonStatus.COMPARABLE else score,
        valid_count=valid_count,
        total_count=len(by_code),
        covered_weight=covered_weight,
        total_weight=total_weight,
        status=status,
        reasons=tuple(reasons),
    )


@dataclass
class CoverageReport:
    """覆盖率全景（用于审计与展示）。"""

    indicator_count_coverage: float
    base_weight_coverage: float
    scenario_weight_coverage: dict[str, float] = field(default_factory=dict)
    threshold: float = 0.8
