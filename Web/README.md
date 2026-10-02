# Leafora Web

Web 是管理与监控端，不替代小程序发起真实任务。包含 FastAPI / PostgreSQL 后端、MQTT Consumer、Vue 3 前端、可选 RT-DETR-L 模型服务与虚拟设备。

## 安装与运行

统一步骤见 [安装指南](../docs/SETUP.md)。需要 Python 3.10+、Node.js 22.12+、PostgreSQL 和 MQTT Broker。

- 后端配置：`backend/.env.example`，复制到本地 `.env` 并填写独立凭据。
- 前端配置：`frontend/.env.example`；服务端密钥不能进入 `VITE_*`。
- 模型配置：`model_service/.env.example`，权重自行提供。
- 虚拟设备：`scripts/mock_jetson/.env.example`，身份为 `TLD_JETSON_001`。
- 真实设备：`TLD_SIM_002`，通过 `backend/scripts/register_real_device.py` 登记。

## 目录

```text
Web/
├── backend/         API、迁移、业务服务和 MQTT 消费
├── frontend/        数据管理界面
├── model_service/   可选独立推理服务
├── infrastructure/  Broker 模板、反向代理示例
├── scripts/
│   ├── lan/         局域网启动、诊断和防火墙工具
│   └── mock_jetson/ 虚拟设备与离线补传
└── docs/            接口契约与助手配置
```

## 常用命令

在 `Web/backend/` 安装依赖、配置数据库后：

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 另开终端（同一目录）
.venv/Scripts/python.exe -m workers.mqtt_consumer
```

前端在 `Web/frontend/` 运行 `npm ci`、`npm run dev` 或 `npm run build`。也可从 `Web/` 使用 [局域网启动脚本](scripts/lan/README.md)，勿重复启动已有服务。

## 测试

在 `Web/backend/`：

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

虚拟设备测试在 `Web/`：

```powershell
backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider scripts/mock_jetson/tests
```

测试不代表真实模型、手机、GPS 或公网部署已经验收。

## 更多说明

- [后端](backend/README.md) · [前端](frontend/README.md) · [模型服务](model_service/README.md)
- [虚拟设备](scripts/mock_jetson/README.md)
- [小程序接口](docs/MINIPROGRAM_API_CONTRACT.md)
- [农业助手接口](docs/ASSISTANT_API_CONTRACT.md) · [配置](docs/ASSISTANT_SETUP_AND_ACCEPTANCE.md)
- [通信协议](../docs/THREE_PARTY_COMMUNICATION_PROTOCOL.md) · [安全](../SECURITY.md)

源码不携带真实配置、用户数据、安装好的依赖或模型文件，克隆后须重新部署。
