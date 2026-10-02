"""pytest 测试配置与共享 fixture.

测试使用独立的 SQLite 数据库（每个测试一个临时库），
并通过 FastAPI 依赖覆盖将 get_db 指向测试会话，从而不依赖真实 PostgreSQL。

短信统一使用 MockSMSProvider，绝不发送真实收费短信。
"""
import os

# 必须在导入 app 之前设置环境变量（settings 为进程内单例）
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_unit_tests")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # 降低哈希成本，加速测试
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_default.db")
# 关闭短信发送限流，避免测试间相互干扰（限流逻辑单独单测）
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# 确保使用 Mock 短信供应商
os.environ.setdefault("SMS_PROVIDER", "mock")
# 强制清空阿里云凭据，避免误读本地 .env 中的真实 AccessKey（测试须隔离真实配置）
os.environ["ALIYUN_ACCESS_KEY_ID"] = ""
os.environ["ALIYUN_ACCESS_KEY_SECRET"] = ""
# 测试绝不调用外部大模型，也不读取开发机 .env 中的真实密钥。
os.environ["DEEPSEEK_API_KEY"] = ""

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.models  # noqa: F401,E402  导入以注册全部模型
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.rate_limit import rate_limiter  # noqa: E402
from app.services.email import reset_email_sender  # noqa: E402
from app.services.sms import reset_sms_provider  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_services():
    """每个测试前后重置短信/邮件提供者与限流器，保证隔离."""
    reset_sms_provider()
    reset_email_sender()
    rate_limiter.reset()
    yield
    reset_sms_provider()
    reset_email_sender()


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    """创建独立测试数据库并覆盖 get_db 依赖.

    返回会话工厂，供直接进行数据库 CRUD 的测试使用。
    """
    db_file = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    # 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield factory

    # 清理
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    """提供 httpx 异步客户端，用于端到端接口测试."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
