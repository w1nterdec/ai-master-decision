"""硬约束引擎。

输出状态：
    * 排除 —— 任一硬约束为「否」。
    * 历史候选 —— 全部硬约束为「是」；**不等于** 2028 正式招生资格。
    * 待核验 —— 存在「待确认」且无「否」。
    * 2028 正式资格已确认 —— 仅在 2028 核验状态为「已核验2028」、
      且存在支持该路径的已核验 2028 来源证据、且硬约束为候选时才成立。

任何尚未核验的 2028 招生信息，一律不得标记为已确认。
本模块为纯 Python，不依赖数据库。
"""

from __future__ import annotations

from dataclasses import dataclass

from decision_system.models.enums import (
    PathEligibility,
    Qualification2028,
    TriState,
    Verification2028,
)

HARD_CONSTRAINT_FIELDS = ("full_time_ok", "program_code_acceptable", "other_constraints_ok")


@dataclass(frozen=True)
class HardConstraintFacts:
    full_time_ok: TriState = TriState.UNKNOWN
    program_code_acceptable: TriState = TriState.UNKNOWN
    other_constraints_ok: TriState = TriState.UNKNOWN
    verification_2028: Verification2028 = Verification2028.UNKNOWN
    has_verified_2028_evidence: bool = False

    def values(self) -> tuple[TriState, TriState, TriState]:
        return (
            self.full_time_ok,
            self.program_code_acceptable,
            self.other_constraints_ok,
        )

    def missing_fields(self) -> list[str]:
        return [
            name
            for name, value in zip(HARD_CONSTRAINT_FIELDS, self.values())
            if value is TriState.UNKNOWN
        ]

    def rejected_fields(self) -> list[str]:
        return [
            name
            for name, value in zip(HARD_CONSTRAINT_FIELDS, self.values())
            if value is TriState.NO
        ]


@dataclass(frozen=True)
class ConstraintOutcome:
    eligibility: PathEligibility
    qualification_2028: Qualification2028
    reasons: tuple[str, ...] = ()

    @property
    def is_excluded(self) -> bool:
        return self.eligibility is PathEligibility.EXCLUDED

    @property
    def is_candidate(self) -> bool:
        return self.eligibility is PathEligibility.CANDIDATE

    @property
    def confirmed_2028(self) -> bool:
        return self.qualification_2028 is Qualification2028.CONFIRMED


def evaluate_hard_constraints(facts: HardConstraintFacts) -> ConstraintOutcome:
    reasons: list[str] = []
    rejected = facts.rejected_fields()
    missing = facts.missing_fields()

    if rejected:
        reasons.append("硬约束不符合：" + "、".join(rejected))
        eligibility = PathEligibility.EXCLUDED
    elif missing:
        reasons.append("硬约束待确认：" + "、".join(missing))
        eligibility = PathEligibility.PENDING
    else:
        reasons.append("全部硬约束为「是」：历史候选（非 2028 正式资格）")
        eligibility = PathEligibility.CANDIDATE

    if facts.verification_2028 is not Verification2028.VERIFIED:
        reasons.append(f"2028 核验状态为「{facts.verification_2028.value}」，不得标记已确认")
        qualification = Qualification2028.NOT_CONFIRMED
    elif not facts.has_verified_2028_evidence:
        reasons.append("缺少支持该路径的已核验 2028 来源证据，不得标记已确认")
        qualification = Qualification2028.NOT_CONFIRMED
    elif eligibility is not PathEligibility.CANDIDATE:
        reasons.append("硬约束未达候选，2028 资格未满足")
        qualification = Qualification2028.NOT_MET
    else:
        reasons.append("2028 已核验且存在已核验来源证据，硬约束为候选")
        qualification = Qualification2028.CONFIRMED

    return ConstraintOutcome(eligibility, qualification, tuple(reasons))


def forced_status_for(outcome: ConstraintOutcome):
    """硬约束对评分输出的强制状态（供 coverage.aggregate 使用）。"""
    from decision_system.models.enums import ComparisonStatus

    if outcome.eligibility is PathEligibility.EXCLUDED:
        return ComparisonStatus.EXCLUDED
    if outcome.eligibility is PathEligibility.PENDING:
        return ComparisonStatus.PENDING
    return None
