"""SQLAlchemy 声明式基类与通用时间戳 Mixin."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 主键/外键类型。
# PostgreSQL 使用 BIGINT；SQLite 使用 INTEGER。
# 原因：SQLite 仅对声明为 "INTEGER PRIMARY KEY" 的列自动分配 rowid 自增，
# 若使用 BIGINT PRIMARY KEY 不会自增（导致 NOT NULL 约束失败）。
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类.

    所有模型共享该基类，以便 Alembic 通过 Base.metadata 收集全部表结构。
    """


class TimestampMixin:
    """为模型提供 created_at / updated_at 时间戳字段."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )
