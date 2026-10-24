"""Phase 5.0｜北邮（BUPT）真实招生数据迁移的验收测试。

测试原则（对应任务书 Task G 的 8 项验收）：
    1.  幂等：迁移脚本重复执行，24 张表计数完全不变；
    2.  年份 / 方向 / 考试科目不得混淆；
    3.  名额口径与「实际录取」不得混淆；
    4.  未核验证据不得进入评分（闸门实测）；
    5.  不得出现伪造的 2028 已确认记录；
    6.  其他 4 所学校完全未被改动；
    7.  权重与演示权重完全未被改动；
    8.  历史候选映射既未被删除、也未被自动升级。

**重要区分**：本文件只验证「工程行为」是否正确（迁移是否合规、闸门是否生效）。
测试通过**不能**证明任何真实招生事实为真——真实事实的真伪由官方原文与人工复核决定。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from decision_system.evidence.gate import ScoreInput, StrictEvidenceGate
from decision_system.models import entities  # noqa: F401
from decision_system.models.entities import (
    AdmissionPath,
    AuditLog,
    ClaimPathLink,
    EvidenceClaim,
    EvidenceSource,
    ScoreRecord,
)
from decision_system.models.enums import ClaimStatus, VerificationStatus
from decision_system.models.base import Base
from decision_system.services.db import init_db
from decision_system.services.decision_service import SqlAlchemyEvidenceResolver

ROOT = Path(__file__).resolve().parents[2]
PROD_DB = ROOT / "data" / "decision.db"

P01 = "BUPT|005|085410|全日制|方向01|2028|统考|一志愿"
P02 = "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"
SRC_CATALOG = "S-BUPT-2027-CATALOG-005"
SRC_ADJ = "S-BUPT-2027-EXAMADJ"
SRC_COLLEGE = "S-BUPT-AI-COLLEGE-SITE"
IND_EXAM = "L3-报考可行性|考试风险|初复试科目稳定性"
IND_QUOTA = "L3-报考可行性|招生路径|名额口径可靠性"


def _load_migration_module():
    import importlib.util

    path = ROOT / "scripts" / "migrate_bupt_phase5_0.py"
    spec = importlib.util.spec_from_file_location("mig_bupt_phase5_0", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory, research_baseline_db) -> Path:
    """把正式库复制到临时目录后执行迁移，绝不污染 data/decision.db。"""
    d = tmp_path_factory.mktemp("phase5_0")
    db = d / "decision.db"
    shutil.copy2(research_baseline_db, db)

    mod = _load_migration_module()
    old_db, old_backup, old_report = mod.DB_PATH, mod.BACKUP_PATH, mod.REPORT_PATH
    mod.DB_PATH = db
    mod.BACKUP_PATH = d / "backup" / "decision.db.bak_phase5_0"
    mod.REPORT_PATH = d / "migration.json"
    try:
        mod.run(apply=True)
        mod.run(apply=True)  # 第二次执行用于幂等验证
    finally:
        mod.DB_PATH, mod.BACKUP_PATH, mod.REPORT_PATH = old_db, old_backup, old_report
    return db


@pytest.fixture(scope="module")
def session_factory(migrated_db: Path):
    engine = create_engine(f"sqlite:///{migrated_db}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory
    engine.dispose()


@pytest.fixture()
def sess(session_factory) -> Iterator:
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


def _counts(db_path: Path) -> dict[str, int]:
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                text("select name from sqlite_master where type='table' order by name")
            )
        ]
        out = {t: conn.execute(text(f'select count(*) from "{t}"')).scalar() for t in tables}
    engine.dispose()
    return out


# ---------------------------------------------------------------------------
# 1. 幂等
# ---------------------------------------------------------------------------
def test_01_migration_is_idempotent(migrated_db: Path):
    """第二次执行后，24 张表的行数与第一次执行后完全一致（含审计表）。"""
    before = _counts(migrated_db)
    mod = _load_migration_module()
    old_db, old_backup, old_report = mod.DB_PATH, mod.BACKUP_PATH, mod.REPORT_PATH
    mod.DB_PATH = migrated_db
    mod.BACKUP_PATH = migrated_db.parent / "backup" / "decision.db.bak_phase5_0"
    mod.REPORT_PATH = migrated_db.parent / "migration2.json"
    try:
        res = mod.run(apply=True)
    finally:
        mod.DB_PATH, mod.BACKUP_PATH, mod.REPORT_PATH = old_db, old_backup, old_report
    assert res["before"] == res["after"], "重复执行后计数发生了变化，迁移不幂等"
    assert _counts(migrated_db) == before


# ---------------------------------------------------------------------------
# 2. 来源登记：本体完整 + 核验依据
# ---------------------------------------------------------------------------
def test_02_sources_have_real_body_and_basis(sess):
    for sid in (SRC_CATALOG, SRC_ADJ, SRC_COLLEGE):
        src = sess.execute(
            select(EvidenceSource).where(EvidenceSource.source_id == sid)
        ).scalar_one_or_none()
        assert src is not None, f"来源未登记：{sid}"
        assert src.url_or_file and src.publisher, f"来源缺本体（URL/发布机构）：{sid}"
        assert not src.is_placeholder

    for sid, date_str in ((SRC_CATALOG, "2026-10-04"), (SRC_ADJ, "2026-06-09")):
        src = sess.execute(
            select(EvidenceSource).where(EvidenceSource.source_id == sid)
        ).scalar_one()
        assert src.verification_status is VerificationStatus.VERIFIED
        # 已核验必须有核验依据，且依据里写明原文日期与自洽校验/落款
        assert src.verification_note and date_str in src.verification_note
        assert src.published_at is not None and str(src.published_at) == date_str
        assert src.applicable_years == [2027], "官方事实适用年份必须是 2027，不得写成 2028"

    college = sess.execute(
        select(EvidenceSource).where(EvidenceSource.source_id == SRC_COLLEGE)
    ).scalar_one()
    # 未取得原文的官方指引页，必须保持待核验，不得标为已核验
    assert college.verification_status is not VerificationStatus.VERIFIED
    assert "HTTP 412" in (college.verification_note or "")


# ---------------------------------------------------------------------------
# 3. 年份 / 方向 / 考试科目不得混淆
# ---------------------------------------------------------------------------
def test_03_direction_and_exam_subject_not_confused(sess):
    def claims_of(path_key: str) -> list[EvidenceClaim]:
        p = sess.execute(
            select(AdmissionPath).where(AdmissionPath.path_key == path_key)
        ).scalar_one()
        links = sess.execute(
            select(ClaimPathLink).where(ClaimPathLink.path_id == p.id)
        ).scalars().all()
        return [sess.get(EvidenceClaim, l.claim_id) for l in links]

    c01 = [c for c in claims_of(P01) if c.source_ref_id == SRC_CATALOG and "方向" in (c.statement or "")]
    c02 = [c for c in claims_of(P02) if c.source_ref_id == SRC_CATALOG and "方向" in (c.statement or "")]
    dir01 = [c for c in c01 if "方向『01" in (c.statement or "")]
    dir02 = [c for c in c02 if "方向『02" in (c.statement or "")]
    assert dir01 and dir02

    # 方向01 声明只挂方向01 路径；方向02 声明只挂方向02 路径（不得交叉）
    dir01_ids = {c.id for c in dir01}
    dir02_ids = {c.id for c in dir02}
    assert dir01_ids.isdisjoint(dir02_ids)
    for c in dir01:
        assert "801" in c.statement and "408" not in c.statement
    for c in dir02:
        assert "408" in c.statement and "801" not in c.statement

    # 任何已核验的北邮官方声明，适用年份都不得写成 2028
    for c in sess.execute(select(EvidenceClaim)).scalars().all():
        if c.source_ref_id in (SRC_CATALOG, SRC_ADJ) and c.status is ClaimStatus.VERIFIED:
            assert c.applicable_years == [2027], f"声明 #{c.id} 年份被错误标注为 {c.applicable_years}"


# ---------------------------------------------------------------------------
# 4. 名额口径不得与「实际录取」混淆
# ---------------------------------------------------------------------------
def test_04_quota_caliber_not_confused_with_actual_admission(sess):
    quota_claims = [
        c
        for c in sess.execute(select(EvidenceClaim)).scalars().all()
        if c.source_ref_id == SRC_CATALOG and ("43" in c.statement or "89" in c.statement or "132" in c.statement)
    ]
    assert quota_claims, "未登记任何名额声明"
    for c in quota_claims:
        assert "目录计划数" in c.statement and "含推免" in c.statement, (
            f"声明 #{c.id} 未标注名额口径，存在‘目录计划 / 统考计划 / 实际录取’混淆风险"
        )

    # 不得出现「统考计划 N 人」「实际录取 N 人」这类未经取得的数字
    pattern = re.compile(r"(统考计划|实际录取|实录|录取人数)\s*[:：为]?\s*\d+")
    for c in sess.execute(select(EvidenceClaim)).scalars().all():
        if c.source_ref_id in (SRC_CATALOG, SRC_ADJ, SRC_COLLEGE):
            assert not pattern.search(c.statement or ""), (
                f"声明 #{c.id} 出现了未取得来源支撑的招生/录取数字"
            )

    # 未取得的实际录取数据不得零填充
    assert sess.execute(text("select count(*) from admission_record")).scalar() == 0


# ---------------------------------------------------------------------------
# 5. 未核验证据不得进入评分（闸门实测）
# ---------------------------------------------------------------------------
def test_05_unverified_evidence_rejected_by_gate(sess):
    resolver = SqlAlchemyEvidenceResolver(sess)
    gate = StrictEvidenceGate(resolver)

    # 5a 已核验的 2027 官方证据，在评价年份 2027 下通过
    ok = gate.validate(
        ScoreInput(indicator_code=IND_EXAM, raw_score=4, source_id=SRC_CATALOG, path_key=P01),
        evaluation_year=2027,
    )
    assert ok.is_valid, f"2027 已核验证据应通过闸门，实际：{ok.reasons}"

    # 5b 同一条证据在评价年份 2028 下必须被年份闸门拒绝（不得泄漏为 2028 结论）
    bad = gate.validate(
        ScoreInput(indicator_code=IND_EXAM, raw_score=4, source_id=SRC_CATALOG, path_key=P01),
        evaluation_year=2028,
    )
    assert not bad.is_valid
    assert any("年份" in r for r in bad.reasons), f"应因年份不匹配被拒，实际：{bad.reasons}"

    # 5c 未核验来源（学院官网指引页）一律拒绝
    pend = gate.validate(
        ScoreInput(indicator_code=IND_EXAM, raw_score=4, source_id=SRC_COLLEGE, path_key=P01),
        evaluation_year=2027,
    )
    assert not pend.is_valid
    assert any("核验状态" in r for r in pend.reasons)

    # 5d 待核验声明（C7 口径差异 / C8 2028 推断）不得被视为已核验
    pend_claims = [
        c
        for c in sess.execute(select(EvidenceClaim)).scalars().all()
        if c.source_ref_id in (SRC_CATALOG, SRC_ADJ) and c.status is ClaimStatus.PENDING
    ]
    assert len(pend_claims) >= 2
    for c in pend_claims:
        assert c.is_candidate is True, f"待核验声明 #{c.id} 的候选标记被错误清除"


# ---------------------------------------------------------------------------
# 6. 不得出现伪造的 2028 已确认记录
# ---------------------------------------------------------------------------
def test_06_no_fake_2028_confirmation(sess):
    bupt = sess.execute(
        select(AdmissionPath).where(AdmissionPath.path_key.like("BUPT|%"))
    ).scalars().all()
    assert len(bupt) == 2, "迁移不得新增或删除北邮路径"
    for p in bupt:
        assert p.admission_year == 2028
        assert str(p.verification_2028) == "待2028核验", (
            f"路径 {p.path_key} 的 2028 核验状态被改动为 {p.verification_2028}"
        )

    # 不存在「适用 2028 且已核验」的事实声明
    for c in sess.execute(select(EvidenceClaim)).scalars().all():
        if 2028 in (c.applicable_years or []):
            assert c.status is not ClaimStatus.VERIFIED, f"声明 #{c.id} 伪造了 2028 已确认"

    # 2028 推断条目必须自我标注为推断
    inferred = [
        c
        for c in sess.execute(select(EvidenceClaim)).scalars().all()
        if 2028 in (c.applicable_years or []) and c.source_ref_id == SRC_CATALOG
    ]
    assert inferred and all("推断" in (c.statement or "") for c in inferred)


# ---------------------------------------------------------------------------
# 7. 其他 4 所学校完全未被改动
# ---------------------------------------------------------------------------
def test_07_other_schools_untouched(migrated_db: Path, research_baseline_db):
    def snapshot(path: Path) -> dict:
        engine = create_engine(f"sqlite:///{path}", future=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "select path_key, admission_year, study_mode, direction, exam_unit4, "
                    "verification_2028, key_risk, notes from admission_path order by id"
                )
            ).all()
            scores = conn.execute(
                text("select path_id, indicator_id, evaluation_year, raw_score, validity from score_record order by id")
            ).all()
        engine.dispose()
        return {"paths": [tuple(r) for r in rows], "scores": [tuple(r) for r in scores]}

    before, after = snapshot(research_baseline_db), snapshot(migrated_db)
    non_bupt_before = [r for r in before["paths"] if not r[0].startswith("BUPT|")]
    non_bupt_after = [r for r in after["paths"] if not r[0].startswith("BUPT|")]
    assert non_bupt_before == non_bupt_after, "其他学校的路径记录被改动"
    assert len(non_bupt_after) == 8

    # 评分记录一条都没变（迁移不触发评分）
    assert before["scores"] == after["scores"]
    assert len(after["scores"]) == 180


# ---------------------------------------------------------------------------
# 8. 权重与演示权重完全未被改动
# ---------------------------------------------------------------------------
def test_08_weights_untouched(migrated_db: Path, research_baseline_db):
    def snap(path: Path):
        engine = create_engine(f"sqlite:///{path}", future=True)
        with engine.connect() as conn:
            prof = conn.execute(
                text("select code, name, is_demo, description from weight_profile order by id")
            ).all()
            nodes = conn.execute(
                text("select profile_id, indicator_id, level, raw_weight from weight_node order by id")
            ).all()
        engine.dispose()
        return [tuple(r) for r in prof], [tuple(r) for r in nodes]

    assert snap(research_baseline_db) == snap(migrated_db), "权重被迁移脚本改动"


# ---------------------------------------------------------------------------
# 9. 历史候选映射：既不删除，也不自动升级
# ---------------------------------------------------------------------------
def test_09_history_candidate_claims_unchanged(migrated_db: Path, research_baseline_db):
    def snap(path: Path) -> dict[int, tuple[str, bool]]:
        engine = create_engine(f"sqlite:///{path}", future=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text("select id, status, is_candidate from evidence_claim order by id")
            ).all()
        engine.dispose()
        return {r[0]: (r[1], bool(r[2])) for r in rows}

    before, after = snap(research_baseline_db), snap(migrated_db)
    for cid, val in before.items():
        assert cid in after, f"历史声明 #{cid} 被删除"
        assert after[cid] == val, f"历史声明 #{cid} 状态被改动：{val} -> {after[cid]}"
    # 历史声明全部保持候选映射，未被自动升级
    assert all(v[0] == "候选映射" for v in before.values())
    assert len(after) == len(before) + 8


# ---------------------------------------------------------------------------
# 10. 路径说明为「追加」而非「覆盖」，且保留原关键风险文本
# ---------------------------------------------------------------------------
def test_10_path_notes_appended_not_overwritten(sess):
    p1 = sess.execute(select(AdmissionPath).where(AdmissionPath.path_key == P01)).scalar_one()
    p2 = sess.execute(select(AdmissionPath).where(AdmissionPath.path_key == P02)).scalar_one()
    assert "历史数据来源为 2026/2027 年度材料" in p1.notes
    assert "历史数据来源为 2026/2027 年度材料" in p2.notes
    assert "原关键风险记录：北邮2027目录原件未取得" in p1.notes
    assert "原关键风险记录：2027改408；原件未取得" in p2.notes
    # 新风险不得声称 2028 已确认
    assert "2028 仍未确认" in (p1.key_risk or "") and "2028 仍未确认" in (p2.key_risk or "")


# ---------------------------------------------------------------------------
# 11. 审计留痕
# ---------------------------------------------------------------------------
def test_11_audit_trail_recorded(sess):
    rows = sess.execute(
        select(AuditLog).where(AuditLog.actor == "phase5.0-bupt")
    ).scalars().all()
    actions = {r.action for r in rows}
    assert {"source.register", "claim.register", "claim.verify"}.issubset(actions)
    assert "path.update" in actions
    assert len(rows) > 0


# ---------------------------------------------------------------------------
# 12. 迁移后北邮 2028 决策输出仍为「不可比较」（不得因新增证据产生虚假置信）
# ---------------------------------------------------------------------------
def test_12_bupt_2028_still_not_comparable(sess):
    from decision_system.engine.pipeline import EngineConfig
    from decision_system.services.decision_service import build_engine, path_context_from_db

    for year in (2027, 2028):
        eng = build_engine(sess, EngineConfig(coverage_threshold=0.8, evaluation_year=year))
        for pk in (P01, P02):
            p = sess.execute(
                select(AdmissionPath).where(AdmissionPath.path_key == pk)
            ).scalar_one()
            res = eng.evaluate(path_context_from_db(sess, p))
            assert str(res.qualification_2028) == "2028资格未确认", (
                f"{pk} 在 {year} 年评价下出现 2028 资格确认：{res.qualification_2028}（属伪造）"
            )
