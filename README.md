# Leafora

烟田智能巡检平台，连接 Jetson 边缘采集、云端数据管理与微信小程序现场操作。

平台将巡检轨迹、环境读数、病虫害图片和识别结果关联到同一次任务，支持历史回看、风险分区和农业助手分析。风险分仅用于辅助巡检，不构成专业农业诊断。

## 功能

- 手机号验证码、手机号密码与小程序确认的 Web 扫码登录。
- 一次性二维码配对设备；一个设备同时归属一个主用户。
- 小程序选择烟田和设备、请求开始与结束任务；Web 管理和监控。
- MQTT 命令与回执、HTTP 病害图片上传、断网缓存和幂等补传。
- 烟田底图、轨迹、病害筛选、环境数据、原图与识别图查看。
- Jetson TensorRT 边缘识别，可选 RT-DETR-L 云端推理。
- 农业助手：平台记录查询、资料检索与可选天气、联网检索和大模型服务。
- 无真实硬件时可使用独立身份的虚拟设备测试闭环。

## 架构

```text
微信小程序 ── HTTP ── 云端 FastAPI / PostgreSQL ── HTTP ── Web 管理端
                            │
                     MQTT 命令 / 回执 / 采样
                            │
                         Jetson
                            └── HTTP 病害图片上传
```

任务由小程序发起；Web 不提供替代小程序的远程启停入口。本项目不实现无人机电机、姿态或飞控航线控制。

## 目录

| 目录 | 内容 |
| --- | --- |
| `Web/backend/` | FastAPI、数据模型、Alembic 迁移与 MQTT Consumer |
| `Web/frontend/` | Vue 3、TypeScript、Element Plus 数据管理界面 |
| `Web/model_service/` | 可选云端识别服务，权重单独配置 |
| `Web/scripts/mock_jetson/` | 虚拟设备、离线队列与闭环测试 |
| `Web/scripts/lan/` | Windows 局域网服务启动与诊断 |
| `TLD_project/` | 真实 Jetson 采集、识别和通信 |
| `weixinapp/` | 微信小程序现场操作端 |
| `assets/` | 演示烟田素材 |
| `docs/` | 通信协议、安装及发布说明 |
| `tools/` | 发布前审查和无历史导出工具 |

## 快速开始

详细配置与命令见 [安装与运行](docs/SETUP.md)。

1. 准备 Python 3.10+、Node.js 22.12+、PostgreSQL 与 Mosquitto。
2. 从各端的 `.env.example` 创建本地配置，生成自己的 JWT、MQTT 和数据库凭据。
3. 安装依赖、执行数据库迁移，启动 API、MQTT Consumer 和 Web 前端。
4. 在微信开发者工具导入 `weixinapp/`，配置自己的 AppID 和开发电脑地址。
5. 登记并扫码绑定设备，从小程序发起任务。

源码不包含真实账号、数据库、上传图片、设备密钥、模型权重或已安装依赖。重新部署需要自行配置这些内容。

## Jetson 与虚拟设备

真实 Jetson 固定编号 `TLD_SIM_002`；规范虚拟设备使用 `TLD_JETSON_001`，历史 `TLD_SIM_001` 仅作兼容。

真实设备目标环境为 Python 3.6.9、JetPack 4.6.6、TensorRT 8.2.19、OpenCV 3.2.0。默认 `python3 main.py` 仅进行通信配置与配对；`--hardware` 才加载硬件。Tkinter 联调暂未恢复。普通 GPS Fix 是启动最低条件，不要求网络 RTK。

参见 [Jetson 说明](TLD_project/README.md)、[实机验收](TLD_project/JETSON_ACCEPTANCE.md) 与 [通信协议](docs/THREE_PARTY_COMMUNICATION_PROTOCOL.md)。演示地图的坐标校准是模拟数据，不代表真实测绘结果。

## 验证

在项目根目录执行（先安装依赖）：

```powershell
Web/backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider Web/backend/tests
Web/backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider Web/scripts/mock_jetson/tests
node weixinapp/test/run-tests.js
python -m unittest discover -s TLD_project/test -t TLD_project -p "test_*.py"
python TLD_project/tools/check_py36_syntax.py
```

Web 构建：在 `Web/frontend/` 执行 `npm ci`、`npm run build`。Windows 的离线单测不等同真实 Jetson、手机或飞行验收。

## 安全与发布

- 所有真实凭据只保存在被忽略的本地配置中；不要把凭据放到二维码、截图或日志。
- `VITE_*` 会进入浏览器构建产物，只能用于允许公开的前端配置，不能存放服务端密钥。
- 生产部署必须关闭调试与开发工具，配置 HTTPS、MQTT TLS / ACL、备份及访问控制。
- [安全说明](SECURITY.md) · [GitHub 上传指南](docs/GITHUB_PUBLISH.md) · [发布审查记录](docs/RELEASE_REVIEW.md)

## 授权与素材

本次整理未擅自选择开源许可证。公开仓库不等于授予所有人使用或再发布权；正式开源前请由项目所有者选定许可证，并确认图片、训练数据、模型权重及第三方依赖的授权。参见 [素材与模型说明](assets/README.md)。
