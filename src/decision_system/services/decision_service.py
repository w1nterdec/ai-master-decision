"""把数据库实体装配成决策引擎输入的服务层（引擎与持久化解耦）。"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.engine.constraints import HardConstraintFacts
from decision_system.engine.pipeline import (
    DecisionEngine,
    EngineConfig,
    PathContext,
    PathDecision,
)
from decision_system.engine.scenarios import ScenarioDef, scenario_weights
from decision_system.engine.weights import WeightTree
from decision_system.evidence.gate import (
    ClaimView,
    EvidenceResolver,
    ScoreInput,
    SourceView,
    StrictEvidenceGate,
)
from decision_system.evidence.registry import unresolved_conflict_source_ids
from decision_system.models.entities import (
    AdmissionPath,
    ClaimIndicatorLink,
    ClaimPathLink,
    DecisionResult,
    EvidenceClaim,
    EvidenceSource,
    HardConstraintEvaluation,
    Indicator,
    Scenario,
    ScenarioMultiplier,
    ScoreRecord,
    WeightNode,
    WeightProfile,
)
from decision_system.models.enums import ClaimStatus, VerificationStatus


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


class SqlAlchemyEvidenceResolver:
    """实现 EvidenceResolver：直接查询 SQLite。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._conflicts: set[str] | None = None

    def find_source(self, source_id: str) -> SourceView | None:
        row = self.session.execute(
            select(EvidenceSource).where(EvidenceSource.source_id == source_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return SourceView(
            source_id=row.source_id,
            verification_status=row.verification_status,
            applicable_years=tuple(row.applicable_years or ()),
            is_placeholder=bool(row.is_placeholder),
        )

    def find_claims(
        self, source_id: str, path_key: str, indicator_code: str
    ) -> Sequence[ClaimView]:
        rows = (
            self.session.execute(
                select(EvidenceClaim).where(EvidenceClaim.source_ref_id == source_id)
            )
            .scalars()
            .all()
        )
        indicator = self.session.execute(
            select(Indicator).where(Indicator.code == indicator_code)
        ).scalar_one_or_none()
        indicator_id = indicator.id if indicator else None

        views: list[ClaimView] = []
        for c in rows:
            path_ok = False
            for link in c.path_links:
                if link.path is not None and link.path.path_key == path_key and link.applicable:
                    path_ok = True
                    break
            supports = False
            for link in c.indicator_links:
                if link.indicator_id == indicator_id and link.supports:
                    supports = True
                    break
            views.append(
                ClaimView(
                    claim_id=c.id,
                    source_id=c.source_ref_id,
                    status=c.status,
                    is_candidate=bool(c.is_candidate),
                    supports=supports,
                    applicable=path_ok,
                    path_key=path_key,
                    indicator_code=indicator_code,
                    applicable_years=tuple(c.applicable_years or ()),
                )
            )
        return views

    def has_unresolved_conflict(self, source_id: str) -> bool:
        if self._conflicts is None:
            self._conflicts = unresolved_conflict_source_ids(self.session)
        return source_id in self._conflicts


def build_weight_tree(session: Session, profile_code: str) -> WeightTree:
    """从数据库读取权重配置并构建权重树。"""
    profile = session.execute(
        select(WeightProfile).where(WeightProfile.code == profile_code)
    ).scalar_one_or_none()
    if profile is None:
        raise ValueError(f"权重配置不存在：{profile_code}")
    from decision_system.engine.weights import IndicatorNode

    nodes: list[IndicatorNode] = []
    for wn in profile.nodes:
        ind = wn.indicator
        nodes.append(
            IndicatorNode(
                code=ind.code,
                name=ind.name,
                level=ind.level,
                parent_code=ind.parent_code,
                raw_weight=float(wn.raw_weight),
                sort_order=ind.sort_order,
            )
        )
    return WeightTree(tuple(nodes))


def load_scenarios(session: Session) -> dict[str, ScenarioDef]:
    result: dict[str, ScenarioDef] = {}
    for sc in session.execute(select(Scenario)).scalars().all():
        mults = {m.target_code: float(m.multiplier) for m in sc.multipliers}
        result[sc.code] = ScenarioDef(
            code=sc.code,
            name=sc.name,
            multipliers=mults,
            is_demo=bool(sc.is_demo),
            description=sc.description or "",
        )
    return result


def build_engine(
    session: Session,
    config: EngineConfig | None = None,
    *,
    profile_code: str | None = None,
) -> DecisionEngine:
    cfg = config or EngineConfig()
    code = profile_code or cfg.profile_code
    tree = build_weight_tree(session, code)
    resolver = SqlAlchemyEvidenceResolver(session)
    gate = StrictEvidenceGate(resolver)
    scenarios = load_scenarios(session) or None
    return DecisionEngine(tree, config=cfg, gate=gate, scenarios=scenarios)


def path_context_from_db(session: Session, path: AdmissionPath) -> PathContext:
    facts = HardConstraintFacts(
        full_time_ok=path.full_time_ok,
        program_code_acceptable=path.program_code_acceptable,
        other_constraints_ok=path.other_constraints_ok,
        verification_2028=path.verification_2028,
        has_verified_2028_evidence=_has_verified_2028_evidence(session, path),
    )
    scores = tuple(
        ScoreInput(
            indicator_code=sr.indicator.code,
            raw_score=sr.raw_score,
            source_id=sr.source_ref_id,
            path_key=path.path_key,
        )
        for sr in path.score_records
    )
    return PathContext(
        path_key=path.path_key,
        label=f"{path.legacy_path_id or path.path_key} {path.school.name if path.school else ''}",
        school_name=path.school.name if path.school else "",
        facts=facts,
        scores=scores,
    )


def _has_verified_2028_evidence(session: Session, path: AdmissionPath) -> bool:
    rows = (
        session.execute(
            select(ClaimPathLink).where(ClaimPathLink.path_id == path.id)
        )
        .scalars()
        .all()
    )
    for link in rows:
        claim = session.get(EvidenceClaim, link.claim_id)
        if claim is None or claim.status is not ClaimStatus.VERIFIED:
            continue
        if claim.is_candidate:
            continue
        if claim.applicable_years and 2028 in claim.applicable_years:
            src = session.get(EvidenceSource, claim.source_id_fk)
            if src is not None and src.verification_status is VerificationStatus.VERIFIED:
                return True
    return False


def evaluate_and_persist(
    session: Session, path_key: str, config: EngineConfig | None = None
) -> PathDecision:
    path = session.execute(
        select(AdmissionPath).where(AdmissionPath.path_key == path_key)
    ).scalar_one_or_none()
    if path is None:
        raise ValueError(f"路径不存在：{path_key}")
    engine = build_engine(session, config)
    decision = engine.evaluate(path_context_from_db(session, path))
    session.add(
        DecisionResult(
            path_id=path.id,
            profile_code=decision.profile_code,
            evaluation_year=decision.evaluation_year,
            payload=decision.to_dict(),
        )
    )
    session.add(
        HardConstraintEvaluation(
            path_id=path.id,
            eligibility=decision.eligibility,
            qualification_2028=decision.qualification_2028,
            reasons=list(decision.constraint_reasons),
        )
    )
    session.flush()
    return decision


def to_summary(decision: PathDecision) -> dict[str, Any]:
    return {
        "path_key": decision.path_key,
        "label": decision.label,
        "eligibility": decision.eligibility.value,
        "qualification_2028": decision.qualification_2028.value,
        "base_score": decision.base.weighted_score,
        "base_status": decision.base.status.value,
        "base_weight_coverage": decision.base.weight_coverage,
        "scenario_scores": {k: v.weighted_score for k, v in decision.scenarios.items()},
        "scenario_status": {k: v.status.value for k, v in decision.scenarios.items()},
        "objective_a_status": decision.objective_a.status.value,
        "objective_a_score": decision.objective_a.score,
        "objective_b_status": decision.objective_b.status.value,
        "objective_b_score": decision.objective_b.score,
        "limitations": decision.limitations,
        "payload": decision.to_dict(),
    }
