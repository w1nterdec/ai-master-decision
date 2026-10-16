"""导入与路径身份的集成测试（Task E 20-23）。"""

from __future__ import annotations

import pytest

from decision_system.importers.excel_importer import ExcelImporter
from decision_system.models.entities import (
    AdmissionPath,
    AdmissionRecord,
    AuditLog,
    ClaimIndicatorLink,
    EvidenceClaim,
    EvidenceSource,
    ImportBatch,
    Indicator,
    ScoreRecord,
    WeightNode,
)
from decision_system.models.enums import (
    AdmissionMethod,
    ClaimStatus,
    PathKind,
    ScoreValidity,
    StudyMode,
    VerificationStatus,
)
from decision_system.services.path_identity import build_path_key, parse_path_key

from ..fixtures import RAW_XLSX

BASE = dict(
    school_code="TEST", college_code="005", program_code="085410",
    study_mode=StudyMode.FULL_TIME, direction="方向01",
    admission_method=AdmissionMethod.UNIFIED_EXAM, path_kind=PathKind.FIRST_CHOICE,
)


@pytest.fixture
def orgs(empty_db):
    """创建一个 学校 / 两个学院 / 两个同名专业代码 的最小组织，满足外键约束。"""
    from decision_system.models.entities import College, Program, School

    school = School(code="TEST", name="测试大学")
    empty_db.add(school)
    empty_db.flush()
    c1 = College(school_id=school.id, college_code="004")
    c2 = College(school_id=school.id, college_code="048")
    empty_db.add_all([c1, c2])
    empty_db.flush()
    p1 = Program(college_id=c1.id, program_code="085410")
    p2 = Program(college_id=c2.id, program_code="085410")
    empty_db.add_all([p1, p2])
    empty_db.commit()
    return {"school": school.id, "colleges": (c1.id, c2.id), "programs": (p1.id, p2.id)}


def test_20_reimport_is_idempotent(db, tmp_path):
    """重复导入同一版本不应产生重复记录。"""
    counts_before = {
        "AdmissionPath": db.query(AdmissionPath).count(),
        "Indicator": db.query(Indicator).count(),
        "EvidenceClaim": db.query(EvidenceClaim).count(),
        "EvidenceSource": db.query(EvidenceSource).count(),
        "ScoreRecord": db.query(ScoreRecord).count(),
        "WeightNode": db.query(WeightNode).count(),
        "ClaimIndicatorLink": db.query(ClaimIndicatorLink).count(),
    }
    assert counts_before["AdmissionPath"] == 10
    assert counts_before["Indicator"] == 33
    assert counts_before["ScoreRecord"] == 180

    report = ExcelImporter(db).run(RAW_XLSX)
    db.commit()
    assert report.replayed is True
    assert all(v == 0 for v in report.inserted.values()), report.inserted

    counts_after = {
        "AdmissionPath": db.query(AdmissionPath).count(),
        "Indicator": db.query(Indicator).count(),
        "EvidenceClaim": db.query(EvidenceClaim).count(),
        "EvidenceSource": db.query(EvidenceSource).count(),
        "ScoreRecord": db.query(ScoreRecord).count(),
        "WeightNode": db.query(WeightNode).count(),
        "ClaimIndicatorLink": db.query(ClaimIndicatorLink).count(),
    }
    assert counts_before == counts_after


def test_20b_import_batch_recorded_once(db):
    batches = db.query(ImportBatch).all()
    assert len(batches) == 1
    assert batches[0].report is not None
    assert "inserted" in batches[0].report


def test_21_different_years_do_not_overwrite(empty_db, orgs):
    """不同招生年份分别记录，互不覆盖。"""
    k2027 = build_path_key(admission_year=2027, **BASE)
    k2028 = build_path_key(admission_year=2028, **BASE)
    assert k2027 != k2028
    p1 = AdmissionPath(path_key=k2027, school_id=orgs["school"], college_id=orgs["colleges"][0],
                       program_id=orgs["programs"][0], admission_year=2027)
    p2 = AdmissionPath(path_key=k2028, school_id=orgs["school"], college_id=orgs["colleges"][0],
                       program_id=orgs["programs"][0], admission_year=2028)
    empty_db.add_all([p1, p2])
    empty_db.commit()
    assert empty_db.query(AdmissionPath).count() == 2
    assert parse_path_key(k2027)["admission_year"] == "2027"
    assert parse_path_key(k2028)["admission_year"] == "2028"


