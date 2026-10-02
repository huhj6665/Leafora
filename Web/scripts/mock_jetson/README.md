# Virtual Jetson Simulator V3

用于 TLD 平台长期开发与全链路验收的虚拟巡检设备。它不是随机数据脚本，而是一台有固定身份、确定路线、连续传感器状态和完整巡检生命周期的模拟 Jetson。

V3 不主动创建巡检。正常启动后只等待云端 `downlink` 的 `START_INSPECTION/END_INSPECTION`，并通过 `ack` 回执。任务由小程序调用云端 API 创建，Web 只监控。

```powershell
backend\.venv\Scripts\python.exe scripts\mock_jetson\main.py
```

START 的 `run_mode` 决定模式：`FAST_TEST` 约 90 秒、`REALTIME_SIMULATION` 约 15 分钟。两种模式共用 MQTT V1.3、烟田内路线、病害图片上传和持久化 outbox。协议预览可运行 `backend\.venv\Scripts\python.exe scripts\mock_jetson\main.py --dry-run --samples 5`，不会发布 legacy control。

## 架构

```text
main.py
  └─ VirtualJetsonSimulator
      ├─ generators/
      │   ├─ gps_generator.py          确定曲线路径 / 匀速 / 航向
      │   ├─ environment_generator.py  基础值 + 慢趋势 + 相关小噪声
      │   ├─ disease_generator.py      高斯空间聚集病害
      │   ├─ device_generator.py       CPU/内存/温度/存储惯性变化
      │   └─ data_builder.py           inspection_id + data_id + timestamp
      ├─ field_route.py                烟田边界内往复式路线
      ├─ mqtt/publisher.py             downlink 订阅 + ACK/采样/状态发布
      ├─ http_client/uploader.py       设备认证 + 三键图片上传
      ├─ outbox.py                     数据/ACK/图片持久化重试
      └─ images/
          ├─ disease/                  病害图片
          └─ normal/                   正常图片
```

旧 `cli.py`、`data_generator.py`、`mqtt_publisher.py` 与 `image_uploader.py` 保留兼容；新全生命周期验收统一使用 `main.py`。

## 生命周期与 Topic

```text
STANDBY → RUNNING → SYNCING → STANDBY
```

- 云端命令：`tld/device/{device_id}/downlink`
- 设备回执：`tld/device/{device_id}/ack`
- 采样数据：`tld/device/{device_id}/data`
- 设备状态：`tld/device/{device_id}/status`

START/END 由云端发送并携带稳定 `command_id`；设备 ACK `ACCEPTED` 后执行。后端根据设备绑定解析 `owner_user_id`，payload 不包含、也不接受模拟器伪造的 `user_id`。旧 control Topic 仅由后端用于兼容旧设备，本模拟器不再发布。

## 快速开始

从 Web/ 目录执行：

```powershell
# 1. 只看协议和生成效果，不连接任何服务
backend\.venv\Scripts\python.exe scripts\mock_jetson\main.py --dry-run --samples 12

# 2. 启动设备并等待云端命令；模式由 START 的 run_mode 决定
backend\.venv\Scripts\python.exe scripts\mock_jetson\main.py
```

标准启动顺序：PostgreSQL → `alembic upgrade head` → FastAPI → MQTT Consumer → 可选 RT-DETR-L model service → Simulator。

模拟器固定读取 `scripts/mock_jetson/.env`，不依赖启动命令所在目录；进程环境变量优先级更高。HTTP 调试日志仅显示密钥是否已配置及长度，不输出凭据内容。

## 关键参数

| 参数 / 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| START `run_mode` | `FAST_TEST` | FAST_TEST 90 秒；REALTIME_SIMULATION 约 15 分钟 |
| `--samples` | `5` | 仅 dry-run 协议预览使用 |
| `--dry-run` | 否 | 离线打印协议 |
| `--seed` | `20260924` | 可复现实验种子 |
| `MOCK_SPEED_MPS` | `1.2` | 移动速度 |
| `MOCK_DISEASE_RATE` | `0.82` | 病害中心峰值概率 |
| `MOCK_DISEASE_CLUSTER_COUNT` | `2` | 空间病害中心数 |
| `MOCK_DISEASE_SIGMA_M` | `22` | 高斯衰减半径尺度 |
| `MOCK_DEVICE_SECRET` | 空 | HTTP 图片上传设备凭据 |
| `MOCK_DEVICE_ID` | `TLD_JETSON_001` | 规范虚拟设备；`TLD_SIM_001` 仅保留历史兼容 |
| `MOCK_HTTP_DEBUG` | `true` | 输出脱敏设备配置、HTTP 状态码和响应体 |
| `MOCK_OUTBOX_PATH` | `local/outbox.sqlite3` | 离线重试队列 |

完整模板见 `.env.example`。

## 数据模型

每个采样点带有：

- `inspection_id`：一次巡检全程固定；
- `field_id/field_version`：来自任务烟田快照；
- `data_id`：按任务和序号稳定生成，重试保持不变；
- `run_mode/data_provenance/flight_status`：V1.3 任务模式、模拟来源和进度；
- `timestamp`：模拟时间轴，环境采样与图片沿用同一值；
- 确定路线上的 GPS/RTK、速度、航向；
- 连续温度、湿度、CO₂、光照；
- 基于病害中心距离的检测结果；
- CPU 温度、CPU、内存、存储和网络状态。

图片 HTTP multipart 同时发送 `inspection_id + data_id + timestamp + image_id`，请求头发送 `X-Device-ID + X-Device-Secret`。后端对事件、记录、设备和时间做交叉校验。

## 图片规则

- 阳性点从 `images/disease/` 循环选择；
- 阴性点不上传图片；
- 素材允许复用，但 `image_id=IMG_{data_id}` 固定；
- 上传前复制到 outbox 临时目录，成功后只删除临时副本；
- 目录为空时，为兼容旧项目回退到 `test_images/`。

## 验收

```powershell
# 后端与兼容测试
cd backend
.venv\Scripts\python.exe -m pytest -q

# 模拟器生成模型测试
cd ..
backend\.venv\Scripts\python.exe -m pytest -q scripts\mock_jetson\tests

# 前端构建
cd frontend
npm run build
```

一次完整联调后，应在网站看到一个 `COMPLETED` 任务、A-01 底图内连续轨迹、环境曲线、风险网格、病害图片及云端推理状态。

## 安全约束

- 不在 JSON 中发送用户 ID、用户密码或设备密钥；
- 设备密钥只放请求头，服务端保存 bcrypt 摘要；
- 日志不打印 Token、密码或设备密钥；
- 所有模拟数据均为开发数据，不代表真实农业测量。
