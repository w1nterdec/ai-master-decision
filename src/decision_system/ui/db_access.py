"""UI 数据库访问：支持通过环境变量 DECISION_DB_PATH 指向临时库（测试用）。"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from decision_system.services.db import (
    DEFAULT_DB_PATH,
    create_sqlite_engine,
    init_db,
    make_session_factory,
)

ENV_DB_PATH = "DECISION_DB_PATH"
_DB_PATH_KEY = "_db_path"


def resolve_db_path() -> Path:
    raw = os.environ.get(ENV_DB_PATH)
    return Path(raw) if raw else DEFAULT_DB_PATH


def get_session_factory() -> sessionmaker[Session]:
    """按会话缓存；不使用 st.cache_resource，避免测试中跨库串扰。"""
    path = str(resolve_db_path())
    cached = st.session_state.get(_DB_PATH_KEY)
    factory = st.session_state.get("_session_factory")
    if factory is None or cached != path:
        engine = create_sqlite_engine(path)
        init_db(engine)  # 空库也建表，保证页面不崩溃
        factory = make_session_factory(engine)
        st.session_state[_DB_PATH_KEY] = path
        st.session_state["_session_factory"] = factory
    return factory


@contextmanager
def db_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
