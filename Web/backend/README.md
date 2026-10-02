# Leafora Backend

FastAPI / SQLAlchemy 异步后端，正式数据库使用 PostgreSQL，结构由 Alembic 迁移管理。MQTT Consumer 独立运行，消费设备心跳、采样和回执。

## 主要职责

- 手机号主身份、验证码 / 密码登录、Web 小程序扫码登录。
- 一次性设备配对、设备归属和任务权限校验。
- 烟田版本快照、START / END 幂等命令、两阶段完成核验。
- 结构化采样、图片上传、可选云端推理、环境和空间风险展示。
- 农业助手、资料检索与可选模型、天气和联网检索。
- 统一响应 `{ code, message, data }`。

历史用户名身份数据保留兼容，但不提供正式用户名注册或登录。

## 安装

Python 3.10+。从本目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

首次部署创建自己的 PostgreSQL 数据库和账号，填写 `DB_*`、随机 `JWT_SECRET_KEY` 与 MQTT 凭据。`SMS_PROVIDER=mock` 仅用于本地开发；真实短信、邮件和 AI 服务自行配置。

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

另一个终端运行：

```powershell
.venv/Scripts/python.exe -m workers.mqtt_consumer
```

健康检查 `GET /api/health` 只能证明 API / 数据库健康，不代表设备认证、MQTT 消费或推理链路全部正常。

## 设备与演示数据

```powershell
# 首次登记规范虚拟设备，安全写入模拟器本地配置
.venv/Scripts/python.exe scripts/seed_dev_device.py --sync-mock-env
# 首次登记真实 Jetson；不会覆盖既有绑定或密钥
.venv/Scripts/python.exe -m scripts.register_real_device
# 正式用户登录创建账号、复制演示底图之后
.venv/Scripts/python.exe scripts/seed_demo_field.py --phone "<你的手机号>"
```

新设备的永久凭据写入 `../local/device_credentials/`，控制台不输出原文，二维码只含一次性配对 Token。已有数据库的设备密钥不能从摘要还原；不要自动重置现有设备。

底图准备见 [素材说明](../../assets/README.md)。数据清理工具要求显式 `--phone`，默认为 dry-run；不要在生产账号上误执行 `--execute`。

## 测试

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

测试使用 SQLite、Mock 服务与临时数据，不需要真实 PostgreSQL、收费短信或真实模型。

## 生产部署

设置 `APP_ENV=production`、`DEBUG=false`、`ENABLE_DOCS=false`、`ENABLE_DEV_TOOLS=false`，使用真实认证服务、HTTPS、严格 CORS 和设备级 MQTT ACL。默认开发 JWT 与空密钥均不能用于生产。

[完整安装](../../docs/SETUP.md) · [通信协议](../../docs/THREE_PARTY_COMMUNICATION_PROTOCOL.md) · [安全说明](../../SECURITY.md)
