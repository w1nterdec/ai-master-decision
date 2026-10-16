"""证据治理相关的 Pydantic 模型（用于导入、API 与校验）。"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from pydantic import BaseModel, Field, field_validator

from decision_system.models.enums import (
    Accessibility,
    ClaimStatus,
    EvidenceLevel,
    SourceType,
    VerificationStatus,
)


class EvidenceSourceSchema(BaseModel):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str | None = None
    url_or_file: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    published_at: _dt.date | None = None
    applicable_years: list[int] = Field(default_factory=list)
    retrieved_at: _dt.datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verification_note: str | None = None
    is_placeholder: bool = False

    @field_validator("source_id")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("source_id 不得为空字符串")
        return v


class EvidenceClaimSchema(BaseModel):
    source_id: str
    statement: str
    topic: str | None = None
    stage: str | None = None
    school_code: str | None = None
    college_code: str | None = None
    program_code: str | None = None
    applicable_years: list[int] = Field(default_factory=list)
    evidence_level: EvidenceLevel = EvidenceLevel.UNKNOWN
    accessibility: Accessibility = Accessibility.NA
    status: ClaimStatus = ClaimStatus.CANDIDATE
    is_candidate: bool = True
    match_limitation: str | None = None
    path_keys: list[str] = Field(default_factory=list)
    indicator_codes: list[str] = Field(default_factory=list)
    raw_row: dict[str, Any] | None = None

    @field_validator("is_candidate")
    @classmethod
    def _candidate_consistency(cls, v: bool, info: Any) -> bool:
        return v


class ScoreInputSchema(BaseModel):
    indicator_code: str
    raw_score: int | None = None
    source_id: str | None = None
    path_key: str | None = None
