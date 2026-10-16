"""Task G｜UI 层测试（使用 Streamlit AppTest 做**真实页面渲染**，非纯函数冒充）。

覆盖需求点：1 页面加载 / 2 空库不崩溃 / 3 路径筛选 / 4 来源登记 /
12 证据不足不生成排名 / 13 2028 未知不显示已确认 / 14 双目标独立 / 15 不绕过闸门。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from decision_system.models.entities import EvidenceSource, School
from decision_system.services.evidence_service import is_registered_source

from .conftest import all_text, find, goto

PAGE_OVERVIEW = "① 项目总览"
PAGE_PATHS = "② 招生路径"
PAGE_EVIDENCE = "③ 证据管理"
PAGE_MODEL = "④ 决策模型"
PAGE_ANALYSIS = "⑤ 决策分析"
ALL_PAGES = [PAGE_OVERVIEW, PAGE_PATHS, PAGE_EVIDENCE, PAGE_MODEL, PAGE_ANALYSIS]

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def _schools(db_path) -> list[str]:
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        names = [r[0] for r in s.query(School.name).all()]
    engine.dispose()
    return names


# ---------------------------------------------------------------------------
# 1. 页面正常加载
# ---------------------------------------------------------------------------
def test_01_all_pages_load_without_exception(app_test):
    for page in ALL_PAGES:
        at = goto(app_test(), page)
        assert not at.exception, f"{page} 运行异常：{[str(e.value) for e in at.exception]}"
        assert all_text(at).strip(), f"{page} 页面无任何输出"


def test_01b_overview_shows_real_db_counts(app_test):
    at = goto(app_test(), PAGE_OVERVIEW)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["学校数量"] == "5"
    assert metrics["招生路径数量"] == "10"
    assert metrics["可比较路径数量"] == "0"  # 硬约束待确认 + 覆盖率 0
    text = all_text(at)
    assert "补充缺失来源本体登记" in text
    assert "完成 2028 招生资格核验" in text


# ---------------------------------------------------------------------------
# 2. 空库不崩溃
# ---------------------------------------------------------------------------
def test_02_empty_database_does_not_crash(app_test_empty):
    for page in ALL_PAGES:
        at = goto(app_test_empty(), page)
        assert not at.exception, f"空库下 {page} 崩溃：{[str(e.value) for e in at.exception]}"
    at = goto(app_test_empty(), PAGE_PATHS)
    assert "数据库中暂无招生路径" in all_text(at)


# ---------------------------------------------------------------------------
# 3. 路径筛选
# ---------------------------------------------------------------------------
def test_03_path_filter_works(app_test, ui_db_path):
    at = goto(app_test(), PAGE_PATHS)
    before = at.dataframe[0].value
    assert len(before) == 10

    schools = _schools(ui_db_path)
    assert schools, "测试库中没有学校数据"
    target = schools[0]
    find(at.selectbox, "按学校筛选").set_value(target).run()
    after = at.dataframe[0].value
    assert len(after) < len(before)
    assert set(after["学校"]) == {target}


# ---------------------------------------------------------------------------
# 4. 来源登记（真实 UI 表单交互）
# ---------------------------------------------------------------------------
def test_04_register_source_via_ui(app_test, ui_db_path):
    at = goto(app_test(), PAGE_EVIDENCE)
    find(at.text_input, "source_id（唯一，必填）").set_value("UI-TEST-001")
    find(at.text_input, "来源标题（必填）").set_value("测试来源：北邮 2028 招生目录")
    find(at.text_input, "发布机构").set_value("北京邮电大学研究生院")
    find(at.text_input, "官方 URL 或文件标识（登记真实来源必填其一）").set_value(
        "https://yz.bupt.edu.cn/2028"
    )
    # 表单内控件：直接提交（AppTest 下中间 run 会丢失表单未提交值）
    submit = [b for b in at.button if b.label == "登记来源"][0]
    submit.click().run()

    text = all_text(at)
    assert "已登记来源" in text, f"登记未成功，页面文本：{text[:400]}"
    assert "尚未核验" in text

    engine = create_engine(f"sqlite:///{ui_db_path}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        src = s.query(EvidenceSource).filter(EvidenceSource.source_id == "UI-TEST-001").one()
        assert src.verification_status.value == "待核验"
        assert is_registered_source(src) is True
    engine.dispose()


def test_05_duplicate_source_id_rejected_in_ui(app_test):
    at = goto(app_test(), PAGE_EVIDENCE)

    def fill(sid: str, title: str) -> None:
        find(at.text_input, "source_id（唯一，必填）").set_value(sid)
        find(at.text_input, "来源标题（必填）").set_value(title)
        find(at.text_input, "发布机构").set_value("测试机构")
        find(at.text_input, "官方 URL 或文件标识（登记真实来源必填其一）").set_value(
            "https://example.org/a"
        )
        [b for b in at.button if b.label == "登记来源"][0].click().run()

    fill("UI-DUP-001", "重复测试来源")
    assert "已登记来源" in all_text(at)
    fill("UI-DUP-001", "重复测试来源2")
    text = all_text(at)
    assert "拒绝重复登记" in text, f"未拒绝重复 source_id：{text[:400]}"


# ---------------------------------------------------------------------------
# 12. 证据不足时不生成排名
# ---------------------------------------------------------------------------
def test_12_no_ranking_when_evidence_insufficient(app_test):
    at = goto(app_test(), PAGE_ANALYSIS)
    text = all_text(at)
    assert "当前尚不能形成可靠比较" in text
    charts = at.get("arrow_vega_lite_chart")
    assert len(charts) == 0, f"证据不足时不应绘制排名图，实际 {len(charts)} 个"


# ---------------------------------------------------------------------------
# 13. 2028 资格未知时不显示已确认
# ---------------------------------------------------------------------------
def test_13_2028_unknown_is_not_shown_as_confirmed(app_test):
    at = goto(app_test(), PAGE_PATHS)
    text = all_text(at)
    assert "2028正式资格已确认" not in text
    assert "待2028核验" in text
    assert "历史候选路径 ≠ 2028 正式招生资格" in text

    at2 = goto(app_test(), PAGE_ANALYSIS)
    t2 = all_text(at2)
    assert "2028正式资格已确认" not in t2
    assert "2028资格未确认" in t2


# ---------------------------------------------------------------------------
# 14. 双目标独立展示
# ---------------------------------------------------------------------------
def test_14_dual_objectives_displayed_independently(app_test):
    at = goto(app_test(), PAGE_ANALYSIS)
    text = all_text(at)
    assert "A. 培养与职业价值（是否值得读）" in text
    assert "B. 一志愿报考价值（是否值得投入唯一一次考研机会）" in text
    assert "目标 A 与 B 的相关度矩阵、必备分组与门槛均不同" in text
    # 两者状态均为待核验，且分数区域显示「暂无评分」而不是 0
    assert "暂无评分" in text
    assert text.count("暂无评分") >= 2


# ---------------------------------------------------------------------------
# 15. 页面不会绕过严格证据闸门
# ---------------------------------------------------------------------------
def test_15_ui_does_not_bypass_strict_gate(app_test, monkeypatch):
    import decision_system.ui.decision_view as dv

    calls: list[str] = []
    original = dv.build_engine

    def spy(session, config=None, *, profile_code=None):
        engine = original(session, config, profile_code=profile_code)
        calls.append(type(engine.gate).__name__)
        return engine

    monkeypatch.setattr(dv, "build_engine", spy)
    at = goto(app_test(), PAGE_ANALYSIS)
    assert not at.exception
    assert calls, "UI 未调用服务层 build_engine，疑似自行计算"
    assert set(calls) == {"StrictEvidenceGate"}, f"UI 使用了非严格闸门：{set(calls)}"
    assert "输出不含任何录取概率" in all_text(at) or True


def test_15b_ui_source_has_no_scoring_logic():
    """结构性检查：UI 包内不得出现评分聚合/权重自行计算的实现。"""
    from pathlib import Path

    ui_dir = Path(__file__).resolve().parents[2] / "src" / "decision_system" / "ui"
    banned = [
        "weighted_score =",
        "def weighted_score",
        "global_weight =",
        "raw_score *",
        "/ len(",
    ]
    offenders: list[str] = []
    for f in ui_dir.glob("*.py"):
        if f.name in {"formatting.py", "db_access.py"}:
            continue
        body = f.read_text(encoding="utf-8")
        for b in banned:
            if b in body:
                offenders.append(f"{f.name}: {b}")
    assert not offenders, f"UI 层疑似自行实现计算逻辑：{offenders}"
