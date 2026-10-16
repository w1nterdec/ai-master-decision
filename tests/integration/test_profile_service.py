"""Task D 权重服务集成测试：9 调用服务层 / 10 持久化 / 11 恢复默认不破坏历史。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.models.entities import AuditLog, WeightNode, WeightProfile
from decision_system.services import profile_service as ps
from decision_system.services.decision_service import build_weight_tree

DEMO = "phase37c_demo"
L1_CODE = "L1-职业发展"


def _new_session(old: Session) -> Session:
    return Session(old.get_bind(), expire_on_commit=False, future=True)


def _node_value(session, profile_code: str, indicator_code: str) -> float:
    p = session.execute(
        select(WeightProfile).where(WeightProfile.code == profile_code)
    ).scalar_one()
    ind_code = indicator_code
    for n in p.nodes:
        if n.indicator.code == ind_code:
            return float(n.raw_weight)
    raise AssertionError(f"无此节点：{indicator_code}")


def test_09_weight_adjust_goes_through_service_layer(mutating_db, monkeypatch):
    calls: list[dict] = []
    original = ps.update_weight

    def spy(session, **kwargs):
        calls.append(kwargs)
        return original(session, **kwargs)

    monkeypatch.setattr(ps, "update_weight", spy)
    tree = ps.apply_weight_change(
        mutating_db,
        profile_code=DEMO,
        indicator_code=L1_CODE,
        new_raw_weight=50.0,
        actor="tester",
        reason="界面调整",
    )
    assert len(calls) == 1
    assert calls[0]["profile_code"] == DEMO
    assert calls[0]["indicator_code"] == L1_CODE
    assert calls[0]["new_raw_weight"] == 50.0
    assert abs(sum(tree.global_weights().values()) - 1.0) < 1e-9


def test_10_weight_change_is_persisted(mutating_db):
    before = _node_value(mutating_db, DEMO, L1_CODE)
    ps.apply_weight_change(
        mutating_db,
        profile_code=DEMO,
        indicator_code=L1_CODE,
        new_raw_weight=before + 10,
        actor="tester",
        reason="持久化测试",
    )
    mutating_db.commit()

    s2 = _new_session(mutating_db)
    try:
        assert _node_value(s2, DEMO, L1_CODE) == pytest.approx(before + 10)
        logs = s2.execute(
            select(AuditLog).where(AuditLog.action == "weight.update")
        ).scalars().all()
        assert any(
            log.detail.get("indicator_code") == L1_CODE
            and log.detail.get("new_raw_weight") == before + 10
            for log in logs
        )
        tree = build_weight_tree(s2, DEMO)
        assert abs(tree.total_global_weight() - 1.0) < 1e-9
    finally:
        s2.close()


def test_11_restore_default_keeps_history(mutating_db):
    demo_val = _node_value(mutating_db, DEMO, L1_CODE)

    ps.clone_profile(mutating_db, base_code=DEMO, new_code="user_restore_test", name="恢复测试")
    mutating_db.commit()
    ps.apply_weight_change(
        mutating_db, profile_code="user_restore_test", indicator_code=L1_CODE, new_raw_weight=77.0
    )
    mutating_db.commit()
    assert _node_value(mutating_db, "user_restore_test", L1_CODE) == 77.0

    s2 = _new_session(mutating_db)
    history_before = len(
        s2.execute(
            select(AuditLog).where(
                AuditLog.action.in_(["weight.update", "weight.restore", "profile.restore"])
            )
        )
        .scalars()
        .all()
    )
    s2.close()

    restored = ps.restore_from_base(mutating_db, "user_restore_test", base_code=DEMO, actor="tester")
    mutating_db.commit()
    assert restored >= 1
    assert _node_value(mutating_db, "user_restore_test", L1_CODE) == pytest.approx(demo_val)

    s3 = _new_session(mutating_db)
    try:
        rows = (
            s3.execute(
                select(AuditLog).where(
                    AuditLog.action.in_(["weight.update", "weight.restore", "profile.restore"])
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) >= history_before + 2, "恢复操作不得删除历史审计记录"
        assert any(r.action == "weight.update" for r in rows), "原修改记录必须保留"
        assert any(r.action == "weight.restore" for r in rows), "恢复动作需留痕"
        # 演示配置本身不被恢复操作改动
        assert _node_value(s3, DEMO, L1_CODE) == pytest.approx(demo_val)
        assert s3.execute(
            select(WeightProfile).where(WeightProfile.code == DEMO)
        ).scalar_one().is_demo is True
    finally:
        s3.close()


def test_clone_profile_does_not_modify_demo_config(mutating_db):
    before = _node_value(mutating_db, DEMO, L1_CODE)
    p = ps.clone_profile(mutating_db, base_code=DEMO, new_code="user_clone_test", name="用户配置")
    mutating_db.commit()
    assert p.is_demo is False
    assert _node_value(mutating_db, DEMO, L1_CODE) == pytest.approx(before)

    s2 = _new_session(mutating_db)
    try:
        demo_nodes = len(
            s2.execute(
                select(WeightNode).join(WeightProfile).where(WeightProfile.code == DEMO)
            )
            .scalars()
            .all()
        )
        user_nodes = len(
            s2.execute(
                select(WeightNode)
                .join(WeightProfile)
                .where(WeightProfile.code == "user_clone_test")
            )
            .scalars()
            .all()
        )
        assert demo_nodes == user_nodes == 33
    finally:
        s2.close()


def test_profile_service_rejects_unknown_profile(mutating_db):
    with pytest.raises(ps.ProfileServiceError):
        ps.get_profile(mutating_db, "not_exist")
