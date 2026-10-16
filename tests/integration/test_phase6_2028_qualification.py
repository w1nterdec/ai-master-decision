"""Phase 6.1 M2｜2028 招生资格判定的边界回归测试。

判定原则：**宁可判「未确认」，不可误判「已确认」**。

覆盖的误判场景：
    * 错误学校 / 学院 / 专业代码
    * 专业级（跨方向）证据冒充方向级证据
    * 错误学习方式
    * 历史年份（2027 冒充 2028）
    * 候选 / 待核验声明
    * 无关声明（考试科目、名额口径）
    * 路径关联不适用
    * 来源年份边界
    * 未解决冲突（含冲突解决后恢复）
    * **文本关键词不得单独认定资格**
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.models.entities import (
    AdmissionPath,
    ClaimConflict,
    ClaimIndicatorLink,
    ClaimPathLink,
    College,
    EvidenceClaim,
    EvidenceSource,
    Indicator,
    Program,
    School,
)
from decision_system.models.enums import (
    AdmissionMethod,
    ClaimStatus,
    PathKind,
    SourceType,
    StudyMode,
    VerificationStatus,
)
from decision_system.services.decision_service import (
    _claim_is_path_specific,
    _claim_scope_matches,
    _claim_supports_qualification,
    _evaluate_claim_for_qualification,
    _has_verified_2028_evidence,
    _is_qualification_indicator,
    explain_2028_qualification,
)

YEAR = 2028

QUAL_L3 = "L3-报考可行性|招生路径|全日制统考路径明确性"
QUAL_L2 = "L2-报考可行性|招生路径"
NON_QUAL_QUOTA = "L3-报考可行性|招生路径|名额口径可靠性"
NON_QUAL_EXAM = "L3-报考可行性|考试风险|初复试科目稳定性"
NON_QUAL_L1 = "L1-报考可行性"
NON_QUAL_OTHER = "L3-职业发展|AI工程就业|岗位与实习机会"


def _ensure_indicator(session: Session, code: str) -> Indicator:
    ind = session.execute(
        select(Indicator).where(Indicator.code == code)
    ).scalar_one_or_none()
    if ind is None:
        level = 1 if code.startswith("L1-") else (2 if code.startswith("L2-") else 3)
        ind = Indicator(code=code, level=level, name=code, parent_code=None)
        session.add(ind)
        session.flush()
    return ind


def _ensure_scope(session: Session):
    school = School(code="T", name="测试大学")
    session.add(school)
    session.flush()
    c1 = College(school_id=school.id, college_code="001", name="人工智能学院")
    c2 = College(school_id=school.id, college_code="002", name="计算机学院")
    session.add_all([c1, c2])
    session.flush()
    p1 = Program(college_id=c1.id, program_code="085410", name="人工智能")
    p2 = Program(college_id=c1.id, program_code="085411", name="其他专业")
    session.add_all([p1, p2])
    session.flush()
    return school, c1, c2, p1, p2


def _make_path(
    session: Session, school, college, program, *, direction: str, study_mode=StudyMode.FULL_TIME
) -> AdmissionPath:
    path = AdmissionPath(
        path_key=f"T|{college.college_code}|{program.program_code}|{study_mode.value}|{direction}|2028|统考|一志愿",
        school_id=school.id,
        college_id=college.id,
        program_id=program.id,
        admission_year=YEAR,
        study_mode=study_mode,
        admission_method=AdmissionMethod.UNIFIED_EXAM,
        path_kind=PathKind.FIRST_CHOICE,
        direction=direction,
    )
    session.add(path)
    session.flush()
    return path


_counter = {"n": 0}


def _make_claim(
    session: Session,
    *,
    topic: str | None = None,
    statement: str = "测试声明",
    status: ClaimStatus = ClaimStatus.VERIFIED,
    is_candidate: bool = False,
    claim_years: list[int] | None = None,
    src_status: VerificationStatus = VerificationStatus.VERIFIED,
    src_years: list[int] | None = None,
    school_code: str | None = None,
    college_code: str | None = None,
    program_code: str | None = None,
    indicator_codes: tuple[str, ...] = (QUAL_L3,),
) -> EvidenceClaim:
    _counter["n"] += 1
    src = EvidenceSource(
        source_id=f"SRC-TEST-{_counter['n']}",
        title="测试来源",
        publisher="测试发布方",
        url_or_file="https://example.org/x",
        source_type=SourceType.OFFICIAL_CATALOG,
        verification_status=src_status,
        applicable_years=src_years,
    )
    session.add(src)
    session.flush()
    claim = EvidenceClaim(
        source_id_fk=src.id,
        source_ref_id=src.source_id,
        statement=statement,
        topic=topic,
        school_code=school_code,
        college_code=college_code,
        program_code=program_code,
        applicable_years=claim_years,
        status=status,
        is_candidate=is_candidate,
    )
    session.add(claim)
    session.flush()
    for code in indicator_codes:
        ind = _ensure_indicator(session, code)
        session.add(ClaimIndicatorLink(claim_id=claim.id, indicator_id=ind.id, supports=True))
    session.flush()
    return claim


def _link(session: Session, claim: EvidenceClaim, path: AdmissionPath, *, applicable: bool = True):
    session.add(ClaimPathLink(claim_id=claim.id, path_id=path.id, applicable=applicable))
    session.flush()


@pytest.fixture
def scope(empty_db: Session):
    school, c1, c2, p1, p2 = _ensure_scope(empty_db)
    path_a = _make_path(empty_db, school, c1, p1, direction="方向01")
    path_b = _make_path(empty_db, school, c1, p1, direction="方向02")
    path_pt = _make_path(
        empty_db, school, c1, p1, direction="方向01", study_mode=StudyMode.PART_TIME
    )
    path_other_college = _make_path(empty_db, school, c2, p1, direction="方向01")
    yield {
        "school": school,
        "c1": c1,
        "c2": c2,
        "p1": p1,
        "p2": p2,
        "a": path_a,
        "b": path_b,
        "pt": path_pt,
        "other": path_other_college,
    }
    empty_db.rollback()


def _valid_claim(session, scope, *, claim_years=(YEAR,), **kw):
    """一条**方向01 专属**且全部条件合格的资格声明。"""
    claim = _make_claim(session, claim_years=list(claim_years) if claim_years else None, **kw)
    _link(session, claim, scope["a"])
    return claim


# ---------------------------------------------------------------------------
# 正例：七项条件全部满足
# ---------------------------------------------------------------------------
def test_valid_direction_specific_claim_confirms(empty_db: Session, scope):
    _valid_claim(empty_db, scope, src_years=[YEAR])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is True


def test_valid_claim_with_scope_codes_confirms(empty_db: Session, scope):
    _valid_claim(
        empty_db,
        scope,
        src_years=[YEAR],
        school_code="T",
        college_code="001",
        program_code="085410",
    )
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is True


def test_other_direction_not_confirmed_by_sibling_claim(empty_db: Session, scope):
    """方向01 的证据不得让方向02 也被认定资格。"""
    _valid_claim(empty_db, scope, src_years=[YEAR])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is True
    assert _has_verified_2028_evidence(empty_db, scope["b"]) is False


# ---------------------------------------------------------------------------
# 适用范围不一致
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"school_code": "OTHER"},
        {"college_code": "002"},
        {"program_code": "085411"},
    ],
)
def test_scope_mismatch_rejected(empty_db: Session, scope, kwargs):
    _valid_claim(empty_db, scope, src_years=[YEAR], **kwargs)
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_scope_mismatch_reason_mentions_field(empty_db: Session, scope):
    claim = _valid_claim(empty_db, scope, src_years=[YEAR], college_code="002")
    ok, why = _claim_scope_matches(empty_db, claim, scope["a"])
    assert ok is False and "学院" in why


# ---------------------------------------------------------------------------
# 方向 / 学习方式粒度
# ---------------------------------------------------------------------------
def test_program_level_claim_cannot_prove_direction(empty_db: Session, scope):
    """学院/专业级声明不能证明某个具体方向招生。"""
    claim = _make_claim(empty_db, claim_years=[YEAR], src_years=[YEAR])
    _link(empty_db, claim, scope["a"])
    _link(empty_db, claim, scope["b"])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False
    ok, why = _claim_is_path_specific(empty_db, claim, scope["a"])
    assert ok is False and "专业级" in why


def test_claim_linked_only_to_other_study_mode_rejected(empty_db: Session, scope):
    """只关联到非全日制路径的证据，不能证明全日制路径招生。"""
    claim = _make_claim(empty_db, claim_years=[YEAR], src_years=[YEAR])
    _link(empty_db, claim, scope["pt"])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_claim_linked_to_other_college_path_rejected(empty_db: Session, scope):
    claim = _make_claim(empty_db, claim_years=[YEAR], src_years=[YEAR])
    _link(empty_db, claim, scope["other"])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


# ---------------------------------------------------------------------------
# 年份
# ---------------------------------------------------------------------------
def test_historical_year_cannot_prove_2028(empty_db: Session, scope):
    _valid_claim(empty_db, scope, claim_years=(2027,), src_years=[2027])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_claim_without_year_rejected(empty_db: Session, scope):
    _valid_claim(empty_db, scope, claim_years=None, src_years=[YEAR])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_source_year_boundary_rejected(empty_db: Session, scope):
    _valid_claim(empty_db, scope, claim_years=(YEAR,), src_years=[2027])
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_source_without_year_keeps_previous_behaviour(empty_db: Session, scope):
    _valid_claim(empty_db, scope, claim_years=(YEAR,), src_years=None)
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is True


# ---------------------------------------------------------------------------
# 声明状态
# ---------------------------------------------------------------------------
def test_candidate_claim_rejected(empty_db: Session, scope):
    _valid_claim(empty_db, scope, src_years=[YEAR], is_candidate=True)
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_pending_claim_rejected(empty_db: Session, scope):
    _valid_claim(empty_db, scope, src_years=[YEAR], status=ClaimStatus.PENDING)
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_unverified_source_rejected(empty_db: Session, scope):
    _valid_claim(
        empty_db,
        scope,
        src_years=[YEAR],
        src_status=VerificationStatus.PENDING,
    )
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_link_not_applicable_rejected(empty_db: Session, scope):
    claim = _make_claim(empty_db, claim_years=[YEAR], src_years=[YEAR])
    _link(empty_db, claim, scope["a"], applicable=False)
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


# ---------------------------------------------------------------------------
# 声明语义：不能证明"路径存在"的声明
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "codes,topic",
    [
        ((NON_QUAL_EXAM,), "初试科目变化"),          # 考试科目确认 ≠ 招生资格
        ((NON_QUAL_QUOTA,), "招生名额（目录计划口径）"),  # 目录计划数 ≠ 统考名额，也不能证明存在
        ((NON_QUAL_OTHER,), "就业与产业连接"),
        ((), "招生目录"),                              # 无任何指标关联
        ((NON_QUAL_L1,), "招生目录"),                  # 一级维度过粗
    ],
)
def test_non_qualification_claim_rejected(empty_db: Session, scope, codes, topic):
    _valid_claim(
        empty_db, scope, src_years=[YEAR], indicator_codes=codes, topic=topic,
        statement="2028 招生目录记载该专业招生",
    )
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_keywords_alone_never_confirm(empty_db: Session, scope):
    """**关键**：正文/topic 含「招生目录」「全日制」「统考」但无资格指标关联 → 不得成立。"""
    claim = _make_claim(
        empty_db,
        topic="招生目录",
        statement="2028 全日制统考招生资格已确认，招生名额 80 人",
        claim_years=[YEAR],
        src_years=[YEAR],
        indicator_codes=(NON_QUAL_EXAM,),
    )
    _link(empty_db, claim, scope["a"])
    assert _claim_supports_qualification(empty_db, claim) is False
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


# ---------------------------------------------------------------------------
# 冲突
# ---------------------------------------------------------------------------
def test_unresolved_conflict_rejected(empty_db: Session, scope):
    claim = _valid_claim(empty_db, scope, src_years=[YEAR])
    empty_db.add(
        ClaimConflict(claim_id=claim.id, description="与另一来源冲突", resolved=False)
    )
    empty_db.flush()
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is False


def test_resolved_conflict_allows(empty_db: Session, scope):
    claim = _valid_claim(empty_db, scope, src_years=[YEAR])
    empty_db.add(
        ClaimConflict(
            claim_id=claim.id,
            description="已裁定",
            resolved=True,
            resolution_note="以官方目录为准",
        )
    )
    empty_db.flush()
    assert _has_verified_2028_evidence(empty_db, scope["a"]) is True


# ---------------------------------------------------------------------------
# 指标判定函数
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", (QUAL_L3, QUAL_L2))
def test_qualification_indicator_positive(code):
    assert _is_qualification_indicator(code) is True


@pytest.mark.parametrize("code", (NON_QUAL_EXAM, NON_QUAL_QUOTA, NON_QUAL_L1, NON_QUAL_OTHER))
def test_qualification_indicator_negative(code):
    assert _is_qualification_indicator(code) is False


# ---------------------------------------------------------------------------
# 解释输出
# ---------------------------------------------------------------------------
def test_explain_returns_reasons_when_not_confirmed(empty_db: Session, scope):
    _valid_claim(empty_db, scope, claim_years=(2027,), src_years=[2027])
    ok, reasons = explain_2028_qualification(empty_db, scope["a"])
    assert ok is False
    assert reasons and any("2027" in r or "2028" in r for r in reasons)


def test_explain_no_links(empty_db: Session, scope):
    ok, reasons = explain_2028_qualification(empty_db, scope["a"])
    assert ok is False
    assert "没有任何证据声明关联" in reasons[0]


# ---------------------------------------------------------------------------
# 真实数据端到端：北邮 2027 官方已核验证据不得确认 2028 资格
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def prod_db():
    """生产库的**只读副本**（含 Phase 5.0 北邮官方已核验证据）。

    生产库本身不在版本库中（.gitignore 排除），本地缺失时整组用例跳过，
    不做任何伪造。
    """
    import shutil

    from decision_system.services.db import create_sqlite_engine, make_session_factory

    src = Path(__file__).resolve().parents[2] / "data" / "decision.db"
    if not src.is_file():
        pytest.skip(f"生产库不存在：{src}（需先执行 scripts/import_excel.py 与 Phase 5.0 迁移）")
    tmp = Path(tempfile.mkdtemp(prefix="prod_db_")) / "decision.db"
    shutil.copy2(src, tmp)
    engine = create_sqlite_engine(str(tmp))
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_real_bupt_2027_evidence_does_not_confirm_2028(prod_db: Session):
    """官方 2027 来源 → 已核验声明 → 北邮路径 → **不得**变成 2028 已确认。"""
    paths = (
        prod_db.execute(select(AdmissionPath).order_by(AdmissionPath.id)).scalars().all()
    )
    bupt = [p for p in paths if p.school and p.school.code == "BUPT"]
    assert len(bupt) == 2

    verified = (
        prod_db.execute(
            select(EvidenceClaim).where(EvidenceClaim.status == ClaimStatus.VERIFIED)
        )
        .scalars()
        .all()
    )
    assert verified, "生产库中应存在已核验证据（2027 北邮官方）"
    assert all(2028 not in (c.applicable_years or []) for c in verified)

    for p in bupt:
        ok, reasons = explain_2028_qualification(prod_db, p)
        assert ok is False, f"{p.legacy_path_id} 不应被 2027 证据确认为 2028 资格"
        assert reasons
        assert _has_verified_2028_evidence(prod_db, p) is False


def test_real_bupt_directions_not_confused(prod_db: Session):
    """方向01 与方向02 的证据不得互相串味。"""
    p01, p02 = (
        prod_db.execute(select(AdmissionPath).order_by(AdmissionPath.id)).scalars().all()[:2]
    )
    assert p01.direction == "方向01" and p02.direction == "方向02"

    ok01, r01 = explain_2028_qualification(prod_db, p01)
    ok02, r02 = explain_2028_qualification(prod_db, p02)
    assert ok01 is False and ok02 is False
    # 方向 01 专属声明（#50）只出现在 P01 的说明里，方向 02 专属声明（#51）只出现在 P02
    assert any("声明 #50" in r for r in r01), r01
    assert not any("声明 #50" in r for r in r02)
    assert any("声明 #51" in r for r in r02), r02
    assert not any("声明 #51" in r for r in r01)
