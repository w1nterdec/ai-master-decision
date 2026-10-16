"""Phase 4.0 数据模型（ORM 实体）。

实体清单（对应需求 Task A）：
    School / College / Program / AdmissionPath / AdmissionYear / AdmissionRecord
    ResearchResource / Mentor / EvidenceSource / EvidenceClaim / Indicator
    WeightProfile / Scenario / ScoreRecord / DecisionResult / AuditLog

补充关联与治理实体：
    ClaimPathLink / ClaimIndicatorLink / ClaimConflict / WeightNode /
    ScenarioMultiplier / HardConstraintEvaluation / ImportBatch

重要设计取舍见 docs/architecture.md；核心要点：
    * AdmissionPath 的唯一性由 path_key（学校+学院码+专业码+学习方式+方向+年份+招生方式+路径角色）
      决定，**不**使用 "学校名称 + 专业代码"。
    * 不同年份 / 不同学院 / 一志愿与调剂，均生成独立 AdmissionPath 行，互不覆盖。
"""

from __future__ import annotations

import datetime as _dt
import enum as _enum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decision_system.models.base import Base, TimestampMixin
from decision_system.models.enums import (
    Accessibility,
    AdmissionMethod,
    ClaimStatus,
    EvidenceLevel,
    PathKind,
    PathEligibility,
    Qualification2028,
    ScoreValidity,
    SourceType,
    StudyMode,
    TriState,
    Verification2028,
    VerificationStatus,
)


def enum_col(enum_cls: Any, **kwargs: Any) -> Any:
    """简写：把 str-Enum 以中文 value 落库。"""
    from decision_system.models.base import StrEnumType

    kwargs.setdefault("nullable", False)
    return mapped_column(StrEnumType(enum_cls), **kwargs)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 组织维度
# ---------------------------------------------------------------------------
class School(Base, TimestampMixin):
    __tablename__ = "school"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64))
    province: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(64))  # 华东/华北/西南/东北...
    note: Mapped[str | None] = mapped_column(Text)

    colleges: Mapped[list["College"]] = relationship(back_populates="school")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<School {self.code} {self.name}>"


class College(Base, TimestampMixin):
    __tablename__ = "college"
    __table_args__ = (UniqueConstraint("school_id", "college_code", name="uq_college"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"))
    college_code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(128))
    campus: Mapped[str | None] = mapped_column(String(128))

    school: Mapped["School"] = relationship(back_populates="colleges")
    programs: Mapped[list["Program"]] = relationship(back_populates="college")


class Program(Base, TimestampMixin):
    """专业（目录条目）。同一专业代码可在多个学院存在，故唯一键含 college_id。"""

    __tablename__ = "program"
    __table_args__ = (UniqueConstraint("college_id", "program_code", name="uq_program"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("college.id"))
    program_code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(128))
    degree_type: Mapped[str | None] = mapped_column(String(32))  # 专硕/学硕

    college: Mapped["College"] = relationship(back_populates="programs")
    paths: Mapped[list["AdmissionPath"]] = relationship(back_populates="program")


# ---------------------------------------------------------------------------
# 招生路径
# ---------------------------------------------------------------------------
class AdmissionYear(Base, TimestampMixin):
    """招生年度维度。历史年度数据只代表该年度，不得推断为 2028 正式情况。"""

    __tablename__ = "admission_year"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, unique=True)
    catalog_published: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)


