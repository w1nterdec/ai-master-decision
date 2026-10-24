"""pytest 公共夹具。"""

from __future__ import annotations

import json
import importlib.util
import shutil
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from decision_system.engine.pipeline import EngineConfig
from decision_system.engine.weights import WeightTree
from decision_system.evidence.gate import (
    ClaimView,
    GateConfig,
    InMemoryEvidenceResolver,
    SourceView,
    StrictEvidenceGate,
)
from decision_system.models.base import Base
from decision_system.models import entities  # noqa: F401
from decision_system.models.enums import ClaimStatus, VerificationStatus
from decision_system.services.db import init_db

from .fixtures import PHASE37C_ROWS, RAW_JSON, RAW_XLSX, code_of, make_tree

VERIFICATION_YEAR = 2028
SOURCE_ID = "SRC-TEST-001"
PATH_KEY = "TEST|001|085410|全日制|方向01|2028|统考|一志愿"


@pytest.fixture(scope="session")
def research_baseline_db(tmp_path_factory):
    """Recreate pre-migration state from tracked Excel; no ignored local backup needed."""
    from decision_system.importers.excel_importer import import_excel

    path = tmp_path_factory.mktemp("research_baseline") / "baseline.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    with sessionmaker(bind=engine)() as session:
        import_excel(session, RAW_XLSX)
        session.commit()
    engine.dispose()
    return path


@pytest.fixture(scope="session")
def research_migrated_db(tmp_path_factory, research_baseline_db):
    """Replay tracked official evidence into an isolated database for all E2E tests."""
    folder = tmp_path_factory.mktemp("research_migrated")
    path = folder / "migrated.db"
    shutil.copy2(research_baseline_db, path)
    script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_bupt_phase5_0.py"
    spec = importlib.util.spec_from_file_location("test_research_migration", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DB_PATH = path
    module.BACKUP_PATH = folder / "before.db"
    result = module.run(apply=True)
    assert not result["warnings"], result["warnings"]
    return path


@pytest.fixture(scope="session")
def tree() -> WeightTree:
    return make_tree()


@pytest.fixture(scope="session")
def codes(tree: WeightTree) -> list[str]:
    return tree.codes(3)


@pytest.fixture
def engine_config() -> EngineConfig:
    return EngineConfig(coverage_threshold=0.8, evaluation_year=VERIFICATION_YEAR)


@pytest.fixture
def good_resolver(tree: WeightTree) -> InMemoryEvidenceResolver:
    """一个"来源已核验、声明已核验、支持全部指标"的解析器。"""
    source = SourceView(
        source_id=SOURCE_ID,
        verification_status=VerificationStatus.VERIFIED,
        applicable_years=(VERIFICATION_YEAR,),
    )
    claims = [
        ClaimView(
            claim_id=i + 1,
            source_id=SOURCE_ID,
            status=ClaimStatus.VERIFIED,
            is_candidate=False,
            supports=True,
            applicable=True,
            path_key=PATH_KEY,
            indicator_code=code,
            applicable_years=(VERIFICATION_YEAR,),
        )
        for i, code in enumerate(tree.codes(3))
    ]
    return InMemoryEvidenceResolver(sources={SOURCE_ID: source}, claims=claims, conflicts=set())


@pytest.fixture
def strict_gate(good_resolver: InMemoryEvidenceResolver) -> StrictEvidenceGate:
    return StrictEvidenceGate(good_resolver, GateConfig())


@pytest.fixture(scope="session")
def golden_baseline() -> dict:
    return json.loads(Path(RAW_JSON).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def raw_xlsx_path() -> Path:
    return RAW_XLSX


# ---------------------------------------------------------------------------
# 数据库夹具
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def imported_db_factory(tmp_path_factory) -> Iterator[sessionmaker[Session]]:
    """导入一次 Excel 的会话工厂（session 级，避免重复导入）。"""
    from decision_system.importers.excel_importer import import_excel

    db_path = tmp_path_factory.mktemp("db") / "test_decision.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        import_excel(session, RAW_XLSX)
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def db(imported_db_factory) -> Iterator[Session]:
    session = imported_db_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def mutating_db(tmp_path) -> Iterator[Session]:
    """独立的、可被测试写入并提交的一次性数据库（避免污染只读夹具）。"""
    from decision_system.importers.excel_importer import import_excel

    engine = create_engine(f"sqlite:///{tmp_path / 'mut.db'}", future=True)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        import_excel(session, RAW_XLSX)
        session.commit()
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def empty_db_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    engine.dispose()


@pytest.fixture
def empty_db(empty_db_factory) -> Iterator[Session]:
    session = empty_db_factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
