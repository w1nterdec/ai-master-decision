from __future__ import annotations

from decision_system.ui.blocks import ARCHIVE_KEY
from decision_system.ui.viewmodels import DecisionArchive

from .conftest import all_text, goto


def test_main_navigation_reaches_research_without_sidebar(app_test):
    at = app_test().run()
    at.selectbox(key="nav_top").set_value("⑧ 研究资料库").run()
    assert not at.exception
    assert at.radio(key="nav_page").value == "⑧ 研究资料库"
    assert "207" in all_text(at)
    at.text_input(key="research_query").set_value("具身").run()
    assert not at.exception
    assert "具身" in all_text(at)


def test_research_filter_resets_pagination_and_handles_empty(app_test):
    at = goto(app_test(), "⑧ 研究资料库")
    at.selectbox(key="research_page").set_value(20).run()
    at.text_input(key="research_query").set_value("找不到的关键词xyz").run()
    assert not at.exception
    assert "没有匹配资料" in all_text(at)
    at.text_input(key="research_query").set_value("408").run()
    assert not at.exception
    assert at.selectbox(key="research_page").value == 1


def test_favorite_cockpit_renders_explanation(app_test):
    at = app_test()
    at.session_state[ARCHIVE_KEY] = DecisionArchive(favorite_path_ids=[1])
    at.run()
    assert not at.exception
    assert "四层决策解释" in all_text(at)


def test_comparison_includes_actual_research_and_download(app_test):
    at = goto(app_test(), "③ 多校对比")
    assert not at.exception
    assert "按主题对比研究依据" in all_text(at)
    assert "来源编号" in all_text(at)


def test_comparison_preserves_same_program_in_different_colleges(app_test):
    at = goto(app_test(), "③ 多校对比")
    at.multiselect(key="compare_multiselect").set_value([3, 4]).run()
    assert not at.exception
    frame = at.dataframe[0].value
    assert len(frame.columns) == 3
    assert any("008" in col for col in frame.columns)
    assert any("028" in col for col in frame.columns)


def test_explore_can_add_path_to_comparison(app_test):
    at = goto(app_test(), "② 院校探索")
    button = next(b for b in at.button if b.label == "加入对比")
    button.click().run()
    assert not at.exception
    assert at.radio(key="nav_page").value == "③ 多校对比"
    assert at.multiselect(key="compare_multiselect").value


def test_interactive_table_mode_remains_available(app_test):
    at = app_test().run()
    at.toggle(key="interactive_tables").set_value(True).run()
    assert not at.exception
    assert at.dataframe


def test_mobile_navigation_reaches_all_management_pages(app_test):
    at = app_test().run()
    at.selectbox(key="nav_top").set_value("⚙️ 高级功能").run()
    for sub in ["证据管理", "数据维护 · 招生路径", "模型参数", "决策分析", "系统状态"]:
        at.selectbox(key="adv_top").set_value(sub).run()
        assert not at.exception, sub
        assert at.radio(key="adv_page").value == sub
