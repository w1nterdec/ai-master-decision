"""情景权重：职业优先 / 报考优先 / 科研优先。

规则（与 Phase 3.7C「3_2情景权重」一致）：
    * 情景权重 = 基础全局权重 × 情景倍率，然后**独立归一化**（该情景内合计 100%）。
    * 每个情景使用**自身**的覆盖率判断是否输出评分；
      禁止因基础情景覆盖率达标就允许其它情景输出。
    * 倍率为情景假设，不代表事实；默认情景标记为演示配置（is_demo=True）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from decision_system.engine.weights import EPS, WeightError, WeightTree

# Phase 3.7C Excel 中的默认倍率（按一级指标分组）。
# 注意：这些数值来自 Phase 3.x 演示配置，不是用户最终偏好。
DEFAULT_SCENARIO_MULTIPLIERS: dict[str, dict[str, float]] = {
    "career": {"职业发展": 1.6, "报考可行性": 0.8, "研究培养": 1.0, "地域生态": 1.0, "成本安排": 0.9},
    "admission": {"职业发展": 0.8, "报考可行性": 1.8, "研究培养": 0.9, "地域生态": 0.9, "成本安排": 1.0},
    "research": {"职业发展": 0.9, "报考可行性": 0.8, "研究培养": 1.9, "地域生态": 0.9, "成本安排": 0.9},
}

DEFAULT_SCENARIO_NAMES = {
    "career": "职业发展优先",
    "admission": "报考可行性优先",
    "research": "科研培养优先",
}


@dataclass(frozen=True)
class ScenarioDef:
    code: str
    name: str
    multipliers: Mapping[str, float] = field(default_factory=dict)
    is_demo: bool = True
    description: str = "倍率为情景假设，不代表事实"


def default_scenarios() -> dict[str, ScenarioDef]:
    return {
        code: ScenarioDef(
            code=code,
            name=DEFAULT_SCENARIO_NAMES[code],
            multipliers=dict(mults),
            is_demo=True,
        )
        for code, mults in DEFAULT_SCENARIO_MULTIPLIERS.items()
    }


def resolve_multiplier(scenario: ScenarioDef, tree: WeightTree, code: str) -> float:
    """取指标倍率：优先三级指标代码直配，其次一级分组倍率，缺省 1.0。"""
    if code in scenario.multipliers:
        return float(scenario.multipliers[code])
    l1 = tree.level1_of(code)
    if l1 in scenario.multipliers:
        return float(scenario.multipliers[l1])
    l1_name = tree.node(l1).name
    if l1_name in scenario.multipliers:
        return float(scenario.multipliers[l1_name])
    return 1.0


def scenario_weights(tree: WeightTree, scenario: ScenarioDef, level: int = 3) -> dict[str, float]:
    """返回该情景下归一化后的指标权重。"""
    for target, m in scenario.multipliers.items():
        if m < 0:
            raise WeightError(f"情景 {scenario.code} 中 {target} 的倍率为负数：{m}")
    raw: dict[str, float] = {}
    for code in tree.codes(level):
        base = tree.global_weight(code)
        raw[code] = base * resolve_multiplier(scenario, tree, code)
    total = sum(raw.values())
    if total <= EPS:
        # 防止除零：全部为 0，交由覆盖率逻辑判定为"证据不足"
        return {c: 0.0 for c in raw}
    return {c: v / total for c, v in raw.items()}
