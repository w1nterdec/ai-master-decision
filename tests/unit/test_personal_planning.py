from __future__ import annotations

import pytest

from decision_system.ui.viewmodels import DecisionArchive
from decision_system.ui.pages_profile import _build_markdown


def test_old_archive_remains_readable():
    archive = DecisionArchive.from_dict({"notes": ["旧档案"], "favorite_path_ids": [1]})
    assert archive.personal_conditions == {} and archive.planning_tiers == {}
    assert archive.notes == ["旧档案"] and archive.favorite_path_ids == [1]


def test_manual_tier_requires_reason_and_clear_reason_removes_tier():
    archive = DecisionArchive(personal_conditions={"目标方向": "机器人"})
    with pytest.raises(ValueError):
        archive.set_planning_tier(1, "保", "   ")
    archive.set_planning_tier(1, "冲", "仍需核验科目与名额")
    restored = DecisionArchive.from_dict(archive.to_dict())
    assert restored.planning_tiers == {"1": "冲"}
    assert restored.personal_conditions == {"目标方向": "机器人"}
    restored.set_note(1, "")
    assert restored.planning_tiers == {}


def test_export_distinguishes_user_hypothesis_from_engine():
    archive = DecisionArchive(personal_conditions={"本科专业": "本人专业"})
    archive.set_planning_tier(1, "稳", "个人计划，等待官方证据")
    text = _build_markdown([], archive, [], profile_code="phase37c_demo")
    assert "本人专业" in text and "信息与计算科学" not in text
    assert "人工假设" in text and "非系统推荐" in text
    assert "个人计划，等待官方证据" in text