class AdmissionPath(Base, TimestampMixin):
    """一条可决策的招生路径。

    path_key = 学校码|学院码|专业码|学习方式|方向|年份|招生方式|路径角色
    """

    __tablename__ = "admission_path"
    __table_args__ = (
        UniqueConstraint("path_key", name="uq_path_key"),
        Index("ix_path_school_year", "school_id", "admission_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    path_key: Mapped[str] = mapped_column(String(255))
    legacy_path_id: Mapped[str | None] = mapped_column(String(32))  # Excel 中的 P01..P10

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id"))
    college_id: Mapped[int] = mapped_column(ForeignKey("college.id"))
    program_id: Mapped[int] = mapped_column(ForeignKey("program.id"))
    admission_year: Mapped[int] = mapped_column(Integer)

    study_mode: Mapped[StudyMode] = enum_col(StudyMode, default=StudyMode.UNKNOWN)
    admission_method: Mapped[AdmissionMethod] = enum_col(
        AdmissionMethod, default=AdmissionMethod.UNKNOWN
    )
    path_kind: Mapped[PathKind] = enum_col(PathKind, default=PathKind.FIRST_CHOICE)
    direction: Mapped[str | None] = mapped_column(String(128))
    exam_unit4: Mapped[str | None] = mapped_column(String(128))  # 初试第四单元
    training_location: Mapped[str | None] = mapped_column(String(128))

    # 硬约束事实（三态：是/否/待确认）
    full_time_ok: Mapped[TriState] = enum_col(TriState, default=TriState.UNKNOWN)
    program_code_acceptable: Mapped[TriState] = enum_col(TriState, default=TriState.UNKNOWN)
    other_constraints_ok: Mapped[TriState] = enum_col(TriState, default=TriState.UNKNOWN)

    verification_2028: Mapped[Verification2028] = enum_col(
        Verification2028, default=Verification2028.UNKNOWN
    )
    key_risk: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    school: Mapped["School"] = relationship()
    college: Mapped["College"] = relationship()
    program: Mapped["Program"] = relationship(back_populates="paths")
    records: Mapped[list["AdmissionRecord"]] = relationship(back_populates="path")
    score_records: Mapped[list["ScoreRecord"]] = relationship(back_populates="path")

    def compute_path_key(self) -> str:
        raise NotImplementedError  # 由 services.path_identity 统一生成，避免多处实现漂移


class AdmissionRecord(Base, TimestampMixin):
    """招生计划 / 实际录取记录。计划人数与实际录取人数分离；统考/推免/专项分开。"""

    __tablename__ = "admission_record"
    __table_args__ = (
        UniqueConstraint(
            "path_id", "year", "admission_method", "quota_basis", name="uq_admission_record"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    path_id: Mapped[int] = mapped_column(ForeignKey("admission_path.id"))
    year: Mapped[int] = mapped_column(Integer)
    admission_method: Mapped[AdmissionMethod] = enum_col(AdmissionMethod)
    quota_basis: Mapped[str] = mapped_column(String(64))  # 目录计划 / 复试统考计划 / 实际录取
    planned_quota: Mapped[int | None] = mapped_column(Integer)
    actual_admitted: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    evidence_claim_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_claim.id"))

    path: Mapped["AdmissionPath"] = relationship(back_populates="records")


# ---------------------------------------------------------------------------
# 科研资源 / 导师
# ---------------------------------------------------------------------------
class ResearchResource(Base, TimestampMixin):
    __tablename__ = "research_resource"

    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("college.id"))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(128))
    accessibility: Mapped[Accessibility] = enum_col(Accessibility, default=Accessibility.NA)
    statement: Mapped[str | None] = mapped_column(Text)
    evidence_claim_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_claim.id"))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.PENDING
    )


class Mentor(Base, TimestampMixin):
    __tablename__ = "mentor"

    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("college.id"))
    name: Mapped[str] = mapped_column(String(64))
    research_direction: Mapped[str | None] = mapped_column(Text)
    evidence_claim_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_claim.id"))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.PENDING
    )


