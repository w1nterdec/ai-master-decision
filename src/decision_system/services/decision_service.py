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
    College,
    Program,
    School,
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
from decision_system.models.enums import (
    AdmissionMethod,
    ClaimStatus,
    SourceType,
    StudyMode,
    VerificationStatus,
)


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


# ---------------------------------------------------------------------------
# 招生资格判定（Phase 6.1 M2 重写）
#
# 判定原则：**宁可判「未确认」，不可误判「已确认」**。
# 认定一条路径在某年"确实招生"，必须同时满足七项条件（见 _evaluate_claim_for_qualification），
# 其中"资格语义"只认指标树上明确表示「该全日制统考路径存在」的指标，
# **不使用任何文本关键词**（"招生目录""招生名额""全日制""统考"等一律不作数）。
# ---------------------------------------------------------------------------

QUALIFICATION_L1_NAME = "报考可行性"
QUALIFICATION_L2_NAME = "招生路径"

# 语义锚点：只有这两个指标的语义是"该全日制统考招生路径在某年确实存在"。
# 「名额口径可靠性」只说明人数口径；「考试风险」只说明科目；一级「报考可行性」过粗。
QUALIFICATION_INDICATOR_CODES: frozenset[str] = frozenset(
    {
        "L3-报考可行性|招生路径|全日制统考路径明确性",
        "L2-报考可行性|招生路径",
    }
)

# 资格判定只接受"官方招生来源"：官方招生目录 / 官方公告 / 官方网页 / PDF 原件。
# 研究报告、媒体报道、访谈等不得单独作为某年"确实招生"的依据。
OFFICIAL_SOURCE_TYPES: frozenset[SourceType] = frozenset(
    {
        SourceType.OFFICIAL_CATALOG,
        SourceType.OFFICIAL_NOTICE,
        SourceType.OFFICIAL_WEB,
        SourceType.PDF_ORIGINAL,
    }
)


def _name_segments(code: str) -> list[str]:
    """`L3-报考可行性|招生路径|名额口径可靠性` -> ['报考可行性', '招生路径', '名额口径可靠性']。"""
    return [seg.split("-", 1)[-1] for seg in code.split("|")]


def _is_qualification_indicator(code: str) -> bool:
    """只有语义锚点指标可以证明路径存在。

    同属「招生路径」子组的「名额口径可靠性」只说明人数口径是否可靠，
    **不能**证明该路径在某年招生；一级「报考可行性」含「考试风险」，语义过粗。
    """
    return code in QUALIFICATION_INDICATOR_CODES


def _claim_supports_qualification(session: Session, claim: EvidenceClaim) -> bool:
    """声明是否**在语义上**支撑「该招生路径存在」。

    只依据指标关联（`supports=True` 且指标属于「报考可行性 · 招生路径」），
    **不**看 topic / stage / 正文关键词。
    """
    return _qualification_indicator_hit(session, claim)[0]


def _qualification_indicator_hit(
    session: Session, claim: EvidenceClaim
) -> tuple[bool, str | None]:
    links = (
        session.execute(
            select(ClaimIndicatorLink).where(ClaimIndicatorLink.claim_id == claim.id)
        )
        .scalars()
        .all()
    )
    if not links:
        return False, "未关联任何指标，无法判断其语义"
    seen: list[str] = []
    for l in links:
        ind = session.get(Indicator, l.indicator_id)
        if ind is None:
            continue
        if not l.supports:
            seen.append(f"{ind.code}(不支持)")
            continue
        if _is_qualification_indicator(ind.code):
            return True, None
        seen.append(ind.code)
    return False, "仅关联 " + "、".join(seen) + "，不能证明该路径存在"


def _path_codes(session: Session, path: AdmissionPath) -> tuple[str | None, ...]:
    school = session.get(School, path.school_id)
    college = session.get(College, path.college_id)
    program = session.get(Program, path.program_id)
    return (
        school.code if school else None,
        college.college_code if college else None,
        program.program_code if program else None,
    )


def _claim_scope_matches(
    session: Session, claim: EvidenceClaim, path: AdmissionPath
) -> tuple[bool, str | None]:
    """证据适用范围（学校 / 学院 / 专业代码）必须与路径一致。

    声明**已标注**的层级必须精确相等；未标注的层级不做正向证明，
    由「方向/学习方式粒度」检查（_claim_is_path_specific）兜底。
    """
    school_code, college_code, program_code = _path_codes(session, path)
    checks = (
        ("学校", claim.school_code, school_code),
        ("学院", claim.college_code, college_code),
        ("专业代码", claim.program_code, program_code),
    )
    for label, declared, actual in checks:
        if declared and actual and str(declared) != str(actual):
            return False, f"证据适用{label}「{declared}」与路径「{actual}」不一致"
    return True, None


