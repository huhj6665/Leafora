"""健康检查接口.

返回数据库连通性、环境、短信配置状态。
sms_configured 仅表示凭据已配置，不代表可发送；健康检查绝不主动发送短信。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.utils.response import ok

router = APIRouter(tags=["健康检查"])


@router.get("/health", summary="健康检查")
async def health(db: AsyncSession = Depends(get_db)):
    """检查服务与数据库状态."""
    database = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - 数据库不可用时降级，不抛出
        database = "error"

    return ok(
        {
            "status": "ok" if database == "ok" else "degraded",
            "database": database,
            "environment": settings.APP_ENV,
            "sms_configured": settings.sms_configured,
        }
    )
