"""UI 测试夹具：提供**文件级**临时 SQLite 库路径（供 DECISION_DB_PATH 指向）。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from decision_system.services.db import init_db

from ..fixtures import RAW_XLSX

APP_PATH = Path(__file__).resolve().parents[2] / "app.py"


@pytest.fixture(scope="session")
def ui_db_path(tmp_path_factory) -> Iterator[Path]:
    """导入过 Excel 的临时库（有 5 校 10 路径 33 指标）。"""
    from decision_system.importers.excel_importer import import_excel

    db_path = tmp_path_factory.mktemp("ui_db") / "ui_decision.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        import_excel(session, RAW_XLSX)
        session.commit()
    engine.dispose()
    yield db_path


@pytest.fixture
def empty_db_path(tmp_path) -> Path:
    """空库文件路径（仅建表，无任何数据）。"""
    db_path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    engine.dispose()
    return db_path


@pytest.fixture
def app_test(ui_db_path, monkeypatch):
    """返回已绑定临时库的 AppTest 工厂。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DECISION_DB_PATH", str(ui_db_path))

    def _make():
        return AppTest.from_file(str(APP_PATH), default_timeout=180)

    return _make


@pytest.fixture
def app_test_empty(empty_db_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DECISION_DB_PATH", str(empty_db_path))

    def _make():
        return AppTest.from_file(str(APP_PATH), default_timeout=180)

    return _make


# Phase 6.0 导航重组后，原 5 个页面全部保留在「高级功能」下。
# 既有用例的页面名不变，由本助手负责映射到新导航位置；
# **所有断言保持原样，未做删改**。
LEGACY_PAGE_MAP: dict[str, tuple[str, str]] = {
    "① 项目总览": ("⚙️ 高级功能", "系统状态"),
    "② 招生路径": ("⚙️ 高级功能", "数据维护 · 招生路径"),
    "③ 证据管理": ("⚙️ 高级功能", "证据管理"),
    "④ 决策模型": ("⚙️ 高级功能", "模型参数"),
    "⑤ 决策分析": ("⚙️ 高级功能", "决策分析"),
}


def goto(at, page: str):
    """切换侧边栏导航并重新运行（兼容 Phase 6.0 导航重组前的页面名）。"""
    at.run()
    if page in LEGACY_PAGE_MAP:
        main, sub = LEGACY_PAGE_MAP[page]
        at.radio[0].set_value(main).run()
        at.radio[1].set_value(sub).run()
    else:
        at.radio[0].set_value(page).run()
    return at


def find(el_list, label: str):
    for el in el_list:
        if getattr(el, "label", None) == label:
            return el
    raise AssertionError(f"未找到元素：{label}（现有：{[getattr(e,'label',None) for e in el_list]}）")


def all_text(at) -> str:
    """拼接页面所有可见文本，便于断言。"""
    parts: list[str] = []
    for name in ("title", "header", "subheader", "markdown", "caption", "text", "success", "warning", "error", "info"):
        for el in getattr(at, name, []):
            v = getattr(el, "value", None)
            if v:
                parts.append(str(v))
    for el in getattr(at, "metric", []):
        parts.append(f"{el.label}={el.value}")
    return "\n".join(parts)