def _claim_is_path_specific(
    session: Session, claim: EvidenceClaim, path: AdmissionPath
) -> tuple[bool, str | None, bool]:
    """方向 / 学习方式粒度检查（Phase 7.0 修正）。

    返回 ``(ok, reason, professional)``：
    - ``ok``：该声明是否可用于本路径资格判定；仅当声明完全未关联本路径（或
      只关联了其它方向）时为 ``False``。
    - ``professional``：声明同时覆盖同一专业的多条兄弟路径，属于**专业级/学院级**
      证据（如官方目录同时列出多个方向）。按 Phase 7.0 要求，这类证据**可以分别
      验证**每条被覆盖的路径，不再"仅因关联多方向就拒绝"；``professional`` 仅用于
      展示提示（"专业级证据，覆盖多方向"），不阻止判定。
    - 方向范围存在未解决冲突时，由 `_evaluate_claim_for_qualification` 的冲突检查
      兜底拒绝。
    """
    siblings = set(
        session.execute(
            select(AdmissionPath.id).where(
                AdmissionPath.school_id == path.school_id,
                AdmissionPath.college_id == path.college_id,
                AdmissionPath.program_id == path.program_id,
            )
        )
        .scalars()
        .all()
    )
    linked = set(
        session.execute(
            select(ClaimPathLink.path_id).where(
                ClaimPathLink.claim_id == claim.id,
                ClaimPathLink.applicable.is_(True),
            )
        )
        .scalars()
        .all()
    )
    hit = siblings & linked
    if not hit:
        return False, "声明未关联到本路径（或只关联了其它方向）", False
    # 命中本路径：允许判定。多方向覆盖视为专业级证据，仍可分别验证。
    if len(hit) > 1:
        return (
            True,
            "专业级/学院级证据，覆盖多个方向（可分别验证每条被覆盖的路径）",
            True,
        )
    return True, None, False


def _evaluate_claim_for_qualification(
    session: Session, path: AdmissionPath, claim: EvidenceClaim, link: ClaimPathLink, year: int
) -> tuple[bool, str]:
    """逐条判定一条声明能否作为「`year` 年该路径确实招生」的证据。

    七项条件缺一不可：
        1. 路径关联明确且有效；
        2. 声明已核验、非候选；
        3. 声明与来源适用年份均含 `year`；
        4. 来源已核验；
        5. 学校 / 学院 / 专业代码适用范围一致；
        6. 方向 / 学习方式粒度足够（不能是专业级证据）；
        7. 无影响资格判断的未解决冲突。
    另：声明语义必须能证明路径存在（指标锚点），不使用文本关键词。
    """
    if not link.applicable:
        return False, "路径关联被标记为不适用"

    if claim.status is not ClaimStatus.VERIFIED:
        return False, f"声明状态为「{claim.status}」，非已核验"
    if claim.is_candidate:
        return False, "声明为候选映射，永不自动升级为已核验"

    if not claim.applicable_years or year not in claim.applicable_years:
        years = list(claim.applicable_years or [])
        return False, f"声明适用年份 {years or '未标注'} 不含 {year}"

    src = session.get(EvidenceSource, claim.source_id_fk)
    if src is None:
        return False, "来源缺失"
    if src.verification_status is not VerificationStatus.VERIFIED:
        return False, f"来源核验状态为「{src.verification_status}」"
    if src.applicable_years and year not in src.applicable_years:
        return False, f"来源适用年份 {list(src.applicable_years)} 不含 {year}"

    ok, why = _qualification_indicator_hit(session, claim)
    if not ok:
        return False, why or "声明语义不能证明该路径存在"

    ok, why = _claim_scope_matches(session, claim, path)
    if not ok:
        return False, why or "证据适用范围与路径不一致"

    # 官方来源约束：资格判定只允许官方招生来源，杜绝研究报告/媒体/访谈单独证明招生。
    if src.source_type not in OFFICIAL_SOURCE_TYPES:
        return False, f"来源类型「{src.source_type}」非官方招生来源，不能单独证明资格"

    # 学习方式 / 招生方式约束：用户仅考虑全日制统考路径；未知则无法确认。
    if path.study_mode not in (StudyMode.FULL_TIME,):
        return False, f"路径学习方式「{path.study_mode}」非全日制，用户仅考虑全日制"
    if path.admission_method == AdmissionMethod.UNKNOWN:
        return False, "路径招生方式未知，无法确认资格"

    ok, why, _professional = _claim_is_path_specific(session, claim, path)
    if not ok:
        return False, why or "证据粒度不足以定位到本路径"

    if unresolved_conflict_source_ids(session) and claim.source_ref_id in (
        unresolved_conflict_source_ids(session)
    ):
        return False, "来源存在未解决冲突，不得用于资格判定"

    return True, f"来源 {src.source_id} 声明 #{claim.id} 通过全部资格条件"


def explain_2028_qualification(
    session: Session, path: AdmissionPath, *, year: int = 2028
) -> tuple[bool, tuple[str, ...]]:
    """返回 (是否已取得资格证据, 逐条未通过原因)。供页面展示「为什么未确认」。"""
    links = (
        session.execute(
            select(ClaimPathLink).where(ClaimPathLink.path_id == path.id)
        )
        .scalars()
        .all()
    )
    if not links:
        return False, ("该路径没有任何证据声明关联",)
    reasons: list[str] = []
    for link in links:
        claim = session.get(EvidenceClaim, link.claim_id)
        if claim is None:
            reasons.append(f"关联 #{link.claim_id} 指向不存在的声明")
            continue
        ok, why = _evaluate_claim_for_qualification(session, path, claim, link, year)
        if ok:
            return True, (f"{year} 年资格证据成立：{why}",)
        reasons.append(f"声明 #{claim.id}（{claim.topic or '无主题'}）：{why}")
    return False, tuple(reasons)


def _has_verified_2028_evidence(
    session: Session, path: AdmissionPath, *, year: int = 2028
) -> bool:
    """是否存在**可支撑 `year` 年招生资格**的已核验证据（严格判定）。"""
    return explain_2028_qualification(session, path, year=year)[0]


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
