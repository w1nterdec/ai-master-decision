"""Task C 服务层集成测试：来源登记 / 核验 / 驳回 / 冲突 / 缺口统计口径。

数据库：临时 SQLite（mutating_db 夹具），不触碰正式库。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from decision_system.evidence.registry import EvidenceGovernanceError
from decision_system.models.entities import (
    AdmissionPath,
    AuditLog,
    ClaimConflict,
    EvidenceClaim,
    EvidenceSource,
    Indicator,
    ScoreRecord,
)
from decision_system.models.enums import ClaimStatus, VerificationStatus
from decision_system.services.decision_service import (
    build_engine,
    path_context_from_db,
)
from decision_system.services.evidence_service import (
    approve_claim,
    attach_claim_to_indicator,
    attach_claim_to_path,
    create_claim,
    evidence_gap_stats,
    is_registered_source,
    is_placeholder_record,
    is_verified_source,
    mark_conflict,
    register_source_strict,
    reject_claim,
    submit_for_verification,
    verification_history,
    verify_source,
)


def _first_path(session):
    return session.execute(select(AdmissionPath).order_by(AdmissionPath.id)).scalars().first()


def _first_leaf(session):
    return (
        session.execute(
            select(Indicator).where(Indicator.level == 3).order_by(Indicator.sort_order)
        )
        .scalars()
        .first()
    )


# ---------------------------------------------------------------------------
# 4 / 5. 来源登记
# ---------------------------------------------------------------------------
def test_register_source_success(mutating_db):
    src = register_source_strict(
        mutating_db,
        source_id="T-SRC-001",
        title="测试来源：某校 2028 硕士招生目录",
        publisher="某校研究生院",
        url_or_file="https://example.edu/2028",
        published_year=2027,
        applicable_years=[2028],
        actor="tester",
    )
    mutating_db.commit()
    assert src.source_id == "T-SRC-001"
    assert src.verification_status is VerificationStatus.PENDING  # 登记 ≠ 已核验
    assert is_registered_source(src) is True
    assert is_verified_source(src) is False


def test_duplicate_source_id_rejected(mutating_db):
    register_source_strict(
        mutating_db,
        source_id="T-DUP",
        title="第一次登记",
        publisher="机构",
        url_or_file="https://example.edu/1",
        actor="tester",
    )
    mutating_db.commit()
    with pytest.raises(EvidenceGovernanceError, match="拒绝重复登记"):
        register_source_strict(
            mutating_db,
            source_id="T-DUP",
            title="第二次登记",
            publisher="机构2",
            url_or_file="https://example.edu/2",
            actor="tester",
        )
    rows = mutating_db.execute(
        select(EvidenceSource).where(EvidenceSource.source_id == "T-DUP")
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "第一次登记"  # 未被覆盖


def test_register_source_requires_identifiable_body(mutating_db):
    with pytest.raises(EvidenceGovernanceError):
        register_source_strict(mutating_db, source_id="T-NOBODY", title="无本体来源", actor="tester")


def test_src_na_placeholder_id_rejected(mutating_db):
    with pytest.raises(EvidenceGovernanceError, match="系统占位"):
        register_source_strict(
            mutating_db, source_id="SRC-NA", title="x", url_or_file="https://a.b", actor="tester"
        )


# ---------------------------------------------------------------------------
# 6. 来源占位符不能直接成为已核验来源
# ---------------------------------------------------------------------------
def test_placeholder_source_cannot_be_verified(mutating_db):
    row = (
        mutating_db.execute(
            select(EvidenceSource).where(EvidenceSource.source_id == "SRC-NA")
        )
        .scalars()
        .one()
    )
    assert is_placeholder_record(row) is True
    with pytest.raises(EvidenceGovernanceError, match="占位符"):
        verify_source(mutating_db, "SRC-NA", actor="tester", basis="尝试直接核验占位符")
    assert row.verification_status is not VerificationStatus.VERIFIED


def test_quoted_reference_source_is_not_registered(mutating_db):
    """（引用自 …）式记录虽有 source_id，也不得视为已登记。"""
    row = (
        mutating_db.execute(
            select(EvidenceSource).where(EvidenceSource.source_id == "S-BUPT-J1")
        )
        .scalars()
        .one()
    )
    assert row.verification_status is VerificationStatus.UNREGISTERED
    assert is_registered_source(row) is False


# ---------------------------------------------------------------------------
# 7. 核验必须记录依据
# ---------------------------------------------------------------------------
def test_verification_requires_actor_and_basis(mutating_db):
    register_source_strict(
        mutating_db,
        source_id="T-VERIFY",
        title="待核验来源",
        publisher="机构",
        url_or_file="https://example.edu/v",
        applicable_years=[2028],
        actor="tester",
    )
    claim = create_claim(
        mutating_db, source_id="T-VERIFY", statement="测试声明", applicable_years=[2028]
    )
    mutating_db.commit()

    with pytest.raises(EvidenceGovernanceError, match="核验依据"):
        approve_claim(mutating_db, claim.id, actor="tester", basis="")
    with pytest.raises(EvidenceGovernanceError, match="actor"):
        approve_claim(mutating_db, claim.id, actor="", basis="有依据")

    approve_claim(
        mutating_db,
        claim.id,
        actor="张三",
        basis="对照原文第 3 页确认",
        applicable_years=[2028],
    )
    mutating_db.commit()

    logs = (
        mutating_db.execute(
            select(AuditLog).where(
                AuditLog.action == "claim.verify", AuditLog.entity_id == str(claim.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    detail = logs[0].detail
    assert detail["actor"] == "张三"
    assert detail["basis"] == "对照原文第 3 页确认"
    assert logs[0].at is not None  # 核验时间
    assert logs[0].actor == "张三"


def test_submit_and_reject_flow(mutating_db):
    register_source_strict(
        mutating_db,
        source_id="T-FLOW",
        title="流程测试来源",
        publisher="机构",
        url_or_file="https://example.edu/f",
        applicable_years=[2028],
        actor="tester",
    )
    claim = create_claim(
        mutating_db, source_id="T-FLOW", statement="流程测试声明", applicable_years=[2028]
    )
    mutating_db.commit()
    assert claim.status is ClaimStatus.CANDIDATE

    submit_for_verification(mutating_db, claim.id, actor="tester", note="进入核验队列")
    mutating_db.commit()
    assert claim.status is ClaimStatus.PENDING
    assert claim.is_candidate is True  # 提交核验 ≠ 已核验

    approve_claim(mutating_db, claim.id, actor="tester", basis="依据 A", applicable_years=[2028])
    mutating_db.commit()
    assert claim.status is ClaimStatus.VERIFIED and claim.is_candidate is False

    reject_claim(mutating_db, claim.id, actor="李四", reason="依据不足")
    mutating_db.commit()
    assert claim.status is ClaimStatus.PENDING
    assert claim.is_candidate is True
    hist = verification_history(mutating_db, claim.id)
    assert any(h["action"] == "claim.reject" and h["detail"].get("reason") == "依据不足" for h in hist)


def test_conflict_blocks_and_does_not_overwrite(mutating_db):
    register_source_strict(
        mutating_db,
        source_id="T-CONF",
        title="冲突测试来源",
        publisher="机构",
        url_or_file="https://example.edu/c",
        applicable_years=[2028],
        actor="tester",
    )
    c1 = create_claim(mutating_db, source_id="T-CONF", statement="声明 A：招 30 人")
    c2 = create_claim(mutating_db, source_id="T-CONF", statement="声明 B：招 50 人")
    mutating_db.commit()
    approve_claim(mutating_db, c1.id, actor="tester", basis="依据 X", applicable_years=[2028])
    mutating_db.commit()

    cf = mark_conflict(
        mutating_db, c2.id, actor="tester", description="人数口径不一致", conflicting_claim_id=c1.id
    )
    mutating_db.commit()
    assert cf.resolved is False
    assert c2.status is ClaimStatus.CONFLICT
    assert c1.status is ClaimStatus.VERIFIED  # 旧事实未被覆盖
    assert c1.statement == "声明 A：招 30 人"


# ---------------------------------------------------------------------------
# 8. 无效来源无法参与评分
# ---------------------------------------------------------------------------
def test_invalid_source_cannot_participate_in_scoring(mutating_db):
    path = _first_path(mutating_db)
    leaf = _first_leaf(mutating_db)
    register_source_strict(
        mutating_db,
        source_id="T-GATE",
        title="闸门测试来源",
        publisher="机构",
        url_or_file="https://example.edu/g",
        applicable_years=[2028],
        actor="tester",
    )
    claim = create_claim(
        mutating_db, source_id="T-GATE", statement="闸门测试声明", applicable_years=[2028]
    )
    mutating_db.flush()
    attach_claim_to_path(mutating_db, claim.id, path.id)
    attach_claim_to_indicator(mutating_db, claim.id, leaf.id)
    sr = mutating_db.execute(
        select(ScoreRecord).where(
            ScoreRecord.path_id == path.id, ScoreRecord.indicator_id == leaf.id
        )
    ).scalars().one()
    sr.raw_score = 4
    sr.source_ref_id = "T-GATE"
    sr.claim_id = claim.id
    mutating_db.commit()

    # 来源未核验 + 声明为候选映射 → 不得进入评分
    engine = build_engine(mutating_db)
    d1 = engine.evaluate(path_context_from_db(mutating_db, path))
    assert d1.base.valid_count == 0, "未核验来源的评分不得生效"

    # 完成核验后 → 该评分生效
    verify_source(mutating_db, "T-GATE", actor="tester", basis="已核对原文")
    approve_claim(mutating_db, claim.id, actor="tester", basis="已核对原文", applicable_years=[2028])
    mutating_db.commit()

    engine2 = build_engine(mutating_db)
    d2 = engine2.evaluate(path_context_from_db(mutating_db, path))
    assert d2.base.valid_count >= 1, "已核验证据应进入评分"


# ---------------------------------------------------------------------------
# C4 缺口统计口径
# ---------------------------------------------------------------------------
def test_gap_stats_definitions(mutating_db):
    g = evidence_gap_stats(mutating_db)
    assert g["source_total"] == 84
    assert g["source_registered"] == 0  # 83 条引用式 + 1 条 SRC-NA 占位符
    assert g["source_placeholder"] == 84
    assert g["source_verified"] == 0
    assert g["claim_total"] == 48
    assert g["claim_candidate"] == 48
    assert g["claim_verified"] == 0
    assert g["pending_verification"] == 48
    assert g["conflict_total"] == 0
    assert g["definitions"]["source_registered"].startswith("非占位符")
