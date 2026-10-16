"""SQLAlchemy 声明式基类与公共混入。"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import DateTime, String, TypeDecorator, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """声明式基类。命名约定显式化，便于后续 Alembic 迁移。"""


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )


class StrEnumType(TypeDecorator):
    """把 Python str-Enum 以其中文 value 落库的通用类型。

    SQLite 下即为 TEXT；同时保证从库里读回时还原为枚举成员。
    """

    impl = String(64)
    cache_ok = True

    def __init__(self, enum_cls: Any, *args: Any, **kwargs: Any) -> None:
        self.enum_cls = enum_cls
        kwargs.setdefault("length", 64)
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return getattr(value, "value", value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        try:
            return self.enum_cls(value)
        except ValueError:
            return value