class ResourcePathLink(Base, TimestampMixin):
    """研究资源 <-> 招生路径 的证据化关联（Task A.9）。"""

    __tablename__ = "resource_path_link"
    __table_args__ = (
        UniqueConstraint("resource_id", "path_id", "claim_id", name="uq_resource_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("research_resource.id"))
    path_id: Mapped[int] = mapped_column(ForeignKey("admission_path.id"))
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_claim.id"))
    accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 证据治理
# ---------------------------------------------------------------------------
class EvidenceSource(Base, TimestampMixin):
    """来源登记。只有 verification_status=已核验 的来源可用于正式评分。"""

    __tablename__ = "evidence_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), unique=True)
    title: Mapped[str] = mapped_column(String(512))
    publisher: Mapped[str | None] = mapped_column(String(255))  # 来源机构
    url_or_file: Mapped[str | None] = mapped_column(Text)  # URL 或文件标识
    source_type: Mapped[SourceType] = enum_col(SourceType, default=SourceType.UNKNOWN)
    published_at: Mapped[_dt.date | None] = mapped_column(Date)  # 发布时间
    applicable_years: Mapped[list[int] | None] = mapped_column(JSON)  # 适用年份
    retrieved_at: Mapped[_dt.datetime | None] = mapped_column(DateTime)
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus, default=VerificationStatus.PENDING
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=False)

    claims: Mapped[list["EvidenceClaim"]] = relationship(back_populates="source")


class EvidenceClaim(Base, TimestampMixin):
    """一条事实声明：来源 -> 支持的（路径 / 指标）事实。

    is_candidate=True 表示"候选证据映射"，**永不**自动升级为已核验证据。
    """

    __tablename__ = "evidence_claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id_fk: Mapped[int] = mapped_column(ForeignKey("evidence_source.id"))
    source_ref_id: Mapped[str] = mapped_column(String(128))  # 冗余保留原始 source_id 字符串
    statement: Mapped[str] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(128))
    stage: Mapped[str | None] = mapped_column(String(64))

    school_code: Mapped[str | None] = mapped_column(String(64))
    college_code: Mapped[str | None] = mapped_column(String(32))
    program_code: Mapped[str | None] = mapped_column(String(32))
    applicable_years: Mapped[list[int] | None] = mapped_column(JSON)

    evidence_level: Mapped[EvidenceLevel] = enum_col(EvidenceLevel, default=EvidenceLevel.UNKNOWN)
    accessibility: Mapped[Accessibility] = enum_col(Accessibility, default=Accessibility.NA)
    status: Mapped[ClaimStatus] = enum_col(ClaimStatus, default=ClaimStatus.CANDIDATE)
    is_candidate: Mapped[bool] = mapped_column(Boolean, default=True)
    match_limitation: Mapped[str | None] = mapped_column(Text)
    raw_row: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    source: Mapped["EvidenceSource"] = relationship(back_populates="claims")
    indicator_links: Mapped[list["ClaimIndicatorLink"]] = relationship(back_populates="claim")
    path_links: Mapped[list["ClaimPathLink"]] = relationship(back_populates="claim")