def test_21b_admission_records_separate_methods_and_basis(empty_db, orgs):
    """统考 / 推免 / 专项计划 与 计划数 / 实际录取数 分离。"""
    path = AdmissionPath(
        path_key=build_path_key(admission_year=2027, **BASE),
        school_id=orgs["school"], college_id=orgs["colleges"][0],
        program_id=orgs["programs"][0], admission_year=2027,
    )
    empty_db.add(path)
    empty_db.commit()
    rows = [
        AdmissionRecord(path_id=path.id, year=2027, admission_method=AdmissionMethod.UNIFIED_EXAM,
                        quota_basis="目录计划", planned_quota=68),
        AdmissionRecord(path_id=path.id, year=2027, admission_method=AdmissionMethod.UNIFIED_EXAM,
                        quota_basis="复试统考计划", planned_quota=40),
        AdmissionRecord(path_id=path.id, year=2027, admission_method=AdmissionMethod.RECOMMENDED,
                        quota_basis="实际录取", actual_admitted=28),
    ]
    empty_db.add_all(rows)
    empty_db.commit()
    assert empty_db.query(AdmissionRecord).count() == 3
    unified = (
        empty_db.query(AdmissionRecord)
        .filter(AdmissionRecord.admission_method == AdmissionMethod.UNIFIED_EXAM)
        .all()
    )
    assert len(unified) == 2


def test_22_different_colleges_not_confused(empty_db, orgs):
    """同一专业代码在不同学院应为不同路径，不得混淆。"""
    k_a = build_path_key(admission_year=2028, **{**BASE, "college_code": "004"})
    k_b = build_path_key(admission_year=2028, **{**BASE, "college_code": "048"})
    assert k_a != k_b
    empty_db.add_all(
        [
            AdmissionPath(path_key=k_a, school_id=orgs["school"],
                          college_id=orgs["colleges"][0], program_id=orgs["programs"][0],
                          admission_year=2028),
            AdmissionPath(path_key=k_b, school_id=orgs["school"],
                          college_id=orgs["colleges"][1], program_id=orgs["programs"][1],
                          admission_year=2028),
        ]
    )
    empty_db.commit()
    assert empty_db.query(AdmissionPath).count() == 2
    assert {p.college_id for p in empty_db.query(AdmissionPath).all()} == set(orgs["colleges"])


def test_22b_same_school_multiple_colleges_present(db):
    """导入结果中同一学校存在多个招生学院。"""
    from decision_system.models.entities import College, School

    schools = db.query(School).all()
    assert len(schools) == 5
    hfut = db.query(School).filter(School.name == "合肥工业大学").one()
    colleges = db.query(College).filter(College.school_id == hfut.id).all()
    assert len(colleges) >= 3


def test_23_first_choice_and_adjustment_not_confused(empty_db, orgs):
    """调剂与一志愿记录不得混淆。"""
    k_first = build_path_key(admission_year=2028, **{**BASE, "path_kind": PathKind.FIRST_CHOICE})
    k_adj = build_path_key(admission_year=2028, **{**BASE, "path_kind": PathKind.ADJUSTMENT})
    assert k_first != k_adj
    empty_db.add_all(
        [
            AdmissionPath(path_key=k_first, school_id=orgs["school"],
                          college_id=orgs["colleges"][0], program_id=orgs["programs"][0],
                          admission_year=2028, path_kind=PathKind.FIRST_CHOICE),
            AdmissionPath(path_key=k_adj, school_id=orgs["school"],
                          college_id=orgs["colleges"][0], program_id=orgs["programs"][0],
                          admission_year=2028, path_kind=PathKind.ADJUSTMENT),
        ]
    )
    empty_db.commit()
    first = (
        empty_db.query(AdmissionPath).filter(AdmissionPath.path_kind == PathKind.FIRST_CHOICE).all()
    )
    adj = empty_db.query(AdmissionPath).filter(AdmissionPath.path_kind == PathKind.ADJUSTMENT).all()
    assert len(first) == 1 and len(adj) == 1
    assert parse_path_key(adj[0].path_key)["path_kind"] == "调剂"


def test_imported_scores_all_unknown(db):
    """导入阶段所有评分保持未知，不以缺失补零。"""
    records = db.query(ScoreRecord).all()
    assert len(records) == 180
    assert all(r.raw_score is None for r in records)
    assert all(r.validity is ScoreValidity.UNKNOWN for r in records)


def test_imported_claims_are_candidates(db):
    """候选证据映射导入后仍是候选，不会被自动升级为已核验。"""
    claims = db.query(EvidenceClaim).all()
    assert len(claims) > 0
    assert all(c.is_candidate is True for c in claims)
    assert all(c.status in (ClaimStatus.CANDIDATE, ClaimStatus.CONFLICT) for c in claims)


def test_imported_sources_not_verified(db):
    """Excel 中未登记/引用来源不得为已核验。"""
    sources = db.query(EvidenceSource).all()
    assert len(sources) > 0
    assert all(s.verification_status is not VerificationStatus.VERIFIED for s in sources)


def test_placeholder_source_registered(db):
    src = db.query(EvidenceSource).filter(EvidenceSource.source_id == "SRC-NA").one()
    assert src.is_placeholder is True
    assert src.verification_status is VerificationStatus.UNREGISTERED


def test_open_questions_and_audit_logged(db):
    logs = db.query(AuditLog).filter(AuditLog.action == "import.open_question").all()
    assert len(logs) >= 7
