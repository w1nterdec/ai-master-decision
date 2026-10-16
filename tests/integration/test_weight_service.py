"""权重修改落库与审计测试（Task C2：保留权重修改记录）。"""

from __future__ import annotations

import math

import pytest

from decision_system.engine.weights import NegativeWeightError
from decision_system.models.entities import AuditLog
from decision_system.services.decision_service import build_weight_tree
from decision_system.services.weight_service import update_weight, weight_change_history

L1_CAREER = "L1-职业发展"
L3_JOB = "L3-职业发展|AI工程就业|岗位与实习机会"


def test_weight_update_persisted_and_audited(mutating_db):
    before = build_weight_tree(mutating_db, "phase37c_demo")
    tree = update_weight(
        mutating_db,
        profile_code="phase37c_demo",
        indicator_code=L1_CAREER,
        new_raw_weight=50.0,
        actor="test-user",
        reason="提高职业发展权重",
    )
    after = build_weight_tree(mutating_db, "phase37c_demo")

    # 落库生效
    assert math.isclose(after.global_weight(L3_JOB), tree.global_weight(L3_JOB), rel_tol=1e-12)
    assert after.global_weight(L3_JOB) > before.global_weight(L3_JOB)
    # 仍然归一化
    assert math.isclose(after.total_global_weight(), 1.0, abs_tol=1e-12)

    history = weight_change_history(mutating_db, "phase37c_demo")
    assert len(history) == 1
    assert history[0]["actor"] == "test-user"
    assert history[0]["old_raw_weight"] == 35.0
    assert history[0]["new_raw_weight"] == 50.0
    assert history[0]["still_demo_config"] is True


def test_weight_update_rejects_negative(mutating_db):
    with pytest.raises(NegativeWeightError):
        update_weight(
            mutating_db,
            profile_code="phase37c_demo",
            indicator_code=L1_CAREER,
            new_raw_weight=-10.0,
        )
    mutating_db.rollback()
    # 拒绝后不得留下非法中间态
    assert weight_change_history(mutating_db, "phase37c_demo") == []
    tree = build_weight_tree(mutating_db, "phase37c_demo")
    assert math.isclose(tree.global_weight(L3_JOB), 0.105, rel_tol=1e-12)


def test_weight_update_unknown_indicator(mutating_db):
    with pytest.raises(ValueError):
        update_weight(
            mutating_db,
            profile_code="phase37c_demo",
            indicator_code="L1-不存在的指标",
            new_raw_weight=10.0,
        )


def test_level3_weight_update_propagates(mutating_db):
    tree = update_weight(
        mutating_db,
        profile_code="phase37c_demo",
        indicator_code=L3_JOB,
        new_raw_weight=90.0,
        actor="test-user",
    )
    sibling = "L3-职业发展|AI工程就业|产业合作可参与性"
    assert tree.global_weight(L3_JOB) > tree.global_weight(sibling)
    assert math.isclose(tree.total_global_weight(), 1.0, abs_tol=1e-12)


def test_hard_constraint_evaluation_persisted(mutating_db):
    from sqlalchemy import select

    from decision_system.engine.pipeline import EngineConfig
    from decision_system.models.entities import AdmissionPath, HardConstraintEvaluation
    from decision_system.services.decision_service import evaluate_and_persist

    path = mutating_db.execute(
        select(AdmissionPath).where(AdmissionPath.legacy_path_id == "P01")
    ).scalar_one()
    evaluate_and_persist(mutating_db, path.path_key, EngineConfig())
    mutating_db.commit()
    rows = mutating_db.execute(select(HardConstraintEvaluation)).scalars().all()
    assert len(rows) == 1
    assert rows[0].eligibility.value == "待核验"
    assert rows[0].qualification_2028.value == "2028资格未确认"
    assert rows[0].reasons
