"""数据库会话与初始化。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from decision_system.models.base import Base
from decision_system.models import entities  # noqa: F401  (确保全部实体注册到 metadata)

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "decision.db"


def create_sqlite_engine(db_path: str | Path | None = None, *, echo: bool = False) -> Engine:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _):  # pragma: no cover - SQLite 特定
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
