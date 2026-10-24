from __future__ import annotations

import json
import shutil

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from decision_system.models.entities import WeightNode
from decision_system.services import view_service
from .conftest import all_text, goto


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    path = tmp_path / "personal.json"
    monkeypatch.setattr(view_service, "ARCHIVE_PATH", path)
    return path


def test_guide_navigates_to_personal_form(app_test):
    at = app_test().run()
    at.button(key="onboard_profile").click().run()
    assert not at.exception
    assert at.radio(key="nav_page").value == "⑥ 我的决策档案"
    assert "R7" in all_text(at) and "尚未实现" in all_text(at)


def test_personal_conditions_and_manual_tier_save_with_explanation(
    app_test, isolated_archive
):
    at = goto(app_test(), "⑥ 我的决策档案")
    at.text_input(key="personal_目标方向").set_value("本人的研究方向")
    next(b for b in at.button if b.label == "保存个人条件").click().run()
    assert not at.exception
    assert (
        json.loads(isolated_archive.read_text(encoding="utf-8"))["personal_conditions"][
            "目标方向"
        ]
        == "本人的研究方向"
    )
    at.selectbox(key="planning_tier_1").set_value("保")
    next(b for b in at.button if b.label == "保存人工分层").click().run()
    assert not at.exception
    assert any("请填写分层理由" in e.value for e in at.error)
    at.text_area(key="planning_reason_1").set_value("仅为个人假设，需核验 2028 名额")
    next(b for b in at.button if b.label == "保存人工分层").click().run()
    assert not at.exception
    saved = json.loads(isolated_archive.read_text(encoding="utf-8"))
    assert saved["planning_tiers"] == {"1": "保"}
    assert "未改变任何引擎结论" in all_text(at)


def test_path_explanation_reports_missing_evidence(app_test):
    at = goto(app_test(), "② 院校探索")
    assert not at.exception
    text = all_text(at)
    assert any(e.label == "看懂当前结论：依据、缺口与风险" for e in at.expander)
    assert "低于门槛" in text and "尚缺有效依据的指标" in text


def test_missing_weight_profile_has_recovery_action(app_test):
    at = app_test()
    at.session_state["active_profile"] = "missing-profile"
    at.run()
    assert not at.exception
    assert "当前配置不存在" in all_text(at)
    at.button(key="recover_demo_profile").click().run()
    assert not at.exception
    assert "决策驾驶舱" in all_text(at)


@pytest.mark.parametrize("negative", [True, False])
def test_invalid_or_zero_weights_are_visible(
    app_test, ui_db_path, tmp_path, monkeypatch, negative
):
    path = tmp_path / "weights.db"
    shutil.copy2(ui_db_path, path)
    engine = create_engine(f"sqlite:///{path}")
    with sessionmaker(bind=engine)() as session:
        for node in session.scalars(select(WeightNode).where(WeightNode.level == 1)):
            node.raw_weight = -1 if negative else 0
        session.commit()
    engine.dispose()
    monkeypatch.setenv("DECISION_DB_PATH", str(path))
    at = app_test()
    if negative:
        at.run()
        assert not at.exception
        assert "权重配置异常" in all_text(at)
    else:
        goto(at, "④ 动态决策树")
        assert not at.exception
        assert "权重异常提示" in all_text(at)
