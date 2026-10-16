"""证据治理工作台服务层（Phase 4.1 Task C）。

本模块是 Streamlit 页面与 Phase 4.0 治理逻辑之间**唯一**的写操作通道：
页面不得直接改 ORM 字段绕过治理规则，所有变更必须经此处的函数，
以便统一落审计、统一校验、并可被 pytest 直接测试。

口径定义（Phase 4.0 遗留的"84 条全部未登记 / 83 条缺本体"歧义在此收敛）：
    * 来源记录总数      = evidence_source 表的行数（含占位符与引用式记录）
    * 占位符记录        = is_placeholder=True，或标题属于占位模板（"（占位）…" / "（引用自…）…"），
                          或同时缺失 url_or_file 与 publisher
    * 已登记来源        = 非占位符 **且** 具备可核验本体（url_or_file 或 publisher 非空）
    * 已核验来源        = verification_status == 已核验（**且**必须已登记本体，否则判为非法态）
    * 待核验数          = 事实声明中状态属于 {候选映射, 待核验, 来源冲突} 的条数
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from decision_system.evidence.registry import (
    EvidenceGovernanceError,
    _audit,  # noqa: PLC2701 - 复用同一审计写入实现，保证审计口径一致
    detect_and_record_conflict,
    register_claim,
    register_source,
    set_source_status,
    verify_claim,
)
from decision_system.models.entities import (
    AdmissionPath,
    AuditLog,
    ClaimConflict,
    ClaimIndicatorLink,
    ClaimPathLink,
    EvidenceClaim,
    EvidenceSource,
    Indicator,
)
from decision_system.models.enums import (
    ClaimStatus,
    SourceType,
    VerificationStatus,
)

PLACEHOLDER_TITLE_PREFIXES = ("（占位）", "（引用自")

_PENDING_CLAIM_STATUSES = (
    ClaimStatus.CANDIDATE,
    ClaimStatus.PENDING,
    ClaimStatus.CONFLICT,
)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 口径判定（可被测试直接断言）
# ---------------------------------------------------------------------------
def is_placeholder_record(src: EvidenceSource) -> bool:
    """是否为占位符 / 引用式记录（无本体，不可用于评分）。"""
    if bool(src.is_placeholder):
        return True
    title = (src.title or "").strip()
    if title.startswith(PLACEHOLDER_TITLE_PREFIXES):
        return True
    return not (src.url_or_file or src.publisher)


def is_registered_source(src: EvidenceSource) -> bool:
    """是否已完成本体登记（具备可核验的 URL/文件标识或发布机构）。"""
    return (not is_placeholder_record(src)) and bool(src.url_or_file or src.publisher)


def is_verified_source(src: EvidenceSource) -> bool:
    """是否已核验。未登记本体的来源即便状态为已核验，也视为非法态（返回 False）。"""
    return src.verification_status is VerificationStatus.VERIFIED and is_registered_source(src)


# ---------------------------------------------------------------------------
# C1 来源登记
# ---------------------------------------------------------------------------
def register_source_strict(
    session: Session,
    *,
    source_id: str,
    title: str,
    publisher: str | None = None,
    url_or_file: str | None = None,
    source_type: SourceType | str | None = None,
    published_year: int | None = None,
    applicable_years: list[int] | None = None,
    verification_status: VerificationStatus = VerificationStatus.PENDING,
    verification_note: str | None = None,
    is_placeholder: bool = False,
    actor: str = "user",
) -> EvidenceSource:
    """登记来源（严格版）：source_id 重复直接拒绝；登记后一律为「已登记但未核验」。

    与 registry.register_source 的差别：后者为导入器幂等 upsert（重复即跳过），
    本函数为人工登记入口，重复必须报错，避免误覆盖既有来源。
    """
    source_id = (source_id or "").strip()
    if not source_id:
        raise EvidenceGovernanceError("source_id 不能为空")
    if source_id.upper() == "SRC-NA":
        raise EvidenceGovernanceError("SRC-NA 为系统占位 ID，不得用于登记真实来源")
    exists = session.execute(
        select(EvidenceSource).where(EvidenceSource.source_id == source_id)
    ).scalar_one_or_none()
    if exists is not None:
        raise EvidenceGovernanceError(f"source_id 已存在，拒绝重复登记：{source_id}")

    title = (title or "").strip()
    if not title:
        raise EvidenceGovernanceError("来源标题不能为空")
    if not is_placeholder and not (url_or_file or publisher):
        raise EvidenceGovernanceError("登记真实来源必须提供 URL/文件标识 或 发布机构")

    published_at = _dt.date(published_year, 1, 1) if published_year else None
    src = register_source(
        session,
        source_id=source_id,
        title=title,
        publisher=publisher,
        url_or_file=url_or_file,
        source_type=source_type or SourceType.UNKNOWN,
        published_at=published_at,
        applicable_years=applicable_years or [],
        verification_status=verification_status,
        verification_note=verification_note,
        is_placeholder=is_placeholder,
        actor=actor,
    )
    session.flush()
    return src


def verify_source(
    session: Session,
    source_id: str,
    *,
    actor: str,
    basis: str,
) -> EvidenceSource:
    """核验来源：必须给出操作者与核验依据，且来源必须已登记本体。"""
    if not actor or not (basis or "").strip():
        raise EvidenceGovernanceError("核验来源必须提供操作者与核验依据")
    src = session.execute(
        select(EvidenceSource).where(EvidenceSource.source_id == source_id)
    ).scalar_one_or_none()
    if src is None:
        raise EvidenceGovernanceError(f"来源不存在：{source_id}")
    if is_placeholder_record(src):
        raise EvidenceGovernanceError(
            f"来源 {source_id} 仍是占位符/引用式记录，必须先补全本体登记才能核验"
        )
    return set_source_status(
        session,
        source_id,
        VerificationStatus.VERIFIED,
        note=basis,
        actor=actor,
    )


def mark_source_unverifiable(
    session: Session, source_id: str, *, actor: str, note: str
) -> EvidenceSource:
    if not actor or not (note or "").strip():
        raise EvidenceGovernanceError("标记无法核验必须提供操作者与原因")
    return set_source_status(
        session, source_id, VerificationStatus.UNVERIFIABLE, note=note, actor=actor
    )


# ---------------------------------------------------------------------------
# C2 证据关联
# ---------------------------------------------------------------------------
def create_claim(
    session: Session,
    *,
    source_id: str,
    statement: str,
    topic: str | None = None,
    applicable_years: list[int] | None = None,
    actor: str = "user",
) -> EvidenceClaim:
    """登记事实声明。要求来源已存在；新声明一律为「候选映射」，不自动升级。"""
    src = session.execute(
        select(EvidenceSource).where(EvidenceSource.source_id == source_id)
    ).scalar_one_or_none()
    if src is None:
        raise EvidenceGovernanceError(f"来源未登记，无法登记事实声明：{source_id}")
    if not (statement or "").strip():
        raise EvidenceGovernanceError("事实声明内容不能为空")
    return register_claim(
        session,
        source_id=source_id,
        statement=statement.strip(),
        topic=topic,
        applicable_years=applicable_years or [],
        status=ClaimStatus.CANDIDATE,
        is_candidate=True,
        actor=actor,
    )


def attach_claim_to_path(
    session: Session, claim_id: int, path_id: int, *, actor: str = "user", applicable: bool = True
) -> ClaimPathLink:
    from decision_system.evidence.registry import link_claim_path

    return link_claim_path(session, claim_id, path_id, applicable=applicable, actor=actor)


def attach_claim_to_indicator(
    session: Session,
    claim_id: int,
    indicator_id: int,
    *,
    actor: str = "user",
    supports: bool = True,
) -> ClaimIndicatorLink:
    from decision_system.evidence.registry import link_claim_indicator

    return link_claim_indicator(session, claim_id, indicator_id, supports=supports, actor=actor)


def attach_claim_by_codes(
    session: Session,
    claim_id: int,
    *,
    path_key: str | None = None,
    indicator_code: str | None = None,
    actor: str = "user",
) -> list[str]:
    """按 path_key / 指标代码关联（UI 友好入口）。返回操作描述列表。"""
    done: list[str] = []
    if path_key:
        path = session.execute(
            select(AdmissionPath).where(AdmissionPath.path_key == path_key)
        ).scalar_one_or_none()
        if path is None:
            raise EvidenceGovernanceError(f"招生路径不存在：{path_key}")
        attach_claim_to_path(session, claim_id, path.id, actor=actor)
        done.append(f"路径 {path_key}")
    if indicator_code:
        ind = session.execute(
            select(Indicator).where(Indicator.code == indicator_code)
        ).scalar_one_or_none()
        if ind is None:
            raise EvidenceGovernanceError(f"指标不存在：{indicator_code}")
        attach_claim_to_indicator(session, claim_id, ind.id, actor=actor)
        done.append(f"指标 {indicator_code}")
    return done


# ---------------------------------------------------------------------------
# C3 人工核验
# ---------------------------------------------------------------------------
def submit_for_verification(
    session: Session, claim_id: int, *, actor: str, note: str | None = None
) -> EvidenceClaim:
    """提交核验：候选映射 → 待核验队列（**不**改变 is_candidate，不得视为已核验）。"""
    claim = session.get(EvidenceClaim, claim_id)
    if claim is None:
        raise EvidenceGovernanceError(f"事实声明不存在：{claim_id}")
    if not actor:
        raise EvidenceGovernanceError("提交核验必须提供操作者")
    before = claim.status
    claim.status = ClaimStatus.PENDING
    claim.is_candidate = True
    _audit(
        session,
        "claim.submit",
        "EvidenceClaim",
        claim_id,
        {"from": str(before), "to": str(ClaimStatus.PENDING), "actor": actor, "note": note},
        actor,
    )
    session.flush()
    return claim


def approve_claim(
    session: Session,
    claim_id: int,
    *,
    actor: str,
    basis: str,
    applicable_years: list[int] | None = None,
) -> EvidenceClaim:
    """核验通过：唯一合法升级入口（转调 registry.verify_claim）。"""
    if not (basis or "").strip():
        raise EvidenceGovernanceError("核验通过必须填写核验依据")
    return verify_claim(
        session, claim_id, actor=actor, basis=basis, applicable_years=applicable_years
    )


def reject_claim(session: Session, claim_id: int, *, actor: str, reason: str) -> EvidenceClaim:
    """核验驳回：退回待核验队列并保留候选标记，绝不保留已核验状态。"""
    if not (reason or "").strip():
        raise EvidenceGovernanceError("驳回必须填写理由")
    claim = session.get(EvidenceClaim, claim_id)
    if claim is None:
        raise EvidenceGovernanceError(f"事实声明不存在：{claim_id}")
    before = claim.status
    claim.status = ClaimStatus.PENDING
    claim.is_candidate = True
    _audit(
        session,
        "claim.reject",
        "EvidenceClaim",
        claim_id,
        {"from": str(before), "to": str(ClaimStatus.PENDING), "actor": actor, "reason": reason},
        actor,
    )
    session.flush()
    return claim


def mark_conflict(
    session: Session,
    claim_id: int,
    *,
    actor: str,
    description: str,
    conflicting_claim_id: int | None = None,
) -> ClaimConflict:
    """标记冲突（登记，不覆盖旧事实）。"""
    if not (description or "").strip():
        raise EvidenceGovernanceError("标记冲突必须填写冲突说明")
    return detect_and_record_conflict(
        session,
        new_claim_id=claim_id,
        existing_claim_id=conflicting_claim_id,
        description=description.strip(),
        actor=actor,
    )


def verification_history(session: Session, claim_id: int | None = None) -> list[dict[str, Any]]:
    """核验历史（只读 audit_log）。"""
    stmt = select(AuditLog).where(
        AuditLog.action.in_(
            [
                "claim.verify",
                "claim.reject",
                "claim.submit",
                "claim.conflict",
                "claim.conflict.resolve",
                "claim.register",
                "source.status",
                "source.register",
            ]
        )
    )
    if claim_id is not None:
        stmt = stmt.where(AuditLog.entity_id == str(claim_id))
    rows = session.execute(stmt.order_by(AuditLog.id.desc())).scalars().all()
    return [
        {
            "at": r.at.isoformat(timespec="seconds") if r.at else None,
            "actor": r.actor,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "detail": dict(r.detail or {}),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# C4 缺口统计
# ---------------------------------------------------------------------------
def evidence_gap_stats(session: Session) -> dict[str, Any]:
    """全部统计来自数据库实查，口径见本模块顶部定义。"""
    sources: Sequence[EvidenceSource] = (
        session.execute(select(EvidenceSource)).scalars().all()
    )
    claims: Sequence[EvidenceClaim] = session.execute(select(EvidenceClaim)).scalars().all()

    source_total = len(sources)
    source_placeholder = sum(1 for s in sources if is_placeholder_record(s))
    source_registered = sum(1 for s in sources if is_registered_source(s))
    source_verified = sum(1 for s in sources if is_verified_source(s))
    source_status_verified_only = sum(
        1 for s in sources if s.verification_status is VerificationStatus.VERIFIED
    )

    claim_total = len(claims)
    claim_candidate = sum(1 for c in claims if c.status is ClaimStatus.CANDIDATE)
    claim_pending = sum(1 for c in claims if c.status is ClaimStatus.PENDING)
    claim_verified = sum(
        1 for c in claims if c.status is ClaimStatus.VERIFIED and not c.is_candidate
    )
    claim_conflict = sum(1 for c in claims if c.status is ClaimStatus.CONFLICT)

    conflicts = session.execute(select(ClaimConflict)).scalars().all()
    conflict_total = len(conflicts)
    conflict_unresolved = sum(1 for c in conflicts if not c.resolved)

    return {
        "source_total": source_total,
        "source_registered": source_registered,
        "source_placeholder": source_placeholder,
        "source_verified": source_verified,
        "source_status_verified_only": source_status_verified_only,
        "source_pending": source_total - source_verified,
        "claim_total": claim_total,
        "claim_candidate": claim_candidate,
        "claim_pending": claim_pending,
        "claim_verified": claim_verified,
        "claim_conflict": claim_conflict,
        "pending_verification": sum(1 for c in claims if c.status in _PENDING_CLAIM_STATUSES),
        "conflict_total": conflict_total,
        "conflict_unresolved": conflict_unresolved,
        "definitions": {
            "source_total": "evidence_source 表行数（含占位符与引用式记录）",
            "source_registered": "非占位符且具备 url_or_file 或 publisher",
            "source_verified": "verification_status=已核验 且 已登记本体",
            "pending_verification": "状态属于 {候选映射, 待核验, 来源冲突} 的事实声明条数",
        },
    }


def list_sources(
    session: Session, *, only_unregistered: bool = False, keyword: str | None = None
) -> list[EvidenceSource]:
    stmt = select(EvidenceSource)
    rows = session.execute(stmt.order_by(EvidenceSource.source_id)).scalars().all()
    if only_unregistered:
        rows = [s for s in rows if not is_registered_source(s)]
    if keyword:
        kw = keyword.strip().lower()
        rows = [
            s
            for s in rows
            if kw in (s.source_id or "").lower() or kw in (s.title or "").lower()
        ]
    return rows


def claims_of_path(session: Session, path_id: int) -> list[EvidenceClaim]:
    links = session.execute(
        select(ClaimPathLink).where(ClaimPathLink.path_id == path_id)
    ).scalars().all()
    out: list[EvidenceClaim] = []
    for link in links:
        claim = session.get(EvidenceClaim, link.claim_id)
        if claim is not None:
            out.append(claim)
    return out


def count_claims() -> Any:  # pragma: no cover - 便于外部聚合查询
    return func.count(EvidenceClaim.id)
