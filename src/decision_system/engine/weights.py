"""三级动态权重：一级 -> 二级 -> 三级。

规则（与 Phase 3.7C Excel「三级指标树」一致并可独立复算）：
    * 每一级在其**同级组内**归一化（组内权重之和 = 1）。
    * 三级全局权重 = 一级归一权重 × 二级组内归一权重 × 三级组内归一权重。
    * 全部三级全局权重合计 = 100%。
    * 拒绝负权重（抛出 NegativeWeightError）。
    * 组内权重合计为 0 时不做除法：该组全部成员权重为 0，并登记为"空组"（empty_groups），
      由调用方决定是否可用——**禁止**以 0/0 产生 NaN 或默认均分。

本模块为纯 Python，不依赖数据库与任何 UI 框架。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

EPS = 1e-12


class WeightError(ValueError):
    """权重配置错误（负权重、结构断裂等）。"""


class NegativeWeightError(WeightError):
    def __init__(self, code: str, value: float) -> None:
        super().__init__(f"指标 {code} 的权重为负数：{value}；负权重一律拒绝")
        self.code = code
        self.value = value


@dataclass(frozen=True)
class IndicatorNode:
    code: str
    name: str
    level: int
    parent_code: str | None = None
    raw_weight: float = 0.0
    sort_order: int = 0


@dataclass
class WeightTree:
    nodes: tuple[IndicatorNode, ...]
    empty_groups: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._by_code: dict[str, IndicatorNode] = {}
        for n in self.nodes:
            if n.code in self._by_code:
                raise WeightError(f"指标代码重复：{n.code}")
            if n.raw_weight < 0:
                raise NegativeWeightError(n.code, n.raw_weight)
            self._by_code[n.code] = n
        self._children: dict[str | None, list[str]] = {}
        for n in sorted(self.nodes, key=lambda x: (x.level, x.sort_order, x.code)):
            self._children.setdefault(n.parent_code, []).append(n.code)
        self._validate_structure()
        self._norm_cache: dict[str, float] = {}
        self.empty_groups = self._compute_empty_groups()

    # ---------- 结构 ----------
    def _validate_structure(self) -> None:
        for n in self.nodes:
            if n.level not in (1, 2, 3):
                raise WeightError(f"指标层级非法（必须为 1/2/3）：{n.code} -> {n.level}")
            if n.level == 1:
                if n.parent_code is not None:
                    raise WeightError(f"一级指标不应有父节点：{n.code}")
            else:
                if n.parent_code is None:
                    raise WeightError(f"{n.level} 级指标缺少父节点：{n.code}")
                parent = self._by_code.get(n.parent_code)
                if parent is None:
                    raise WeightError(f"指标 {n.code} 的父节点不存在：{n.parent_code}")
                if parent.level != n.level - 1:
                    raise WeightError(
                        f"指标 {n.code} 的父节点层级错误：{n.parent_code}(level={parent.level})"
                    )

    def _compute_empty_groups(self) -> list[str]:
        empty: list[str] = []
        for parent, members in self._children.items():
            total = sum(self._by_code[c].raw_weight for c in members)
            if total <= EPS:
                empty.append(parent if parent is not None else "<root>")
        return empty

    # ---------- 查询 ----------
    def node(self, code: str) -> IndicatorNode:
        try:
            return self._by_code[code]
        except KeyError as exc:  # pragma: no cover
            raise KeyError(f"指标不存在：{code}") from exc

    def children(self, parent_code: str | None) -> list[str]:
        return list(self._children.get(parent_code, []))

    def codes(self, level: int) -> list[str]:
        return [n.code for n in self.nodes if n.level == level]

    def parent_chain(self, code: str) -> list[str]:
        chain: list[str] = []
        cur = self._by_code[code]
        while cur.parent_code is not None:
            chain.append(cur.parent_code)
            cur = self._by_code[cur.parent_code]
        return chain

    def level1_of(self, code: str) -> str:
        chain = self.parent_chain(code)
        return chain[-1] if chain else code

    def contains(self, code: str) -> bool:
        return code in self._by_code

    # ---------- 归一化 ----------
    def group_total(self, parent_code: str | None) -> float:
        return sum(self._by_code[c].raw_weight for c in self._children.get(parent_code, []))

    def group_normalized(self, code: str) -> float:
        """同级组内归一权重。空组返回 0（不做除法）。"""
        if code in self._norm_cache:
            return self._norm_cache[code]
        parent = self._by_code[code].parent_code
        total = self.group_total(parent)
        value = 0.0 if total <= EPS else self._by_code[code].raw_weight / total
        self._norm_cache[code] = value
        return value

    def global_weight(self, code: str) -> float:
        """全局权重（0~1）。沿父链逐级相乘。"""
        value = self.group_normalized(code)
        cur = self._by_code[code]
        while cur.parent_code is not None:
            cur = self._by_code[cur.parent_code]
            value *= self.group_normalized(cur.code)
        return value

    def global_weights(self, level: int = 3) -> dict[str, float]:
        return {c: self.global_weight(c) for c in self.codes(level)}

    def total_global_weight(self, level: int = 3) -> float:
        return sum(self.global_weights(level).values())

    def group_weight_map(self, group_code: str) -> dict[str, float]:
        """返回指定一级分组下所有三级指标的全局权重。"""
        return {
            c: self.global_weight(c)
            for c in self.codes(3)
            if self.level1_of(c) == group_code
        }

    # ---------- 编辑 ----------
    def with_updated_weight(self, code: str, raw_weight: float) -> "WeightTree":
        """返回修改了某节点组内相对权重后的新树（原树不可变）。"""
        if raw_weight < 0:
            raise NegativeWeightError(code, raw_weight)
        new_nodes = tuple(
            IndicatorNode(
                code=n.code,
                name=n.name,
                level=n.level,
                parent_code=n.parent_code,
                raw_weight=raw_weight if n.code == code else n.raw_weight,
                sort_order=n.sort_order,
            )
            for n in self.nodes
        )
        return WeightTree(new_nodes)

    def validate(self) -> list[str]:
        """返回人类可读的校验信息（不抛异常）。"""
        issues: list[str] = []
        total = self.total_global_weight()
        if abs(total - 1.0) > 1e-9:
            issues.append(f"三级全局权重合计为 {total:.10f}，应为 1.0（100%）")
        for g in self.empty_groups:
            issues.append(f"分组 {g} 的组内权重合计为 0，该组全部指标权重按 0 处理")
        return issues


def build_tree_from_rows(rows: Sequence[Mapping[str, object]]) -> WeightTree:
    """从「三级指标树」形态的行数据构建权重树。

    每行需提供：一级 / 二级 / 三级指标 名称，以及一级权重、二级组内权重、三级组内权重。
    指标代码由引擎稳定生成（L1-<一级> / L2-<一级>|<二级> / L3-<一级>|<二级>|<三级>），
    保证跨版本稳定，便于黄金测试与权威威映射。
    """
    nodes: list[IndicatorNode] = []
    for idx, row in enumerate(rows):
        l1 = str(row["level1"]).strip()
        l2 = str(row["level2"]).strip()
        l3 = str(row["level3"]).strip()
        c1 = f"L1-{l1}"
        c2 = f"L2-{l1}|{l2}"
        c3 = f"L3-{l1}|{l2}|{l3}"
        nodes.append(IndicatorNode(c1, l1, 1, None, float(row["w1"]), idx))
        nodes.append(IndicatorNode(c2, l2, 2, c1, float(row["w2"]), idx))
        nodes.append(IndicatorNode(c3, l3, 3, c2, float(row["w3"]), idx))
    return _dedupe(nodes)


def _dedupe(nodes: Iterable[IndicatorNode]) -> WeightTree:
    seen: dict[str, IndicatorNode] = {}
    order: list[str] = []
    for n in nodes:
        if n.code not in seen:
            seen[n.code] = n
            order.append(n.code)
    return WeightTree(tuple(seen[c] for c in order))
