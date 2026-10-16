"""决策输入/输出相关的 Pydantic 模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from decision_system.models.enums import (
    AdmissionMethod,
    PathKind,
    PathEligibility,
    Qualification2028,
    StudyMode,
    TriState,
    Verification2028,
)


class IndicatorWeightRow(BaseModel):
    level1: str
    level2: str
    level3: str
    w1: float
    w2: float
    w3: float


class HardConstraintSchema(BaseModel):
    full_time_ok: TriState = TriState.UNKNOWN
    program_code_acceptable: TriState = TriState.UNKNOWN
    other_constraints_ok: TriState = TriState.UNKNOWN
    verification_2028: Verification2028 = Verification2028.UNKNOWN
    has_verified_2028_evidence: bool = False


class AdmissionPathSchema(BaseModel):
    path_key: str
    legacy_path_id: str | None = None
    school_code: str
    school_name: str
    college_code: str
    program_code: str
    program_name: str | None = None
    admission_year: int
    study_mode: StudyMode = StudyMode.UNKNOWN
    admission_method: AdmissionMethod = AdmissionMethod.UNIFIED_EXAM
    path_kind: PathKind = PathKind.FIRST_CHOICE
    direction: str | None = None
    exam_unit4: str | None = None
    training_location: str | None = None
    hard_constraints: HardConstraintSchema = Field(default_factory=HardConstraintSchema)
    key_risk: str | None = None


class DecisionSummary(BaseModel):
    """供 UI / 报告消费的精简输出。**不含录取概率字段**。"""

    path_key: str
    label: str
    eligibility: PathEligibility
    qualification_2028: Qualification2028
    base_score: float | None
    base_status: str
    base_weight_coverage: float
    scenario_scores: dict[str, float | None] = Field(default_factory=dict)
    scenario_status: dict[str, str] = Field(default_factory=dict)
    objective_a_status: str
    objective_a_score: float | None
    objective_b_status: str
    objective_b_score: float | None
    limitations: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
