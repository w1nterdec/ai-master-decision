"""Phase 6.0｜决策产品化 UI 测试（真实页面渲染，非纯函数冒充）。

覆盖：六页面渲染 / 空库不崩溃 / 路径身份不混淆 / 历史不冒充 2028 /
未知不补零 / 权重持久化 / 演示权重不被当用户偏好 / 无虚假排名 / 档案导出。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from streamlit.testing.v1 import AppTest

from decision_system.models.entities import AdmissionPath, Indicator, WeightNode, WeightProfile
from decision_system.services.db import init_db
from decision_system.ui.pages_profile import _build_markdown
from decision_system.ui.viewmodels import DecisionArchive

from ..fixtures import RAW_XLSX
from .conftest import all_text, find, goto

PAGE_COCKPIT = "① 决策驾驶舱"
PAGE_EXPLORE = "② 院校探索"
PAGE_COMPARE = "③ 多校对比"
PAGE_TREE = "④ 动态决策树"
PAGE_RISK = "⑤ 风险与路径规划"
PAGE_PROFILE = "⑥ 我的决策档案"
MAIN_PAGES = [
    PAGE_COCKPIT,
    PAGE_EXPLORE,
    PAGE_COMPARE,
    PAGE_TREE,
    PAGE_RISK,
    PAGE_PROFILE,
]

# 出现即视为「伪造排名 / 伪造概率」的违规表述
BANNED_CLAIMS = ("最优目标", "推荐报考", "首选院校", "录取概率：", "上岸概率", "录取率：", "排名第一")
# 学校名：用于验证「禁止预设最优目标」
SCHOOL_NAMES = ("北京邮电大学", "电子科技大学", "东南大学", "合肥工业大学", "西南交通大学")

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

_APP_PATH = Path(__file__).resolve().parents[2] / "app.py"


@pytest.fixture(autouse=True)
def _archive_to_tmp(monkeypatch, tmp_path):
    """把决策档案落到临时目录，避免测试写入项目内 data/decision_profile.json。"""
    from decision_system.services import view_service

    monkeypatch.setattr(view_service, "ARCHIVE_PATH", tmp_path / "decision_profile.json")


@pytest.fixture
def p6_db_path(tmp_path):
    from decision_system.importers.excel_importer import import_excel

    db_path = tmp_path / "p6.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        import_excel(s, RAW_XLSX)
        s.commit()
    engine.dispose()
    return db_path


@pytest.fixture
def at_factory(p6_db_path, monkeypatch):
    monkeypatch.setenv("DECISION_DB_PATH", str(p6_db_path))

    def _make():
        return AppTest.from_file(str(_APP_PATH), default_timeout=240)

    return _make


@pytest.fixture
def empty_at_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    engine.dispose()
    monkeypatch.setenv("DECISION_DB_PATH", str(db_path))

    def _make():
        return AppTest.from_file(str(_APP_PATH), default_timeout=240)

    return _make




# ---------------------------------------------------------------------------
# 1. 六个主页面渲染
# ---------------------------------------------------------------------------
def test_01_six_main_pages_render(at_factory):
    for page in MAIN_PAGES:
        at = goto(at_factory(), page)
        assert not at.exception, f"{page} 异常：{[str(e.value) for e in at.exception]}"
        assert all_text(at).strip(), f"{page} 无任何输出"


def test_02_empty_db_does_not_crash(empty_at_factory):
    for page in MAIN_PAGES:
        at = goto(empty_at_factory(), page)
        assert not at.exception, f"空库下 {page} 崩溃：{[str(e.value) for e in at.exception]}"


def test_03_default_home_is_cockpit(at_factory):
    at = at_factory()
    at.run()
    assert not at.exception
    text = all_text(at)
    assert "决策驾驶舱" in text


# ---------------------------------------------------------------------------
# 2. 不预设最优目标 / 无虚假排名 / 无录取概率
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page", MAIN_PAGES)
def test_04_no_fake_ranking_or_probability(at_factory, page):
    at = goto(at_factory(), page)
    text = all_text(at)
    for banned in BANNED_CLAIMS:
        assert banned not in text, f"{page} 出现违规表述：{banned}"


def test_05_no_school_presupposed_as_best(at_factory):
    """任何主页面都不得把某所学校写成「最优/首选/建议报考」。"""
    for page in MAIN_PAGES:
        at = goto(at_factory(), page)
        text = all_text(at)
        for name in SCHOOL_NAMES:
            for banned in ("最优", "首选", "建议报考", "推荐院校"):
                assert f"{name}{banned}" not in text, f"{page}：{name}{banned}"


def test_06_compare_page_has_no_winner(at_factory):
    at = goto(at_factory(), PAGE_COMPARE)
    text = all_text(at)
    assert "不产生排名" in text
    assert "无法判断" in text or "暂无数据" in text


# ---------------------------------------------------------------------------
# 3. 历史不冒充 2028
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page", [PAGE_COCKPIT, PAGE_EXPLORE, PAGE_RISK])
def test_07_history_not_impersonating_2028(at_factory, page):
    at = goto(at_factory(), page)
    text = all_text(at)
    assert "已确认 2028 资格" in text or "2028 正式资格" in text
    assert "未确认即按" in text or "尚未发布" in text or "不得冒充" in text


def test_08_no_path_marked_confirmed(at_factory):
    """当前数据状态下，驾驶舱不得声称任何路径已确认 2028 资格。"""
    at = goto(at_factory(), PAGE_COCKPIT)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["已确认 2028 资格"].startswith("0")


# ---------------------------------------------------------------------------
# 4. 未知不补零
# ---------------------------------------------------------------------------
def test_09_unknown_not_rendered_as_zero(at_factory):
    at = goto(at_factory(), PAGE_COCKPIT)
    text = all_text(at)
    assert "暂无数据" in text
    # 名额/评分缺失时不得出现「0 人 / 0 分」这类冒充
    assert "计划 0 人" not in text
    assert "实际录取 0 人" not in text


def test_10_compare_unknown_cells_are_not_zero(at_factory):
    at = goto(at_factory(), PAGE_COMPARE)
    text = all_text(at)
    assert "无法判断" in text
    assert "图例" in text


# ---------------------------------------------------------------------------
# 5. 路径身份不混淆（比较单位是路径，不是学校）
# ---------------------------------------------------------------------------
def test_11_path_identity_not_confused(p6_db_path):
    """同一学校不同方向的两条路径，必须可区分且 path_key 唯一。"""
    from decision_system.services import view_service
    from decision_system.ui.db_access import resolve_db_path  # noqa: F401
    from decision_system.services.db import create_sqlite_engine, make_session_factory
    from decision_system.engine.pipeline import EngineConfig
    from decision_system.ui.decision_view import load_path_rows

    engine = create_sqlite_engine(str(p6_db_path))
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        rows = load_path_rows(session, EngineConfig(profile_code="phase37c_demo"))
        summaries = view_service.load_path_summaries(session, rows)
        keys = [s.path_key for s in summaries]
        assert len(keys) == len(set(keys)), "path_key 必须唯一"
        bupt = [s for s in summaries if s.school_code == "BUPT"]
        assert len(bupt) == 2
        exams = {s.exam_unit4 for s in bupt}
        assert exams == {"801 通信原理", "408"}, exams
        directions = {s.direction for s in bupt}
        assert directions == {"方向01", "方向02"}
    engine.dispose()


# ---------------------------------------------------------------------------
# 6. 权重持久化与演示配置纪律
# ---------------------------------------------------------------------------
def test_12_weight_change_persisted_and_audited(at_factory, p6_db_path):
    at = goto(at_factory(), PAGE_TREE)
    assert not at.exception
    text = all_text(at)
    assert "演示配置" in text, "必须显式标注当前为演示配置"

    # 调整第一个三级指标的组内权重
    slider = at.slider[0]
    old = float(slider.value)
    new = old + 10.0 if old < 90 else old - 10.0
    slider.set_value(new).run()
    btn = find(at.button, "应用修改（写入数据库并记录审计）")
    btn.click().run()
    assert not at.exception, f"应用权重异常：{[str(e.value) for e in at.exception]}"

    engine = create_engine(f"sqlite:///{p6_db_path}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        profile = s.execute(
            select(WeightProfile).where(WeightProfile.code == "phase37c_demo")
        ).scalar_one()
        # 演示配置被修改后**仍**是演示配置，不得自动升级为用户偏好
        assert profile.is_demo is True
        nodes = s.execute(
            select(WeightNode).where(WeightNode.profile_id == profile.id)
        ).scalars().all()
        raws = sorted(float(n.raw_weight) for n in nodes)
        assert any(abs(r - new) < 1e-6 for r in raws), "权重未落库"
    engine.dispose()


def test_13_demo_weight_not_mistaken_as_user_preference(at_factory):
    at = goto(at_factory(), PAGE_TREE)
    text = all_text(at)
    assert "不是" in text and "演示配置" in text


# ---------------------------------------------------------------------------
# 7. 决策档案
# ---------------------------------------------------------------------------
def test_14_archive_add_and_export(at_factory):
    at = goto(at_factory(), PAGE_EXPLORE)
    assert not at.exception
    btn = find(at.button, "☆ 加入候选")
    btn.click().run()
    assert not at.exception

    at2 = goto(at_factory(), PAGE_PROFILE)
    text = all_text(at2)
    assert "候选路径" in text
    frames = "\n".join(df.value.to_string() for df in at2.dataframe)
    assert "演示配置（待确认）" in frames, "必须区分演示配置与用户偏好"
    assert "已加入的路径" in text or "·" in text, "候选路径应显示在档案页"


def test_15_markdown_export_has_no_probability(p6_db_path):
    from decision_system.services import view_service
    from decision_system.services.db import create_sqlite_engine, make_session_factory
    from decision_system.engine.pipeline import EngineConfig
    from decision_system.ui.decision_view import load_path_rows
    from decision_system.ui.blocks import get_archive  # noqa: F401

    engine = create_sqlite_engine(str(p6_db_path))
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        rows = load_path_rows(session, EngineConfig(profile_code="phase37c_demo"))
        summaries = view_service.load_path_summaries(session, rows)
    engine.dispose()

    archive = DecisionArchive(candidate_path_ids=[summaries[0].path_id], notes=["测试备注"])
    md = _build_markdown(
        summaries, archive, [{"配置代码": "phase37c_demo", "名称": "演示", "性质": "演示配置（待确认）"}],
        profile_code="phase37c_demo",
    )
    for banned in BANNED_CLAIMS:
        assert banned not in md
    assert "决策前提" in md
    assert "测试备注" in md
    assert "演示配置仅代表示例权重结构" in md


# ---------------------------------------------------------------------------
# 8. 数据库初始化 / 重建后页面可用
# ---------------------------------------------------------------------------
def test_16_fresh_db_init_then_pages_work(empty_at_factory, tmp_path):
    """空库初始化后，六个页面均可渲染（不依赖任何既有数据）。"""
    at = goto(empty_at_factory(), PAGE_COCKPIT)
    assert not at.exception
    assert "暂无招生路径" in all_text(at)

    at2 = goto(empty_at_factory(), PAGE_TREE)
    assert not at2.exception


def test_17_indicator_tree_unchanged(p6_db_path):
    """Phase 6.0 不得改动指标树结构：仍为 5 / 10 / 18。"""
    engine = create_engine(f"sqlite:///{p6_db_path}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        counts = {}
        for lv in (1, 2, 3):
            counts[lv] = len(
                s.execute(select(Indicator).where(Indicator.level == lv)).scalars().all()
            )
        paths = len(s.execute(select(AdmissionPath)).scalars().all())
    engine.dispose()
    assert counts == {1: 5, 2: 10, 3: 18}, counts
    assert paths == 10
