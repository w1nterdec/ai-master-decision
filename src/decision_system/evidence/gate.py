"""证据评分闸门：判定一条（路径 × 指标）评分是否为"有效评分"。

严格闸门（默认）要求同时满足：
    1. 合法整数评分，且 1 ≤ score ≤ 5；
    2. source_id 非空；
    3. source_id 在来源登记表中**存在**；
    4. 来源核验状态为「已核验」（待核验 / 来源冲突 / 已失效 / 无法核验 一律拒绝）；
    5. 存在事实声明把该来源关联到**当前路径**；
    6. 存在事实声明表明该来源**支持当前指标**；
    7. 该事实声明本身已核验，且不是"候选证据映射"；
    8. 证据适用年份符合评价年份要求；
    9. 该来源不存在未解决的来源冲突。

任何一条不满足 -> 无效，不计入覆盖率。
空白（未评分）-> 未知，不计零分。

历史兼容闸门（LegacyPhase37CGate）仅做格式检查，用于与 Phase 3.7C Excel 做黄金比对，
**不得**用于生产决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from decision_system.models.enums import ClaimStatus, ScoreValidity, VerificationStatus


@dataclass(frozen=True)
class SourceView:
    source_id: str
    verification_status: VerificationStatus
    applicable_years: tuple[int, ...] = ()
    is_placeholder: bool = False


@dataclass(frozen=True)
class ClaimView:
    claim_id: int
    source_id: str
    status: ClaimStatus
    is_candidate: bool
    supports: bool
    applicable: bool
    path_key: str | None = None
    indicator_code: str | None = None
    applicable_years: tuple[int, ...] = ()


class EvidenceResolver(Protocol):
    def find_source(self, source_id: str) -> SourceView | None: ...
    def find_claims(
        self, source_id: str, path_key: str, indicator_code: str
    ) -> Sequence[ClaimView]: ...
    def has_unresolved_conflict(self, source_id: str) -> bool: ...


@dataclass(frozen=True)
class ScoreInput:
    indicator_code: str
    raw_score: object = None
    source_id: str | None = None
    path_key: str | None = None


@dataclass(frozen=True)
class ScoreValidation:
    indicator_code: str
    validity: ScoreValidity
    score: int | None = None
    reasons: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.validity is ScoreValidity.VALID


@dataclass
class GateConfig:
    score_min: int = 1
    score_max: int = 5
    require_year_match: bool = True
    year_window: int = 0  # 0 = 必须精确命中评价年份
    allow_candidate_claims: bool = False  # 候选映射永不允许进入正式评分


def _is_int(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    # 4.0 这类浮点视为整数；4.5 不是
    if isinstance(value, float):
        return float(value).is_integer()
    return False


class StrictEvidenceGate:
    """严格证据闸门（默认，生产使用）。"""

    def __init__(self, resolver: EvidenceResolver, config: GateConfig | None = None) -> None:
        self.resolver = resolver
        self.config = config or GateConfig()

    def validate(
        self, item: ScoreInput, *, evaluation_year: int | None = None
    ) -> ScoreValidation:
        cfg = self.config
        reasons: list[str] = []

        # 1) 空白 -> 未知
        if item.raw_score is None or (isinstance(item.raw_score, str) and not item.raw_score.strip()):
            return ScoreValidation(item.indicator_code, ScoreValidity.UNKNOWN, None, ("未评分：保持未知，不计零分",))
        if item.raw_score == "不适用" or item.raw_score == "NA":
            return ScoreValidation(item.indicator_code, ScoreValidity.UNKNOWN, None, ("标记为不适用：不计入评分",))

        # 2) 合法性
        if not _is_int(item.raw_score):
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, (f"评分非整数：{item.raw_score!r}",))
        score = int(item.raw_score)  # type: ignore[arg-type]
        if not (cfg.score_min <= score <= cfg.score_max):
            return ScoreValidation(
                item.indicator_code, ScoreValidity.INVALID, None,
                (f"评分超出 {cfg.score_min}-{cfg.score_max} 范围：{score}",),
            )

        # 3) source_id 非空
        if item.source_id is None or not str(item.source_id).strip():
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("来源ID为空",))

        source_id = str(item.source_id).strip()

        # 4) 来源存在
        source = self.resolver.find_source(source_id)
        if source is None:
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, (f"来源未登记：{source_id}",))

        # 5) 来源核验状态
        if source.verification_status is not VerificationStatus.VERIFIED:
            return ScoreValidation(
                item.indicator_code, ScoreValidity.INVALID, None,
                (f"来源核验状态为「{source.verification_status.value}」，不得进入正式评分",),
            )
        if source.is_placeholder:
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, (f"来源为占位登记：{source_id}",))

        # 6) 冲突
        if self.resolver.has_unresolved_conflict(source_id):
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("存在未解决来源冲突",))

        # 7) 与路径/指标的关联
        claims = list(self.resolver.find_claims(source_id, item.path_key or "", item.indicator_code))
        path_claims = [c for c in claims if c.applicable]
        if not path_claims:
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("来源不适用于当前路径",))
        indicator_claims = [c for c in path_claims if c.supports]
        if not indicator_claims:
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("来源不支持当前指标",))

        usable = []
        for c in indicator_claims:
            if c.is_candidate and not cfg.allow_candidate_claims:
                reasons.append(f"证据声明 #{c.claim_id} 为候选映射，不得自动升级为已核验")
                continue
            if c.status is not ClaimStatus.VERIFIED:
                reasons.append(f"证据声明 #{c.claim_id} 状态为「{c.status.value}」")
                continue
            if cfg.require_year_match and evaluation_year is not None:
                years = c.applicable_years or source.applicable_years
                if not self._year_ok(years, evaluation_year):
                    reasons.append(
                        f"证据适用年份 {list(years) if years else '未标注'} 不含评价年份 {evaluation_year}"
                    )
                    continue
            usable.append(c)

        if not usable:
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, tuple(reasons or ("无可用已核验证据声明",)))

        return ScoreValidation(item.indicator_code, ScoreValidity.VALID, score, ("证据核验通过",))

    def _year_ok(self, years: Sequence[int] | tuple[int, ...], evaluation_year: int) -> bool:
        if not years:
            return False
        lo = evaluation_year - self.config.year_window
        hi = evaluation_year + self.config.year_window
        return any(lo <= y <= hi for y in years)


class LegacyPhase37CGate:
    """Phase 3.7C Excel 口径闸门：**仅**检查 (评分∈{1..5}整数) AND (source_id 非空)。

    仅用于与 Excel 基线做黄金比对，复现其"格式有效"语义。生产决策禁止使用。
    """

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()

    def validate(self, item: ScoreInput, *, evaluation_year: int | None = None) -> ScoreValidation:
        cfg = self.config
        if item.raw_score is None or (isinstance(item.raw_score, str) and not item.raw_score.strip()):
            return ScoreValidation(item.indicator_code, ScoreValidity.UNKNOWN, None, ("未评分",))
        if not _is_int(item.raw_score):
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("评分非整数",))
        score = int(item.raw_score)  # type: ignore[arg-type]
        if not (cfg.score_min <= score <= cfg.score_max):
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("评分超出范围",))
        if item.source_id is None or not str(item.source_id).strip():
            return ScoreValidation(item.indicator_code, ScoreValidity.INVALID, None, ("来源ID为空",))
        return ScoreValidation(item.indicator_code, ScoreValidity.VALID, score, ("Phase3.7C 格式有效",))


@dataclass
class InMemoryEvidenceResolver:
    """测试/内存用解析器。"""

    sources: dict[str, SourceView] = field(default_factory=dict)
    claims: list[ClaimView] = field(default_factory=list)
    conflicts: set[str] = field(default_factory=set)

    def find_source(self, source_id: str) -> SourceView | None:
        return self.sources.get(source_id)

    def find_claims(
        self, source_id: str, path_key: str, indicator_code: str
    ) -> Sequence[ClaimView]:
        """返回该来源针对**当前路径**的声明；是否支持当前指标由 supports 标记表达。

        注意：来源"适用于路径"与"支持指标"是两级不同判断，
        必须分开表达，否则无法区分两种拒绝原因。
        """
        from dataclasses import replace

        out: list[ClaimView] = []
        for c in self.claims:
            if c.source_id != source_id:
                continue
            if c.path_key is not None and c.path_key != path_key:
                continue
            supports = bool(c.supports) and (c.indicator_code in (None, indicator_code))
            out.append(
                replace(c, supports=supports, path_key=path_key, indicator_code=indicator_code)
            )
        return out

    def has_unresolved_conflict(self, source_id: str) -> bool:
        return source_id in self.conflicts
