"""应用入口.

创建 FastAPI 实例，注册路由、CORS 与全局异常处理器，
统一所有接口返回格式 {code, message, data}。
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import account_security, assistant, auth, device, field, health, image, inspection, platform, task, user
from app.core.config import settings
from app.core.exceptions import BusinessError
from app.utils.response import fail, ok

# 开发环境提升业务日志级别，确保短信分类日志（LOCAL_RATE_LIMIT / SMS_SENT 等）可见
logging.getLogger("app").setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理.

    启动时：可在此初始化连接池、MQTT 客户端、设备注册中心等。
    关闭时：释放相应资源。
    """
    # 启动逻辑
    yield
    # 关闭逻辑
    await assistant.shutdown()


# 开发/生产环境开关：生产环境可关闭 /docs /redoc /openapi.json
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

# CORS：仅允许明确配置的来源，禁止 allow_origins=["*"] 与 allow_credentials=True 同用
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """通用浏览器安全头；生产 HTTPS 额外启用 HSTS。"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(settings.API_PREFIX) else "no-cache"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError) -> JSONResponse:
    """统一处理业务异常，返回 {code, message, data}."""
    return JSONResponse(
        status_code=exc.status_code,
        content=fail(exc.code, exc.message, exc.data),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """统一处理请求参数校验异常."""
    return JSONResponse(
        status_code=422,
        content=fail(422, "参数校验失败", jsonable_encoder(exc.errors())),
    )


# 注册业务路由（统一挂载 /api 前缀）
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(user.router, prefix=settings.API_PREFIX)
app.include_router(account_security.router, prefix=settings.API_PREFIX)
app.include_router(device.router, prefix=settings.API_PREFIX)
app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(inspection.router, prefix=settings.API_PREFIX)
app.include_router(image.router, prefix=settings.API_PREFIX)
app.include_router(platform.router, prefix=settings.API_PREFIX)
app.include_router(assistant.router, prefix=settings.API_PREFIX)
app.include_router(field.router, prefix=settings.API_PREFIX)
app.include_router(task.router, prefix=settings.API_PREFIX)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    """服务信息."""
    return ok(
        {
            "service": settings.APP_NAME,
            "version": settings.VERSION,
            "env": settings.APP_ENV,
        }
    )
