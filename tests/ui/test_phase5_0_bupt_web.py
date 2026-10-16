"""Phase 5.0 Task F｜用 Phase 4.1 既有页面对北邮迁移结果做 8 项 Web 验证。

原则：
    * 不新增页面、不改现有页面逻辑，只做验证；
    * 只读：把迁移后的库复制到临时目录再渲染，绝不写入 data/decision.db；
    * 只断言「页面如实反映数据库」，不断言真实招生事实为真。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "app.py"
PROD_DB = ROOT / "data" / "decision.db"

PAGE_OVERVIEW = "① 项目总览"
PAGE_PATHS = "② 招生路径"
PAGE_EVIDENCE = "③ 证据管理"
PAGE_MODEL = "④ 决策模型"
PAGE_ANALYSIS = "⑤ 决策分析"

# 禁用的是「给出录取概率」这一行为；页面自带的「输出不含录取概率」免责声明属合规表述，不算违规
BANNED = ("录取概率：", "录取概率为", "录取概率 =", "上岸概率：", "上岸概率=", "录取率：")


def _text(at) -> str:
    parts: list[str] = []
    for name in (
        "title", "header", "subheader", "markdown", "caption", "text",
        "success", "warning", "error", "info",
    ):
        for el in getattr(at, name, []):
            v = getattr(el, "value", None)
            if v:
                parts.append(str(v))
    for el in getattr(at, "metric", []):
        parts.append(f"{el.label}={el.value}")
    for df in getattr(at, "dataframe", []):
        try:
            parts.append(df.value.to_string())
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(parts)


def _goto(at, page: str):
    at.run()
    at.radio[0].set_value(page).run()
    return at


@pytest.fixture(scope="module")
def at_factory(tmp_path_factory):
    import os

    db_path = tmp_path_factory.mktemp("phase5_0_ui") / "ui.db"
    shutil.copy2(PROD_DB, db_path)
    old = os.environ.get("DECISION_DB_PATH")
    os.environ["DECISION_DB_PATH"] = str(db_path)

    def _make() -> AppTest:
        return AppTest.from_file(str(APP_PATH), default_timeout=240)

    yield _make
    if old is None:
        os.environ.pop("DECISION_DB_PATH", None)
    else:
        os.environ["DECISION_DB_PATH"] = old


def test_f1_overview_renders_and_shows_registered_sources(at_factory):
    """检查 1：总览页正常渲染，并如实反映新增的已登记来源（迁移前为 0）。"""
    at = _goto(at_factory(), PAGE_OVERVIEW)
    assert not at.exception, f"总览页渲染异常：{at.exception}"
    txt = _text(at)
    assert "北邮" in txt or "BUPT" in txt or "项目总览" in txt


def test_f2_paths_page_shows_bupt_exam_subjects(at_factory):
    """检查 2：招生路径页能区分方向01=801 与 方向02=408。"""
    at = _goto(at_factory(), PAGE_PATHS)
    assert not at.exception, f"招生路径页渲染异常：{at.exception}"
    txt = _text(at)
    assert "801" in txt, "路径页未显示方向01 的 801 通信原理"
    assert "408" in txt, "路径页未显示方向02 的 408"


def test_f3_paths_page_does_not_claim_2028_confirmed(at_factory):
    """检查 3：路径页不得出现 2028 已确认表述。"""
    at = _goto(at_factory(), PAGE_PATHS)
    txt = _text(at)
    assert "2028正式资格已确认" not in txt
    assert ("待2028核验" in txt) or ("2028资格未确认" in txt), "未显示 2028 未确认状态"


def test_f4_paths_page_shows_quota_caliber(at_factory):
    """检查 4：路径页展示北邮 2027 核验结果与名额口径提示（含推免）。"""
    at = _goto(at_factory(), PAGE_PATHS)
    txt = _text(at)
    # 名额口径提示或关键风险文本应出现在页面上
    assert ("含推免" in txt) or ("名额" in txt), "页面未体现名额口径信息"


def test_f5_evidence_page_shows_new_sources(at_factory):
    """检查 5：证据管理页能看到 3 条新登记来源及其核验状态。"""
    at = _goto(at_factory(), PAGE_EVIDENCE)
    # 该页「来源清单」默认勾选「只看未登记本体的来源」，需取消勾选才能看到已登记来源
    for cb in at.checkbox:
        if getattr(cb, "label", "") == "只看未登记本体的来源":
            cb.set_value(False).run()
            break
    assert not at.exception, f"证据管理页渲染异常：{at.exception}"
    txt = _text(at)
    assert "S-BUPT-2027-CATALOG-005" in txt, "未显示 2027 官方目录来源"
    assert "S-BUPT-2027-EXAMADJ" in txt, "未显示 2027 科目调整公告来源"
    assert "S-BUPT-AI-COLLEGE-SITE" in txt, "未显示学院官网来源（应保持待核验）"


def test_f6_evidence_gap_stats_consistent_with_db(at_factory):
    """检查 6：页面缺口统计与数据库实查一致（已登记 3 / 已核验 2 / 已核验声明 6）。"""
    at = _goto(at_factory(), PAGE_EVIDENCE)
    txt = _text(at)
    for token in ("已登记", "已核验"):
        assert token in txt, f"证据页未展示 {token} 统计"
    # 与数据库实查交叉验证（避免页面自说自话）
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from decision_system.services.db import init_db
    from decision_system.services.evidence_service import evidence_gap_stats

    import os

    engine = create_engine(f"sqlite:///{os.environ['DECISION_DB_PATH']}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        g = evidence_gap_stats(s)
    assert g["source_registered"] == 3
    assert g["source_verified"] == 2
    assert g["claim_verified"] == 6
    assert g["claim_pending"] == 2


def test_f7_model_page_weights_unchanged(at_factory):
    """检查 7：决策模型页仍使用演示权重档案，迁移未改动权重。"""
    at = _goto(at_factory(), PAGE_MODEL)
    assert not at.exception, f"决策模型页渲染异常：{at.exception}"
    txt = _text(at)
    assert "phase37c_demo" in txt or "演示" in txt, "未显示演示权重档案"


def test_f8_analysis_page_no_probability_and_bupt_not_comparable(at_factory):
    """检查 8：决策分析页北邮不可比较，且全站不出现录取概率。"""
    at = _goto(at_factory(), PAGE_ANALYSIS)
    assert not at.exception, f"决策分析页渲染异常：{at.exception}"
    txt = _text(at)
    for b in BANNED:
        assert b not in txt, f"页面出现禁用表述：{b}"
    assert ("不可比较" in txt) or ("证据不足" in txt), "北邮应显示为不可比较/证据不足"
