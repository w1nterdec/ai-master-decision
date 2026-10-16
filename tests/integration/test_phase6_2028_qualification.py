"""Phase 6.0 M4｜2028 资格判定的边界回归测试。

背景：`_has_verified_2028_evidence()` 原实现存在三处误判风险，会把
**历史或无关**的 2028 已核验声明误当作「2028 已取得招生资格」。
本文件逐条锁定修复后的边界行为：**宁可判「未确认」，不可误判「已确认」**。
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from decision_system.models.entities import (
    AdmissionPath,
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
    _claim_supports_qualification,
    _has_verified_2028_evidence,
    _is_qualification_indicator,
)

YEAR = 2028

QUAL_IND_CODES = ("L3-报考可行性|招生路径|全日制统考路径明确性", "L2-报考可行性|招生路径")
OTHER_IND_CODES = (
    "L3-报考可行性|考试风险|初复试科目稳定性",
    "L3-职业发展|AI工程就业|岗位与实习机会",
)


def _make_path(session: Session) -> AdmissionPath:
    school = School(code="T", name="测试大学")
    session.add(school)
    session.flush()
    college = College(school_id=school.id, college_code="001", name="测试学院")
    session.add(college)
    session.flush()
    program = Program(college_id=college.id, program_code="085410", name="人工智能")
    session.add(program)
    session.flush()
    path = AdmissionPath(
        path_key="T|001|085410|全日制|方向01|2028|统考|一志愿",
        school_id=school.id,
        college_id=college.id,
        program_id=program.id,
        admission_year=YEAR,
        study_mode=StudyMode.FULL_TIME,
        admission_method=AdmissionMethod.UNIFIED_EXAM,
        path_kind=PathKind.FIRST_CHOICE,
    )
    session.add(path)
    session.flush()
    return path


def _make_claim(
    session: Session,
    path: AdmissionPath,
    *,
    topic: str | None = None,
    statement: str = "测试声明",
    claim_status: ClaimStatus = ClaimStatus.VERIFIED,
    is_candidate: bool = False,
    claim_years: list[int] | None = None,
    src_status: VerificationStatus = VerificationStatus.VERIFIED,
    src_years: list[int] | None = None,
    link_applicable: bool = True,
    indicator_codes: tuple[str, ...] = (),
) -> EvidenceClaim:
    src = EvidenceSource(
        source_id=f"SRC-{path.id}-{abs(hash((topic, statement, id(statement))))}",
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
        applicable_years=claim_years,
        status=claim_status,
        is_candidate=is_candidate,
    )
    session.add(claim)
    session.flush()
    session.add(
        ClaimPathLink(claim_id=claim.id, path_id=path.id, applicable=link_applicable)
    )
    for code in indicator_codes:
        ind = session.execute(
            __import__("sqlalchemy").select(Indicator).where(Indicator.code == code)
        ).scalar_one_or_none()
        if ind is None:
            ind = Indicator(
                code=code,
                level=1 if code.startswith("L1-") else (2 if code.startswith("L2-") else 3),
                name=code,
                parent_code=None,
            )
            session.add(ind)
            session.flush()
        session.add(ClaimIndicatorLink(claim_id=claim.id, indicator_id=ind.id, supports=True))
    session.flush()
    return claim


@pytest.fixture
def path(empty_db: Session) -> AdmissionPath:
    p = _make_path(empty_db)
    yield p
    empty_db.rollback()


# ---------------------------------------------------------------------------
# 1. 路径关联被标记为不适用
# ---------------------------------------------------------------------------
def test_link_not_applicable_never_confirms(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=[YEAR],
        link_applicable=False,
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


# ---------------------------------------------------------------------------
# 2. 来源年份边界：来源只适用 2027，不得支撑 2028
# ---------------------------------------------------------------------------
def test_source_year_boundary_blocks_2028(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=[YEAR],
        src_years=[2027],
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


def test_source_without_year_keeps_previous_behaviour(empty_db: Session, path: AdmissionPath):
    """来源未标注年份 → 视为不限年份（保持既有行为，不能因修复而变得更宽松/更严）。"""
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=[YEAR],
        src_years=None,
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is True


# ---------------------------------------------------------------------------
# 3. 声明必须与「招生资格」相关
# ---------------------------------------------------------------------------
def test_exam_subject_claim_does_not_grant_qualification(empty_db: Session, path: AdmissionPath):
    """考试科目类 2028 已核验声明，不构成招生资格证据。"""
    _make_claim(
        empty_db,
        path,
        topic="初试科目变化",
        statement="2028 初试第四单元为 408",
        claim_years=[YEAR],
        indicator_codes=OTHER_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


def test_qualification_claim_grants_qualification(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 该专业全日制统考招生",
        claim_years=[YEAR],
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is True


def test_topic_keyword_alone_can_grant_qualification(empty_db: Session, path: AdmissionPath):
    """没有指标关联时，topic/stage/正文命中资格关键词也可支撑。"""
    _make_claim(
        empty_db,
        path,
        topic="2028 招生资格",
        statement="2028 全日制统考招生资格已发布",
        claim_years=[YEAR],
    )
    assert _has_verified_2028_evidence(empty_db, path) is True


# ---------------------------------------------------------------------------
# 4. 既有严格规则不得被放宽
# ---------------------------------------------------------------------------
def test_candidate_claim_never_confirms(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=[YEAR],
        is_candidate=True,
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


def test_pending_claim_never_confirms(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=[YEAR],
        claim_status=ClaimStatus.PENDING,
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


def test_unverified_source_never_confirms(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=[YEAR],
        src_status=VerificationStatus.PENDING,
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


def test_claim_without_year_never_confirms(empty_db: Session, path: AdmissionPath):
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2028 全日制统考招生",
        claim_years=None,
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


def test_historical_year_claim_never_confirms_2028(empty_db: Session, path: AdmissionPath):
    """2027 的历史事实不得冒充 2028。"""
    _make_claim(
        empty_db,
        path,
        topic="招生目录",
        statement="2027 全日制统考招生",
        claim_years=[2027],
        src_years=[2027],
        indicator_codes=QUAL_IND_CODES[:1],
    )
    assert _has_verified_2028_evidence(empty_db, path) is False


# ---------------------------------------------------------------------------
# 5. 指标判定函数本身
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", QUAL_IND_CODES + ("L1-报考可行性",))
def test_qualification_indicator_positive(code: str):
    assert _is_qualification_indicator(code) is True


@pytest.mark.parametrize("code", OTHER_IND_CODES)
def test_qualification_indicator_negative(code: str):
    assert _is_qualification_indicator(code) is False


def test_claim_supports_qualification_by_keyword(empty_db: Session, path: AdmissionPath):
    claim = _make_claim(empty_db, path, topic="统考计划", statement="统考招生计划")
    assert _claim_supports_qualification(empty_db, claim) is True


def test_claim_supports_qualification_negative(empty_db: Session, path: AdmissionPath):
    claim = _make_claim(empty_db, path, topic="初试科目变化", statement="考试科目为 408")
    assert _claim_supports_qualification(empty_db, claim) is False
