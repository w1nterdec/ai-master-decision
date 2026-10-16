"""Phase 6.0｜只读展示查询服务。

只做**查询与组装**，不实现决策算法：
    * 评分 / 资格 / 覆盖率全部来自 engine 与 services.decision_service；
    * 不新增 ORM 实体、不改数据库结构；
    * 未知保持未知，不用 0 冒充。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.models.entities import (
    AdmissionPath,
    AdmissionRecord,
    ClaimPathLink,
    EvidenceClaim,
    EvidenceSource,
    Indicator,
    Mentor,
    ResearchResource,
    School,
)
from decision_system.models.enums import ClaimStatus, VerificationStatus
from decision_system.ui.decision_view import PathRow
from decision_system.ui.viewmodels import (
    CONFLICT,
    NOT_APPLICABLE,
    NOT_EVALUATED,
    PARTIAL,
    PENDING,
    QUAL_CONFIRMED,
    QUAL_UNCONFIRMED,
    UNJUDGEABLE,
    UNKNOWN,
    VERIFIED,
    ClaimItem,
    ComparisonCell,
    ComparisonSummary,
    DecisionArchive,
    EvidenceSummary,
    PathSummary,
    QuotaItem,
    RiskGap,
    RiskSummary,
    SchoolSummary,
    COMPARE_DIMENSIONS,
)

# 本文件位于 <repo>/src/decision_system/services/view_service.py
#   parents[0]=services  parents[1]=decision_system  parents[2]=src  parents[3]=<repo>
ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_PATH = ROOT / "data" / "decision_profile.json"


def _now_text() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 证据摘要
# ---------------------------------------------------------------------------
def build_evidence_summary(session: Session, path: AdmissionPath) -> EvidenceSummary:
    links = (
        session.execute(select(ClaimPathLink).where(ClaimPathLink.path_id == path.id))
        .scalars()
        .all()
    )
    items: list[ClaimItem] = []
    verified = candidate = pending = 0
    verified_2028 = 0
    source_ids: set[int] = set()
    for link in links:
        claim = session.get(EvidenceClaim, link.claim_id)
        if claim is None:
            continue
        src = session.get(EvidenceSource, claim.source_id_fk)
        if src is not None:
            source_ids.add(src.id)
        years = tuple(claim.applicable_years or ())
        st = str(claim.status)
        if claim.status is ClaimStatus.VERIFIED:
            verified += 1
            if 2028 in years:
                verified_2028 += 1
        elif claim.status is ClaimStatus.CANDIDATE:
            candidate += 1
        elif claim.status is ClaimStatus.PENDING:
            pending += 1
        items.append(
            ClaimItem(
                statement=claim.statement,
                topic=claim.topic,
                status=st,
                applicable_years=years,
                source_title=src.title if src else UNKNOWN,
                source_status=str(src.verification_status) if src else UNKNOWN,
                source_type=str(src.source_type) if src else None,
                url_or_file=src.url_or_file if src else None,
                is_candidate=bool(claim.is_candidate),
            )
        )

    verified_sources = unregistered = 0
    for sid in source_ids:
        src = session.get(EvidenceSource, sid)
        if src is None:
            continue
        if src.verification_status is VerificationStatus.VERIFIED:
            verified_sources += 1
        elif src.verification_status is VerificationStatus.UNREGISTERED:
            unregistered += 1

    total = len(items)
    if total == 0:
        state = UNKNOWN
    elif verified and verified == total:
        state = VERIFIED
    elif verified:
        state = PARTIAL
    elif pending or candidate:
        state = PENDING
    else:
        state = UNKNOWN

    return EvidenceSummary(
        total_claims=total,
        verified_claims=verified,
        candidate_claims=candidate,
        pending_claims=pending,
        verified_sources=verified_sources,
        unregistered_sources=unregistered,
        conflicts=0,
        verified_2028_claims=verified_2028,
        items=tuple(items),
        state=state,
    )


def load_quotas(session: Session, path: AdmissionPath) -> tuple[QuotaItem, ...]:
    rows = (
        session.execute(
            select(AdmissionRecord).where(AdmissionRecord.path_id == path.id)
        )
        .scalars()
        .all()
    )
    out: list[QuotaItem] = []
    for r in rows:
        claim_status = None
        if r.evidence_claim_id:
            c = session.get(EvidenceClaim, r.evidence_claim_id)
            claim_status = str(c.status) if c else None
        out.append(
            QuotaItem(
                year=r.year,
                basis=r.quota_basis,
                method=str(r.admission_method),
                planned=r.planned_quota,
                actual=r.actual_admitted,
                note=r.note,
                claim_status=claim_status,
            )
        )
    return tuple(sorted(out, key=lambda q: (q.year, q.basis), reverse=True))


# ---------------------------------------------------------------------------
# 路径 / 学校摘要
# ---------------------------------------------------------------------------
def build_path_summary(session: Session, row: PathRow) -> PathSummary:
    p = row.path
    d = row.decision
    ev = build_evidence_summary(session, p)
    qual = str(d.qualification_2028) if d is not None else UNKNOWN
    qual_text = QUAL_CONFIRMED if qual == "已确认" else QUAL_UNCONFIRMED
    unknown = tuple(d.to_dict().get("unknown_indicators", ())) if d is not None else ()
    coverage = float(d.base.weight_coverage) if d is not None else None
    return PathSummary(
        path_id=p.id,
        path_key=p.path_key,
        legacy_id=p.legacy_path_id,
        school_name=p.school.name if p.school else UNKNOWN,
        school_code=p.school.code if p.school else "",
        college_name=(p.college.name or "") if p.college else "",
        college_code=(p.college.college_code or "") if p.college else "",
        program_code=p.program.program_code if p.program else UNKNOWN,
        program_name=p.program.name if p.program else None,
        study_mode=str(p.study_mode),
        direction=p.direction,
        exam_unit4=p.exam_unit4,
        admission_year=p.admission_year,
        admission_method=str(p.admission_method),
        path_kind=str(p.path_kind),
        training_location=p.training_location,
        qualification_2028=qual_text,
        eligibility=str(d.eligibility) if d is not None else UNKNOWN,
        key_risk=p.key_risk,
        notes=p.notes,
        evidence=ev,
        quotas=load_quotas(session, p),
        decision=d,
        coverage=coverage,
        unknown_indicators=unknown,
    )


def load_path_summaries(session: Session, rows: Sequence[PathRow]) -> list[PathSummary]:
    return [build_path_summary(session, r) for r in rows]


def _eval_state(coverage: float | None, threshold: float = 0.8) -> str:
    if coverage is None or coverage <= 0:
        return NOT_EVALUATED
    if coverage >= threshold:
        return "已评估"
    return PARTIAL


def build_school_summaries(
    session: Session,
    summaries: Sequence[PathSummary],
    *,
    threshold: float = 0.8,
) -> list[SchoolSummary]:
    by_code: dict[str, list[PathSummary]] = {}
    for s in summaries:
        by_code.setdefault(s.school_code, []).append(s)

    out: list[SchoolSummary] = []
    for code, paths in by_code.items():
        first = paths[0]
        region, city = _school_region(session, code)
        coverages = [p.coverage for p in paths if p.coverage is not None]
        # 职业价值 / 报考风险：分别取关联维度覆盖情况（当前无评分时一律待评估）
        career_state = _eval_state(max(coverages) if coverages else None, threshold)
        risk_state = career_state  # 评分矩阵尚未分维度建立，保持一致口径
        verified_items = [it for p in paths for it in p.evidence.items if it.status == VERIFIED]
        strengths = tuple(i.statement for i in verified_items[:3])
        risks: list[str] = []
        for p in paths:
            if p.key_risk:
                risks.append(p.key_risk)
        risks = risks[:3]
        ev = EvidenceSummary(
            total_claims=sum(p.evidence.total_claims for p in paths),
            verified_claims=sum(p.evidence.verified_claims for p in paths),
            candidate_claims=sum(p.evidence.candidate_claims for p in paths),
            pending_claims=sum(p.evidence.pending_claims for p in paths),
            verified_sources=sum(p.evidence.verified_sources for p in paths),
            unregistered_sources=sum(p.evidence.unregistered_sources for p in paths),
            verified_2028_claims=sum(p.evidence.verified_2028_claims for p in paths),
            state=(VERIFIED if verified_items else PENDING),
            items=tuple(verified_items),
        )
        out.append(
            SchoolSummary(
                code=code,
                name=first.school_name,
                region=region,
                city=city,
                path_count=len(paths),
                career_value_state=career_state,
                risk_state=risk_state,
                qualification_2028=(
                    QUAL_CONFIRMED
                    if any(p.qualification_is_confirmed for p in paths)
                    else QUAL_UNCONFIRMED
                ),
                strengths=strengths,
                risks=tuple(risks),
                evidence=ev,
                paths=tuple(paths),
            )
        )
    return sorted(out, key=lambda s: (-s.evidence.verified_claims, s.name))


def _school_region(session: Session, school_code: str) -> tuple[str | None, str | None]:
    """地域/城市取自 school 实体；ViewModel 内不硬编码任何城市名。"""
    if not school_code:
        return None, None
    row = session.execute(
        select(School).where(School.code == school_code)
    ).scalar_one_or_none()
    if row is None:
        return None, None
    return row.region, row.city


# ---------------------------------------------------------------------------
# 多校对比
# ---------------------------------------------------------------------------
def _dimension_cell(session: Session, p: PathSummary, dim: str, l1: str | None) -> ComparisonCell:
    if dim == "考试科目":
        return ComparisonCell(
            dim, p.exam_unit4 or UNKNOWN, judgeable=bool(p.exam_unit4)
        )
    if dim == "历史招生规模":
        if not p.quotas:
            return ComparisonCell(dim, UNKNOWN, judgeable=False)
        txt = "；".join(
            f"{q.year} {q.basis}"
            + (f" 计划 {q.planned}" if q.planned is not None else " 计划暂无数据")
            + (f" 实际 {q.actual}" if q.actual is not None else "")
            for q in p.quotas
        )
        return ComparisonCell(dim, txt, judgeable=True)
    if dim == "调剂价值":
        if p.path_kind and "调剂" in str(p.path_kind):
            return ComparisonCell(
                dim, f"调剂路径 · {p.eligibility}", judgeable=True
            )
        return ComparisonCell(dim, NOT_APPLICABLE, judgeable=False)
    if dim == "数据可信度":
        return ComparisonCell(dim, p.evidence.state, judgeable=True)
    # 依赖评分的维度：当前评分矩阵全部未知 → 无法判断，绝不补零
    return ComparisonCell(dim, UNJUDGEABLE, judgeable=False)


def build_comparison(
    session: Session, paths: Sequence[PathSummary]
) -> ComparisonSummary:
    rows: list[tuple[str, tuple[ComparisonCell, ...]]] = []
    for dim, l1 in COMPARE_DIMENSIONS:
        cells = tuple(_dimension_cell(session, p, dim, l1) for p in paths)
        # 只有「可判断且存在差异」才高亮
        texts = {c.text for c in cells if c.judgeable}
        highlight = len(texts) > 1
        rows.append(
            (
                dim,
                tuple(
                    ComparisonCell(c.dimension, c.text, c.judgeable, highlight and c.judgeable)
                    for c in cells
                ),
            )
        )
    return ComparisonSummary(paths=tuple(paths), rows=tuple(rows))


# ---------------------------------------------------------------------------
# 风险与缺口
# ---------------------------------------------------------------------------
def build_risk_gaps(session: Session, paths: Sequence[PathSummary]) -> list[RiskGap]:
    gaps: list[RiskGap] = []
    unconfirmed = [p for p in paths if not p.qualification_is_confirmed]
    if unconfirmed:
        gaps.append(
            RiskGap(
                topic=f"{len(unconfirmed)} 条路径的 2028 招生资格未确认",
                reason="2028 招生目录尚未发布或未通过严格闸门；历史事实不得冒充 2028。",
                affects_hard_constraint=True,
                affects_first_choice_risk=True,
                may_change_choice=True,
                data_exists_but_unstructured=False,
            )
        )
    unregistered = sum(p.evidence.unregistered_sources for p in paths)
    if unregistered:
        gaps.append(
            RiskGap(
                topic=f"{unregistered} 个来源缺少本体登记（无 URL / 发布方）",
                reason="来源无法核验，其声明不能进入正式评分与资格判定。",
                affects_hard_constraint=True,
                affects_first_choice_risk=False,
                may_change_choice=True,
                data_exists_but_unstructured=True,
            )
        )
    pending = sum(p.evidence.pending_claims for p in paths)
    if pending:
        gaps.append(
            RiskGap(
                topic=f"{pending} 条声明处于待核验",
                reason="待核验声明不参与评分，相关维度只能显示「无法判断」。",
                affects_hard_constraint=False,
                affects_first_choice_risk=True,
                may_change_choice=True,
                data_exists_but_unstructured=True,
            )
        )
    if session.execute(select(Mentor).limit(1)).scalar_one_or_none() is None:
        gaps.append(
            RiskGap(
                topic="导师数据缺失（mentor 表为空）",
                reason="影响「院校、专业与科研平台」判断，无法评估科研匹配。",
                affects_hard_constraint=False,
                affects_first_choice_risk=False,
                may_change_choice=True,
                data_exists_but_unstructured=False,
            )
        )
    if session.execute(select(ResearchResource).limit(1)).scalar_one_or_none() is None:
        gaps.append(
            RiskGap(
                topic="科研资源数据缺失（research_resource 表为空）",
                reason="影响培养价值与科研平台可进入性判断。",
                affects_hard_constraint=False,
                affects_first_choice_risk=False,
                may_change_choice=True,
                data_exists_but_unstructured=False,
            )
        )
    if not any(p.quotas for p in paths):
        gaps.append(
            RiskGap(
                topic="缺少分口径招生名额记录",
                reason="目录计划 / 统考计划 / 实际录取均无记录，报考风险无法量化。",
                affects_hard_constraint=False,
                affects_first_choice_risk=True,
                may_change_choice=True,
                data_exists_but_unstructured=False,
            )
        )
    for g in gaps:
        g.score = (
            (2 if g.affects_hard_constraint else 0)
            + (1 if g.affects_first_choice_risk else 0)
            + (1 if g.may_change_choice else 0)
        )
    gaps.sort(key=lambda g: -g.score)
    return gaps


def build_risk_summary(session: Session, p: PathSummary) -> RiskSummary:
    reasons: tuple[str, ...] = ()
    if p.decision is not None:
        reasons = tuple(p.decision.constraint_reasons)
    hard_state = p.eligibility
    first = (
        f"目标路径：{p.title}（{p.subtitle}）",
        f"考试科目：{p.exam_unit4 or UNKNOWN}",
        f"2028 资格：{p.qualification_2028}",
        f"主要不确定性：{(p.key_risk or UNKNOWN)}",
    )
    if p.quotas:
        first = first + (
            "历史名额（分口径）："
            + "；".join(f"{q.year} {q.basis} 计划 {q.planned if q.planned is not None else UNKNOWN}" for q in p.quotas),
        )
    else:
        first = first + ("历史名额：暂无数据（目录计划 / 统考计划 / 实际录取均无记录）",)
    transfer = (
        "暂无足够证据支持调剂推荐"
        if not (p.path_kind and "调剂" in str(p.path_kind))
        else f"该路径为{p.path_kind}，是否接受取决于培养价值证据（当前{p.evidence.state}）"
    )
    employment = (
        "方向：AI 工程 / LLM · Agent（用户已确认方向，非系统推断）",
        "本模块仅提供风险情景说明与准备事项，不做就业预测",
    )
    return RiskSummary(
        path=p,
        hard_constraint_state=hard_state,
        hard_constraint_reasons=reasons,
        first_choice=first,
        transfer=(transfer,),
        employment=employment,
        gaps=tuple(build_risk_gaps(session, [p])),
        risk_level=UNKNOWN if p.qualification_2028 != QUAL_CONFIRMED else PENDING,
    )


# ---------------------------------------------------------------------------
# 决策档案（轻量持久化，不改数据库结构）
# ---------------------------------------------------------------------------
def load_archive() -> DecisionArchive:
    if not ARCHIVE_PATH.is_file():
        return DecisionArchive()
    try:
        data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DecisionArchive()
    return DecisionArchive.from_dict(data)


def save_archive(archive: DecisionArchive) -> Path:
    archive.updated_at = _now_text()
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_PATH.write_text(
        json.dumps(archive.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ARCHIVE_PATH
