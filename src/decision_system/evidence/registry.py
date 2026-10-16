"""证据登记与冲突治理服务（Task B）。

关键约束：
    * 候选证据映射（is_candidate=True）**不会**自动升级为已核验证据；
      只有显式调用 `verify_claim()` 并给出核验人与依据时才可改变状态。
    * 来源冲突保留冲突记录，不覆盖旧事实；冲突未解决前该来源不得进入正式评分。
    * 所有写操作均写入 AuditLog。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy.orm import Session

from decision_system.models.entities import (
    AuditLog,
    ClaimConflict,
    ClaimIndicatorLink,
    ClaimPathLink,
    EvidenceClaim,
    EvidenceSource,
)
from decision_system.models.enums import ClaimStatus, VerificationStatus


class EvidenceGovernanceError(RuntimeError):
    pass


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _audit(
    session: Session, action: str, entity_type: str, entity_id: Any, detail: dict[str, Any], actor: str
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            detail=detail,
        )
    )


# ---------------------------------------------------------------------------
# 来源
# ---------------------------------------------------------------------------
def register_source(
    session: Session,
    *,
    source_id: str,
    title: str,
    publisher: str | None = None,
    url_or_file: str | None = None,
    source_type: Any = None,
    published_at: _dt.date | None = None,
    applicable_years: list[int] | None = None,
    retrieved_at: _dt.datetime | None = None,
    verification_status: VerificationStatus = VerificationStatus.PENDING,
    verification_note: str | None = None,
    is_placeholder: bool = False,
    actor: str = "system",
) -> EvidenceSource:
    """登记（幂等）来源。已存在则只更新"补充性"字段，不静默提升核验状态。"""
    existing = (
        session.query(EvidenceSource).filter(EvidenceSource.source_id == source_id).one_or_none()
    )
    if existing is not None:
        _audit(session, "source.register.skip", "EvidenceSource", source_id, {"reason": "已存在"}, actor)
        return existing

    src = EvidenceSource(
        source_id=source_id,
        title=title,
        publisher=publisher,
        url_or_file=url_or_file,
        source_type=source_type,
        published_at=published_at,
        applicable_years=applicable_years,
        retrieved_at=retrieved_at or _now(),
        verification_status=verification_status,
        verification_note=verification_note,
        is_placeholder=is_placeholder,
    )
    session.add(src)
    session.flush()
    _audit(
        session,
        "source.register",
        "EvidenceSource",
        source_id,
        {"verification_status": str(verification_status), "title": title},
        actor,
    )
    return src


def set_source_status(
    session: Session,
    source_id: str,
    status: VerificationStatus,
    *,
    note: str | None = None,
    actor: str = "system",
) -> EvidenceSource:
    src = (
        session.query(EvidenceSource).filter(EvidenceSource.source_id == source_id).one_or_none()
    )
    if src is None:
        raise EvidenceGovernanceError(f"来源不存在：{source_id}")
    before = src.verification_status
    src.verification_status = status
    src.verification_note = note
    _audit(
        session,
        "source.status",
        "EvidenceSource",
        source_id,
        {"from": str(before), "to": str(status), "note": note},
        actor,
    )
    return src


# ---------------------------------------------------------------------------
# 事实声明
# ---------------------------------------------------------------------------
def register_claim(
    session: Session,
    *,
    source_id: str,
    statement: str,
    source_ref_id: str | None = None,
    topic: str | None = None,
    stage: str | None = None,
    school_code: str | None = None,
    college_code: str | None = None,
    program_code: str | None = None,
    applicable_years: list[int] | None = None,
    evidence_level: Any = None,
    accessibility: Any = None,
    status: ClaimStatus = ClaimStatus.CANDIDATE,
    is_candidate: bool = True,
    match_limitation: str | None = None,
    raw_row: dict[str, Any] | None = None,
    actor: str = "system",
) -> EvidenceClaim:
    """登记一条事实声明。默认状态为"候选映射"，永不自动升级。"""
    src = (
        session.query(EvidenceSource).filter(EvidenceSource.source_id == source_id).one_or_none()
    )
    if src is None:
        raise EvidenceGovernanceError(f"来源未登记，无法登记事实声明：{source_id}")

    claim = EvidenceClaim(
        source_id_fk=src.id,
        source_ref_id=source_ref_id or source_id,
        statement=statement,
        topic=topic,
        stage=stage,
        school_code=school_code,
        college_code=college_code,
        program_code=program_code,
        applicable_years=applicable_years,
        evidence_level=evidence_level,
        accessibility=accessibility,
        status=status,
        is_candidate=is_candidate,
        match_limitation=match_limitation,
        raw_row=raw_row,
    )
    session.add(claim)
    session.flush()
    _audit(
        session,
        "claim.register",
        "EvidenceClaim",
        claim.id,
        {"source_id": source_id, "status": str(status), "is_candidate": is_candidate},
        actor,
    )
    return claim


def verify_claim(
    session: Session,
    claim_id: int,
    *,
    actor: str,
    basis: str,
    applicable_years: list[int] | None = None,
) -> EvidenceClaim:
    """人工核验一条事实声明（唯一合法的升级路径）。必须提供核验人与依据。"""
    if not actor or not basis:
        raise EvidenceGovernanceError("核验必须提供 actor 与 basis")
    claim = session.get(EvidenceClaim, claim_id)
    if claim is None:
        raise EvidenceGovernanceError(f"事实声明不存在：{claim_id}")
    before = claim.status
    claim.status = ClaimStatus.VERIFIED
    claim.is_candidate = False
    if applicable_years is not None:
        claim.applicable_years = applicable_years
    _audit(
        session,
        "claim.verify",
        "EvidenceClaim",
        claim_id,
        {"from": str(before), "to": str(ClaimStatus.VERIFIED), "actor": actor, "basis": basis},
        actor,
    )
    return claim


def reject_auto_promotion(claim: EvidenceClaim) -> None:
    """显式表达：候选映射不得自动升级。任何自动化流程都应先调用此方法自检。"""
    if claim.is_candidate and claim.status is ClaimStatus.VERIFIED:
        raise EvidenceGovernanceError(
            f"事实声明 #{claim.id} 同时为候选映射且标记为已核验，属于非法自动升级"
        )


def link_claim_path(
    session: Session, claim_id: int, path_id: int, *, applicable: bool = True, actor: str = "system"
) -> ClaimPathLink:
    existing = (
        session.query(ClaimPathLink)
        .filter(ClaimPathLink.claim_id == claim_id, ClaimPathLink.path_id == path_id)
        .one_or_none()
    )
    if existing is not None:
        return existing
    link = ClaimPathLink(claim_id=claim_id, path_id=path_id, applicable=applicable)
    session.add(link)
    session.flush()
    _audit(session, "claim.link_path", "ClaimPathLink", link.id, {"claim_id": claim_id, "path_id": path_id}, actor)
    return link


def link_claim_indicator(
    session: Session,
    claim_id: int,
    indicator_id: int,
    *,
    supports: bool = True,
    actor: str = "system",
) -> ClaimIndicatorLink:
    existing = (
        session.query(ClaimIndicatorLink)
        .filter(
            ClaimIndicatorLink.claim_id == claim_id,
            ClaimIndicatorLink.indicator_id == indicator_id,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    link = ClaimIndicatorLink(claim_id=claim_id, indicator_id=indicator_id, supports=supports)
    session.add(link)
    session.flush()
    _audit(
        session, "claim.link_indicator", "ClaimIndicatorLink", link.id,
        {"claim_id": claim_id, "indicator_id": indicator_id}, actor,
    )
    return link


# ---------------------------------------------------------------------------
# 冲突
# ---------------------------------------------------------------------------
def detect_and_record_conflict(
    session: Session,
    *,
    new_claim_id: int,
    existing_claim_id: int | None,
    description: str,
    actor: str = "system",
) -> ClaimConflict:
    """记录来源冲突。

    **不**修改既有事实声明的内容或状态（除非显式标记），也**不**自动合并。
    """
    conflict = ClaimConflict(
        claim_id=new_claim_id,
        conflicting_claim_id=existing_claim_id,
        description=description,
        resolved=False,
    )
    session.add(conflict)
    session.flush()

    new_claim = session.get(EvidenceClaim, new_claim_id)
    if new_claim is not None:
        new_claim.status = ClaimStatus.CONFLICT
        new_claim.is_candidate = True
    _audit(
        session, "claim.conflict", "ClaimConflict", conflict.id,
        {"new_claim_id": new_claim_id, "existing_claim_id": existing_claim_id,
         "description": description}, actor,
    )
    return conflict


def resolve_conflict(
    session: Session, conflict_id: int, *, resolution_note: str, actor: str
) -> ClaimConflict:
    conflict = session.get(ClaimConflict, conflict_id)
    if conflict is None:
        raise EvidenceGovernanceError(f"冲突记录不存在：{conflict_id}")
    conflict.resolved = True
    conflict.resolution_note = resolution_note
    _audit(session, "claim.conflict.resolve", "ClaimConflict", conflict_id,
           {"note": resolution_note}, actor)
    return conflict


def unresolved_conflict_source_ids(session: Session) -> set[str]:
    rows = (
        session.query(EvidenceClaim.source_ref_id)
        .join(ClaimConflict, ClaimConflict.claim_id == EvidenceClaim.id)
        .filter(ClaimConflict.resolved.is_(False))
        .all()
    )
    return {r[0] for r in rows}
