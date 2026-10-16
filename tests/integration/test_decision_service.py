"""数据库驱动的决策引擎集成测试。"""

from __future__ import annotations

import math

import pytest
from sqlalchemy import select

from decision_system.engine.pipeline import EngineConfig
from decision_system.models.entities import AdmissionPath, DecisionResult, Indicator, ScoreRecord
from decision_system.models.enums import (
    ClaimStatus,
    ComparisonStatus,
    ObjectiveStatus,
    Qualification2028,
    VerificationStatus,
)
from decision_system.services.decision_service import (
    build_engine,
    path_context_from_db,
    build_weight_tree,
    evaluate_and_persist,
    to_summary,
)
from decision_system.evidence.registry import (
    link_claim_indicator,
    link_claim_path,
    register_claim,
    register_source,
    verify_claim,
)


def test_build_engine_from_db(mutating_db):
    tree = build_weight_tree(mutating_db, "phase37c_demo")
    assert len(tree.codes(3)) == 18
    assert math.isclose(tree.total_global_weight(), 1.0, abs_tol=1e-12)
    engine = build_engine(mutating_db, EngineConfig())
    assert set(engine.scenarios) == {"career", "admission", "research"}


def test_all_imported_paths_are_undecidable(mutating_db):
    """导入态下不得产生任何评分：所有路径都是待核验 + 无有效证据。"""
    paths = mutating_db.execute(select(AdmissionPath)).scalars().all()
    assert len(paths) == 10
    engine = build_engine(mutating_db, EngineConfig())
    for path in paths:
        decision = engine.evaluate(path_context_from_db(mutating_db, path))
        assert decision.base.weighted_score is None
        assert decision.base.weight_coverage == 0.0
        assert decision.qualification_2028 is not Qualification2028.CONFIRMED
        assert decision.objective_a.score is None
        assert decision.objective_b.score is None
        assert any("录取概率" in x for x in decision.limitations)


def _prepare_verified_evidence(db, legacy_path_id: str = "P01") -> AdmissionPath:
    """为指定路径登记已核验来源、已核验声明，并填入 18 项有效评分。"""
    path = db.execute(
        select(AdmissionPath).where(AdmissionPath.legacy_path_id == legacy_path_id)
    ).scalar_one()

    register_source(
        db,
        source_id="SRC-E2E-001",
        title="2028 年硕士招生专业目录（测试样例）",
        publisher="测试机构",
        url_or_file="file:///sample/2028-catalog.pdf",
        applicable_years=[2028],
        verification_status=VerificationStatus.VERIFIED,
    )
    db.flush()

    indicators = db.execute(select(Indicator).where(Indicator.level == 3)).scalars().all()
    assert len(indicators) == 18

    for ind in indicators:
        claim = register_claim(
            db,
            source_id="SRC-E2E-001",
            statement=f"测试样例：{ind.name} 的可核验证据",
            applicable_years=[2028],
            status=ClaimStatus.CANDIDATE,
            is_candidate=True,
        )
        db.flush()
        verify_claim(db, claim.id, actor="tester", basis="端到端测试：模拟人工核验")
        link_claim_path(db, claim.id, path.id)
        link_claim_indicator(db, claim.id, ind.id)
        db.flush()

    records = db.execute(
        select(ScoreRecord).where(ScoreRecord.path_id == path.id)
    ).scalars().all()
    assert len(records) == 18
    for rec in records:
        rec.raw_score = 4
        rec.source_ref_id = "SRC-E2E-001"
    db.flush()
    return path


def test_end_to_end_pending_hard_constraint_blocks_output(mutating_db):
    """人工核验并填分后覆盖率可达 100%，但硬约束待确认仍不得输出比较分数。"""
    path = _prepare_verified_evidence(mutating_db)
    decision = evaluate_and_persist(mutating_db, path.path_key, EngineConfig())
    mutating_db.commit()

    assert decision.base.weight_coverage == pytest.approx(1.0)
    assert decision.eligibility.value == "待核验"
    assert decision.base.status is ComparisonStatus.PENDING
    assert decision.base.weighted_score is None
    assert decision.objective_a.status is ObjectiveStatus.PENDING_VERIFICATION

    saved = mutating_db.execute(select(DecisionResult)).scalars().all()
    assert len(saved) == 1
    from decision_system.engine.pipeline import assert_no_admission_probability

    assert_no_admission_probability(saved[0].payload)


def test_end_to_end_full_candidate(mutating_db):
    """补齐硬约束后，路径应可比较并输出双目标结论。"""
    path = _prepare_verified_evidence(mutating_db)

    from decision_system.models.enums import TriState, Verification2028

    path.other_constraints_ok = TriState.YES
    path.verification_2028 = Verification2028.VERIFIED
    mutating_db.flush()
    mutating_db.commit()

    decision = evaluate_and_persist(mutating_db, path.path_key, EngineConfig())
    assert decision.eligibility.value == "候选"
    assert decision.base.status is ComparisonStatus.COMPARABLE
    assert decision.base.weighted_score == pytest.approx(4.0)
    assert decision.qualification_2028 is Qualification2028.CONFIRMED
    assert decision.objective_a.status is ObjectiveStatus.AVAILABLE
    assert decision.objective_b.status is ObjectiveStatus.AVAILABLE

    summary = to_summary(decision)
    assert summary["base_score"] == pytest.approx(4.0)
    assert summary["qualification_2028"] == "2028正式资格已确认"
