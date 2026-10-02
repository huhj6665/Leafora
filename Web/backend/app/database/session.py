"""数据库引擎与会话管理.

提供全局异步引擎、会话工厂，以及供 FastAPI 依赖注入使用的 get_db。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# 全局异步引擎。
# pool_pre_ping：每次从连接池取出连接前先探测有效性，避免使用已断开的连接。
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    future=True,
)

# 异步会话工厂。
# expire_on_commit=False：提交后不使对象过期，便于在请求内继续使用已加载的属性。
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：为每个请求提供一个数据库会话，请求结束后自动关闭."""
    async with AsyncSessionLocal() as session:
        yield session
