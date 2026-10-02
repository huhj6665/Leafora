"""应用配置模块.

通过 pydantic-settings 从环境变量与 .env 文件加载配置，
支持 development / production / test 等多环境区分。

安全要求：
    - 所有敏感信息（数据库密码、JWT 密钥、阿里云 AccessKey）通过环境变量注入，禁止硬编码。
    - 生产环境强制要求替换默认 JWT 密钥，否则启动失败。
    - 数据库连接串通过 SQLAlchemy URL.create() 从拆分字段构造，
      避免密码中的特殊字符产生 URL 编码问题。
"""
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# 开发环境默认密钥，仅用于本地开发；生产环境禁止使用。
_INSECURE_DEV_SECRET = "dev_insecure_secret_change_me"


class Settings(BaseSettings):
    """全局应用配置单例.

    配置读取优先级：环境变量 > .env 文件 > 默认值。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用基础配置 ----
    APP_NAME: str = "TLD Intelligent Inspection Platform"
    APP_ENV: Literal["development", "production", "test"] = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api"
    VERSION: str = "1.0.0"

    # ---- 数据库配置 ----
    # DATABASE_URL 为可选覆盖项；为空时由下方 DB_* 字段构造。
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "tld_db"
    DB_USER: str = "tld_backend"
    DB_PASSWORD: str = ""

    # ---- JWT 配置 ----
    JWT_SECRET_KEY: str = Field(
        default=_INSECURE_DEV_SECRET,
        description="JWT 签名密钥，生产环境必须通过环境变量注入",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # ---- 密码加密配置 ----
    BCRYPT_ROUNDS: int = 12

    # ---- CORS 配置（逗号分隔的允许来源） ----
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- 阿里云号码认证服务（短信认证） ----
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_SMS_SIGN_NAME: str = ""
    ALIYUN_SMS_TEMPLATE_CODE: str = ""
    ALIYUN_SMS_ENDPOINT: str = "dypnsapi.aliyuncs.com"
    # 模板参数（JSON 字符串）。使用 "##code##" 占位符让阿里云动态生成并核验验证码。
    ALIYUN_SMS_TEMPLATE_PARAM: str = '{"code":"##code##"}'
    # 验证码：6 位纯数字；有效时长单位秒（5 分钟 = 300）
    ALIYUN_SMS_CODE_LENGTH: int = 6
    ALIYUN_SMS_VALID_TIME: int = 300
    # 短信供应商：mock / aliyun；空字符串时按凭据是否配置自动选择
    SMS_PROVIDER: str = ""

    # ---- 短信发送限流 ----
    RATE_LIMIT_ENABLED: bool = True

    # ---- 163 SMTP 邮件发送（邮箱绑定 / 密码找回） ----
    # SMTP_PASSWORD 为 163 客户端授权码，非网页登录密码。
    SMTP_HOST: str = "smtp.163.com"
    SMTP_PORT: int = 465
    SMTP_USE_SSL: bool = True
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "TLD智能巡检平台"
    # 连接 / 认证 / 发送超时（秒）
    SMTP_TIMEOUT: float = 15.0

    # ---- 邮箱验证码 ----
    # 短数字验证码以 HMAC(服务端密钥) 摘要落库，不存明文。
    EMAIL_CODE_LENGTH: int = 6
    # 验证码有效期（秒），默认 5 分钟
    EMAIL_CODE_TTL_SECONDS: int = 300
    # 单个凭据允许的最大失败尝试次数（超过即作废）
    EMAIL_CODE_MAX_ATTEMPTS: int = 5

    # ---- 开发文档开关（生产环境可关闭 /docs /redoc /openapi.json） ----
    ENABLE_DOCS: bool = True

    # ---- MQTT Broker ----
    MQTT_HOST: str = "127.0.0.1"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    # 统一 Topic 前缀，最终订阅/发布：{prefix}/device/{device_id}/data
    MQTT_TOPIC_PREFIX: str = "tld"
    MQTT_CONSUMER_CLIENT_ID: str = Field(default="tld-cloud-consumer", min_length=1, max_length=64)
    MQTT_COMMAND_TTL_SECONDS: int = Field(default=60, ge=15, le=3600)
    MQTT_COMMAND_RETRY_BASE_SECONDS: int = Field(default=10, ge=10, le=300)
    MQTT_COMMAND_RETRY_MAX_SECONDS: int = Field(default=30, ge=10, le=600)
    MQTT_COMMAND_MAX_ATTEMPTS: int = Field(default=6, ge=1, le=100)

    # ---- 图片存储（本地文件系统根目录，正式部署可迁移对象存储） ----
    IMAGE_STORAGE_ROOT: str = "storage"
    IMAGE_MAX_SIZE_MB: int = 10

    # ---- 设备 HTTP 图片上传：MQTT 记录尚未入库时的有界等待 ----
    # 设备上传图片时，若 (device_id, data_id) 巡检记录尚未入库（图片先到），
    # 轮询等待该记录出现，最长等待秒数与轮询间隔。超过仍未出现则返回可重试错误。
    IMAGE_PENDING_WAIT_SECONDS: float = 5.0
    IMAGE_PENDING_POLL_INTERVAL: float = 0.5

    # ---- 云端模型服务（RT-DETR-L）----
    MODEL_SERVICE_URL: str = ""
    MODEL_WEIGHT_PATH: str = ""
    MODEL_DEVICE: str = "cpu"
    MODEL_CONFIDENCE: float = 0.5
    MODEL_IMAGE_SIZE: int = 800
    MODEL_NAME: str = "RT-DETR-L"
    MODEL_VERSION: str = "v1.0"

    # ---- DeepSeek 辅助分析（仅接收分析服务产出的结构化摘要）----
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/chat/completions"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DEEPSEEK_TIMEOUT_SECONDS: float = 20.0
    ASSISTANT_RUN_TIMEOUT_SECONDS: int = 180
    ASSISTANT_MODEL_TIMEOUT_SECONDS: int = 60
    ASSISTANT_MAX_ROUNDS: int = 6
    ASSISTANT_MAX_TOOL_CALLS: int = 12
    ASSISTANT_MAX_DAILY_RUNS: int = 100
    ASSISTANT_MAX_DAILY_TOKENS: int = 500000
    ASSISTANT_STORAGE_ROOT: str = "storage/assistant"
    QWEATHER_API_HOST: str = ""
    QWEATHER_API_KEY: str = ""
    QWEATHER_KEY_ID: str = ""
    QWEATHER_PROJECT_ID: str = ""
    QWEATHER_PRIVATE_KEY_PATH: str = ""
    TAVILY_API_KEY: str = ""

    # ---- 开发工具开关（模拟设备 / 测试页面 / seed 脚本）----
    ENABLE_DEV_TOOLS: bool = True
    # 固定模拟设备编号（开发与压力测试专用）
    DEV_SIM_DEVICE_ID: str = "TLD_JETSON_001"
    DEV_SIM_DEVICE_NAME: str = "TLD Simulator"

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        """未显式提供 DATABASE_URL 时，从 DB_* 字段安全构造连接串."""
        if not self.DATABASE_URL:
            self.DATABASE_URL = URL.create(
                drivername="postgresql+asyncpg",
                username=self.DB_USER,
                password=self.DB_PASSWORD,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            ).render_as_string(hide_password=False)
        return self

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """生产环境安全检查：禁止使用默认 JWT 密钥."""
        if self.APP_ENV == "production" and (
            not self.JWT_SECRET_KEY.strip() or self.JWT_SECRET_KEY == _INSECURE_DEV_SECRET
        ):
            raise ValueError(
                "生产环境必须通过环境变量 JWT_SECRET_KEY 配置安全的签名密钥"
            )
        return self

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        """解析逗号分隔的 CORS 来源列表."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sms_configured(self) -> bool:
        """阿里云短信凭据是否已配置（仅表示配置存在，不代表可发送）."""
        return bool(self.ALIYUN_ACCESS_KEY_ID and self.ALIYUN_ACCESS_KEY_SECRET)

    @property
    def smtp_configured(self) -> bool:
        """SMTP 凭据是否已配置（仅表示配置存在，不代表可发送）."""
        return bool(self.SMTP_USERNAME and self.SMTP_PASSWORD and self.SMTP_FROM_EMAIL)

    def mqtt_topic(self, device_id: str) -> str:
        """构造统一数据 Topic：{prefix}/device/{device_id}/data."""
        return f"{self.MQTT_TOPIC_PREFIX}/device/{device_id}/data"


@lru_cache
def get_settings() -> Settings:
    """返回缓存后的全局配置实例（进程内单例）."""
    return Settings()


settings = get_settings()