class ClaimPathLink(Base, TimestampMixin):
    __tablename__ = "claim_path_link"
    __table_args__ = (UniqueConstraint("claim_id", "path_id", name="uq_claim_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("evidence_claim.id"))
    path_id: Mapped[int] = mapped_column(ForeignKey("admission_path.id"))
    applicable: Mapped[bool] = mapped_column(Boolean, default=True)

    claim: Mapped["EvidenceClaim"] = relationship(back_populates="path_links")
    path: Mapped["AdmissionPath"] = relationship()


class ClaimIndicatorLink(Base, TimestampMixin):
    __tablename__ = "claim_indicator_link"
    __table_args__ = (UniqueConstraint("claim_id", "indicator_id", name="uq_claim_indicator"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("evidence_claim.id"))
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator.id"))
    supports: Mapped[bool] = mapped_column(Boolean, default=True)

    claim: Mapped["EvidenceClaim"] = relationship(back_populates="indicator_links")


class ClaimConflict(Base, TimestampMixin):
    """来源冲突登记。冲突保留记录，**不**自动覆盖旧事实。"""

    __tablename__ = "claim_conflict"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("evidence_claim.id"))
    conflicting_claim_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_claim.id"))
    description: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 指标与权重
# ---------------------------------------------------------------------------
class Indicator(Base, TimestampMixin):
    __tablename__ = "indicator"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    level: Mapped[int] = mapped_column(Integer)  # 1 / 2 / 3
    name: Mapped[str] = mapped_column(String(128))
    parent_code: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    scoring_anchor: Mapped[str | None] = mapped_column(Text)


class WeightProfile(Base, TimestampMixin):
    """权重配置。is_demo=True 表示这是演示配置，**不得**冒充用户最终偏好。"""

    __tablename__ = "weight_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)
    nodes: Mapped[list["WeightNode"]] = relationship(back_populates="profile")


class WeightNode(Base, TimestampMixin):
    __tablename__ = "weight_node"
    __table_args__ = (UniqueConstraint("profile_id", "indicator_id", name="uq_weight_node"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("weight_profile.id"))
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator.id"))
    level: Mapped[int] = mapped_column(Integer)
    raw_weight: Mapped[float] = mapped_column(Float)  # 组内相对权重（可为百分比）

    profile: Mapped["WeightProfile"] = relationship(back_populates="nodes")
    indicator: Mapped["Indicator"] = relationship()


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenario"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)
    multipliers: Mapped[list["ScenarioMultiplier"]] = relationship(back_populates="scenario")


class ScenarioMultiplier(Base, TimestampMixin):
    __tablename__ = "scenario_multiplier"
    __table_args__ = (UniqueConstraint("scenario_id", "target_code", name="uq_scenario_mult"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenario.id"))
    target_code: Mapped[str] = mapped_column(String(64))  # 一级或三级指标代码
    multiplier: Mapped[float] = mapped_column(Float)

    scenario: Mapped["Scenario"] = relationship(back_populates="multipliers")


# ---------------------------------------------------------------------------
# 评分与结果
# ---------------------------------------------------------------------------
class ScoreRecord(Base, TimestampMixin):
    """单条（路径 × 指标）评分。raw_score 为 None 表示未知，**不得**视为 0 分。"""

    __tablename__ = "score_record"
    __table_args__ = (
        UniqueConstraint("path_id", "indicator_id", "evaluation_year", name="uq_score_record"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    path_id: Mapped[int] = mapped_column(ForeignKey("admission_path.id"))
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator.id"))
    evaluation_year: Mapped[int] = mapped_column(Integer)

    raw_score: Mapped[int | None] = mapped_column(Integer)
    source_ref_id: Mapped[str | None] = mapped_column(String(128))
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_claim.id"))
    fact_type: Mapped[str | None] = mapped_column(String(32))  # 事实/推断/未知
    validity: Mapped[ScoreValidity] = enum_col(ScoreValidity, default=ScoreValidity.UNKNOWN)
    rejection_reasons: Mapped[list[str] | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)

    path: Mapped["AdmissionPath"] = relationship(back_populates="score_records")
    indicator: Mapped["Indicator"] = relationship()


class HardConstraintEvaluation(Base, TimestampMixin):
    __tablename__ = "hard_constraint_evaluation"

    id: Mapped[int] = mapped_column(primary_key=True)
    path_id: Mapped[int] = mapped_column(ForeignKey("admission_path.id"))
    evaluated_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_utcnow)
    eligibility: Mapped[PathEligibility] = enum_col(PathEligibility)
    qualification_2028: Mapped[Qualification2028] = enum_col(Qualification2028)
    reasons: Mapped[list[str] | None] = mapped_column(JSON)


class DecisionResult(Base, TimestampMixin):
    """一次决策计算的输出快照。不含任何录取概率字段。"""

    __tablename__ = "decision_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    path_id: Mapped[int] = mapped_column(ForeignKey("admission_path.id"))
    profile_code: Mapped[str] = mapped_column(String(64))
    evaluation_year: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_utcnow, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ImportBatch(Base):
    """导入批次，用于幂等控制与导入报告留痕。"""

    __tablename__ = "import_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_key: Mapped[str] = mapped_column(String(128), unique=True)
    source_file: Mapped[str] = mapped_column(String(512))
    file_sha256: Mapped[str] = mapped_column(String(128))
    imported_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now()
    )
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
