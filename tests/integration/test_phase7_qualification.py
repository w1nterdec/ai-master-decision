"""Phase 7.0｜2028 资格判定集成测试（P1）。

覆盖：
    * 真实生产库副本的安全性质检（历史 2027 证据不得确认 2028 资格）；
    * 构造场景验证：官方来源要求、全日制/统考约束、多方向合法覆盖、候选声明不升级。
使用数据库副本，不污染生产库。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from decision_system.models.base import Base
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
from decision_system.services.db import init_db
from decision_system.services import view_service
from decision_system.services.decision_service import explain_2028_qualification


PROD_DB = Path(__file__).resolve().parents[2] / "data" / "decision.db"
QUAL_INDICATOR = "L2-报考可行性|招生路径"


@pytest.fixture
def prod_session(tmp_path):
    if not PROD_DB.is_file():
        pytest.skip("生产库不存在，跳过真实数据质检")
    dest = tmp_path / "decision_copy.db"
    shutil.copy(PROD_DB, dest)
    engine = create_engine(f"sqlite:///{dest}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _build_scenario(session, *, source_type, study_mode, admission_method,
                    claim_years, is_candidate, link_both=False):
    sch = School(code="BUPT", name="北京邮电大学", region="华北")
    session.add(sch); session.flush()
    col = College(school_id=sch.id, college_code="005", name="人工智能学院")
    session.add(col); session.flush()
    prog = Program(college_id=col.id, program_code="085410", name="人工智能")
    session.add(prog); session.flush()
    p1 = AdmissionPath(
        path_key="BUPT|005|085410|全日制|方向01|2028|统考|一志愿",
        school_id=sch.id, college_id=col.id, program_id=prog.id,
        admission_year=2028, study_mode=study_mode, admission_method=admission_method,
        path_kind=PathKind.FIRST_CHOICE, direction="方向01", exam_unit4="408",
    )
    p2 = AdmissionPath(
        path_key="BUPT|005|085410|全日制|方向02|2028|统考|一志愿",
        school_id=sch.id, college_id=col.id, program_id=prog.id,
        admission_year=2028, study_mode=study_mode, admission_method=admission_method,
        path_kind=PathKind.FIRST_CHOICE, direction="方向02", exam_unit4="801",
    )
    session.add_all([p1, p2]); session.flush()
    ind = Indicator(code=QUAL_INDICATOR, level=2, name="招生路径",
                   parent_code="L1-报考可行性", sort_order=0)
    session.add(ind); session.flush()
    src = EvidenceSource(
        source_id="S1", title="t", publisher="p", source_type=source_type,
        verification_status=VerificationStatus.VERIFIED, applicable_years=[2028],
    )
    session.add(src); session.flush()
    claim = EvidenceClaim(
        source_id_fk=src.id, source_ref_id="S1", statement="该路径 2028 招生",
        status=ClaimStatus.VERIFIED, is_candidate=is_candidate,
        applicable_years=claim_years,
    )
    session.add(claim); session.flush()
    session.add(ClaimIndicatorLink(claim_id=claim.id, indicator_id=ind.id, supports=True))
    session.add(ClaimPathLink(claim_id=claim.id, path_id=p1.id, applicable=True))
    if link_both:
        session.add(ClaimPathLink(claim_id=claim.id, path_id=p2.id, applicable=True))
    session.flush()
    return p1, p2


# ---------------------------------------------------------------------------
# 真实数据质检
# ---------------------------------------------------------------------------
def test_bupt_direction01_2028_not_confirmed_from_2027(prod_session):
    path = prod_session.execute(
        __import__("sqlalchemy").select(AdmissionPath).where(
            AdmissionPath.direction == "方向01"
        )
    ).scalar_one_or_none()
    assert path is not None
    ok, reasons = explain_2028_qualification(prod_session, path, year=2028)
    assert ok is False
    assert any("2027" in r or "年份" in r or "未确认" in r for r in reasons)


def test_bupt_direction_evidence_is_historical_only(prod_session):
    path = prod_session.execute(
        __import__("sqlalchemy").select(AdmissionPath).where(
            AdmissionPath.direction == "方向02"
        )
    ).scalar_one_or_none()
    ok, _ = explain_2028_qualification(prod_session, path, year=2028)
    assert ok is False  # 仅有 2027 官方资料，不能确认 2028


def test_dossier_does_not_leak_other_direction(prod_session):
    """P2 要求：方向专属声明不得错配到另一方向（反之亦然）。

    方向专属声明：claim 50 仅描述方向01、claim 51 仅描述方向02。
    专业级声明（49/52/53/54）同时覆盖两方向，出现在任一方向证据中均正确。
    """
    import sqlalchemy as sa
    claim50 = prod_session.execute(
        sa.select(EvidenceClaim.statement).where(EvidenceClaim.id == 50)
    ).scalar_one()
    claim51 = prod_session.execute(
        sa.select(EvidenceClaim.statement).where(EvidenceClaim.id == 51)
    ).scalar_one()

    p1 = prod_session.execute(
        sa.select(AdmissionPath).where(AdmissionPath.direction == "方向01")
    ).scalar_one_or_none()
    p2 = prod_session.execute(
        sa.select(AdmissionPath).where(AdmissionPath.direction == "方向02")
    ).scalar_one_or_none()

    ev1 = view_service.build_evidence_summary(prod_session, p1)
    ev2 = view_service.build_evidence_summary(prod_session, p2)
    s1 = [it.statement for it in ev1.items]
    s2 = [it.statement for it in ev2.items]

    # 方向01 的证据必须含 claim50（方向01 专属），但不得含 claim51（方向02 专属）
    assert claim50 in s1
    assert claim51 not in s1
    # 对称
    assert claim51 in s2
    assert claim50 not in s2


# ---------------------------------------------------------------------------
# 构造场景
# ---------------------------------------------------------------------------
def test_official_source_required(empty_db):
    p1, _ = _build_scenario(
        empty_db, source_type=SourceType.MEDIA, study_mode=StudyMode.FULL_TIME,
        admission_method=AdmissionMethod.UNIFIED_EXAM, claim_years=[2028],
        is_candidate=False,
    )
    ok, reasons = explain_2028_qualification(empty_db, p1, year=2028)
    assert ok is False
    assert any("官方" in r for r in reasons)


def test_official_catalog_confirms_when_conditions_met(empty_db):
    p1, _ = _build_scenario(
        empty_db, source_type=SourceType.OFFICIAL_CATALOG, study_mode=StudyMode.FULL_TIME,
        admission_method=AdmissionMethod.UNIFIED_EXAM, claim_years=[2028],
        is_candidate=False,
    )
    ok, reasons = explain_2028_qualification(empty_db, p1, year=2028)
    assert ok is True


def test_non_full_time_rejected(empty_db):
    p1, _ = _build_scenario(
        empty_db, source_type=SourceType.OFFICIAL_CATALOG, study_mode=StudyMode.UNKNOWN,
        admission_method=AdmissionMethod.UNIFIED_EXAM, claim_years=[2028],
        is_candidate=False,
    )
    ok, reasons = explain_2028_qualification(empty_db, p1, year=2028)
    assert ok is False
    assert any("全日制" in r for r in reasons)


def test_candidate_claim_never_confirms(empty_db):
    p1, _ = _build_scenario(
        empty_db, source_type=SourceType.OFFICIAL_CATALOG, study_mode=StudyMode.FULL_TIME,
        admission_method=AdmissionMethod.UNIFIED_EXAM, claim_years=[2028],
        is_candidate=True,
    )
    ok, reasons = explain_2028_qualification(empty_db, p1, year=2028)
    assert ok is False
    assert any("候选" in r for r in reasons)


def test_multi_direction_official_coverage_allowed(empty_db):
    """官方证据明确覆盖多个方向时，可分别验证每条方向（P1 问题二）。"""
    p1, p2 = _build_scenario(
        empty_db, source_type=SourceType.OFFICIAL_CATALOG, study_mode=StudyMode.FULL_TIME,
        admission_method=AdmissionMethod.UNIFIED_EXAM, claim_years=[2028],
        is_candidate=False, link_both=True,
    )
    ok1, _ = explain_2028_qualification(empty_db, p1, year=2028)
    ok2, _ = explain_2028_qualification(empty_db, p2, year=2028)
    assert ok1 is True and ok2 is True


def test_historical_year_cannot_confirm_2028(empty_db):
    p1, _ = _build_scenario(
        empty_db, source_type=SourceType.OFFICIAL_CATALOG, study_mode=StudyMode.FULL_TIME,
        admission_method=AdmissionMethod.UNIFIED_EXAM, claim_years=[2027],
        is_candidate=False,
    )
    ok, reasons = explain_2028_qualification(empty_db, p1, year=2028)
    assert ok is False
    assert any("2027" in r or "年份" in r for r in reasons)
