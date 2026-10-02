# TLD 三方通信协议基线

版本：0.3

冻结日期：2026-10-01（V0.3 增量；既有 Topic、REST 路径及消息 schema_version 不变）

适用范围：Jetson/虚拟设备、云端/Web、微信小程序

## 1. 架构与职责

```text
微信小程序 -- HTTPS REST --> 云端 -- MQTT downlink --> Jetson/虚拟设备
微信小程序 <-- HTTPS REST -- 云端 <-- MQTT/HTTP ------ Jetson/虚拟设备
```

- 云端是用户、设备、烟田、绑定关系、巡检任务、命令状态和数据权限的唯一可信中心。
- 小程序是现场业务操作端，负责选烟田、选设备、申请开始/结束任务和查看结果。
- Web 负责烟田/设备/巡检管理、实时监控和数据分析，本阶段不提供替代小程序的启停入口。
- 小程序不连接 MQTT，也不持续直连 Jetson。设备二维码只用于一次性配对。
- 云端和小程序只下发业务级任务命令，不控制无人机电机、姿态或航线；运动控制与采集执行属于 Jetson/飞控。
- Jetson 使用 MQTT 传输状态、任务回执和结构化采样，使用 HTTP 上传病害图片。

## 2. 冻结业务规则

1. 一个设备同一时间只能绑定一个主用户，一个主用户可绑定多个设备。
2. 手机号是正式用户唯一主身份；验证码首次登录自动创建账号，支持验证码和手机号密码登录。
3. Web 小程序扫码登录与 Jetson 设备配对是两个独立协议。
4. 烟田归属用户，不永久绑定设备；每次巡检绑定当次 `field_id`、`device_id` 和烟田版本快照。
5. 用户在小程序发起开始/结束请求，云端鉴权并通过 MQTT 下发命令；Web 本阶段只管理和监控。
6. 开始任务时设备必须在线并返回 `ACCEPTED`；开始后断网继续运行和持久化缓存，恢复后补传。
7. 普通 GPS Fix 是开始采集最低条件；RTK Float/Fixed 只影响精度等级，不阻止开始。
8. 只有识别出病虫害的图片才保存并上传；确认上传后设备可删除本地文件。
9. 用户、设备、烟田和图片归属只由云端认证及绑定关系确定，不信任客户端传入的 `user_id`。

## 3. 身份、认证与局域网测试

- Web 和小程序使用云端 JWT；用户身份从 JWT 解析。
- 设备 HTTP 使用 `X-Device-ID` 与永久设备密钥；永久密钥不进入二维码。
- 本地开发允许小程序首次进入填写电脑局域网 IPv4。客户端据此形成统一 API Base URL，并在进入业务页前完成健康检查。
- IP 配置只用于开发构建，必须集中存储且可重置；禁止在各页面硬编码 URL。
- 小程序真机与电脑/Jetson 必须网络互通；开发者工具需按当前微信开发设置处理本地合法域名校验。

## 4. 核心 ID 与幂等

| 字段 | 含义 |
|---|---|
| `device_id` | 设备永久编号 |
| `field_id` | 烟田永久编号 |
| `field_version` | 本次任务使用的烟田快照版本 |
| `inspection_id` | 一次巡检任务 |
| `command_id` | 一次云端下行命令及其重试 |
| `data_id` | 一个采样点 |
| `image_id` | 一张病害图片 |
| `pairing_session_id` / `pairing_token` | 一次设备配对会话/凭证 |

同一业务对象重试必须复用原 ID。数据库需用唯一约束或幂等表防止重复任务、重复采样和重复图片。

## 5. MQTT Topic

| Topic | 方向 | QoS | Retain | 用途 |
|---|---|---:|---:|---|
| `tld/device/{id}/data` | 设备→云端 | 1 | 否 | 巡检采样 |
| `tld/device/{id}/status` | 设备→云端 | 1 | 是 | 心跳、模块、同步和运行状态 |
| `tld/device/{id}/downlink` | 云端→设备 | 1 | 否 | 配对结果、任务命令、配置通知 |
| `tld/device/{id}/ack` | 设备→云端 | 1 | 否 | 下行命令回执 |
| `tld/device/{id}/control` | 设备→云端 | 1 | 否 | 仅兼容旧设备主动 START/END，不作为新流程入口 |

设备为 `status` 设置 Last Will。命令、数据和 ACK 不 Retain。

### 5.1 真实设备心跳枚举（V0.3）

- `type=device_status`；`communication_status` 为 `ONLINE/OFFLINE`，Last Will 必须明确为 `OFFLINE`，不能只传 `online=false`。
- `operating_status`：`STARTUP` 为通信已启动但硬件未启动或前检查未通过；`SHUTDOWN` 为无活动任务且已通过绑定、硬件/GPS、存储前检查的待命设备；`RUNNING` 为正在执行任务；`ERROR` 为阻断性故障。不得仅因 MQTT 已连接而报告 `SHUTDOWN`/业务 `READY`。
- `gps_fix` 与 `rtk_status` 使用 `NO_FIX/GPS_FIX/DGPS/RTK_FLOAT/RTK_FIXED`；未配置 NTRIP 不阻断普通 GPS，不伪造 RTK 状态。
- `camera_status/inference_status` 使用 `NOT_STARTED/READY/ERROR`。
- `sync_status` 使用 `IDLE`（无任务且无积压）、`PENDING`（有任务待同步数据/图片）、`SYNCED`（本任务业务队列已清空）；`pending_sync_count` 为非负整数。
- 活动或结束同步通知携带对应 `inspection_id`；有活动任务时统计该任务待同步的数据/图片（包括在途业务对象），空闲时可统计总积压。命令 ACK 自身不计入业务待同步数，避免最终 ACK 等待自身清空。
- 云端结合绑定关系、心跳新鲜度及明确的模块错误推导业务就绪状态；旧设备缺省分项字段继续兼容，新设备不得用缺省值掩盖未启动硬件。

## 6. 新任务闭环

### 6.1 小程序请求开始

```text
POST /api/inspections/start
Authorization: Bearer <user JWT>
```

请求只包含用户选择：`field_id`、`device_id`、可选任务名称和客户端请求 ID。云端必须校验用户归属、烟田 READY、设备已绑定且 READY、无冲突任务，然后事务性创建巡检、烟田版本快照和 START 命令。

云端下发：

```json
{
  "type": "inspection_command",
  "schema_version": "2.0",
  "command_id": "CMD_xxx",
  "command": "START_INSPECTION",
  "inspection_id": "INS_xxx",
  "device_id": "TLD_JETSON_001",
  "field_id": "FIELD_A01",
  "field_version": 1,
  "run_mode": "REALTIME_SIMULATION",
  "timestamp": "2026-09-30T08:00:00Z",
  "expires_at": "2026-09-30T08:01:00Z"
}
```

设备回执：

```json
{
  "type": "command_ack",
  "schema_version": "2.0",
  "command_id": "CMD_xxx",
  "inspection_id": "INS_xxx",
  "device_id": "TLD_JETSON_001",
  "command": "START_INSPECTION",
  "status": "ACCEPTED",
  "phase": "RUNNING",
  "reason_code": null,
  "timestamp": "2026-09-30T08:00:01Z"
}
```

命令状态：

```text
PENDING → DELIVERED → ACCEPTED → EXECUTING → COMPLETED
                    ↘ REJECTED / FAILED / EXPIRED / CANCELLED
```

巡检状态：

```text
START_REQUESTED → STARTING → RUNNING ↔ RUNNING_OFFLINE
                                   → ENDING → SYNCING → COMPLETED
                                   ↘ FAILED / CANCELLED
```

小程序轮询任务/命令状态；只有设备 `ACCEPTED` 才显示“巡检已开始”。

### 6.2 小程序请求结束

```text
POST /api/inspections/{inspection_id}/end
```

云端下发 `END_INSPECTION`。设备收到后停止产生新采样，回传 ACK 和摘要，继续补传队列。云端只有在 END 被接受且待同步数据归零后进入 `COMPLETED`。若手机或云端离线，结束请求不能假装成功。

### 6.3 END 两阶段确认与最终入库证据（V0.3）

适用于云端持久化的 V2.0 `END_INSPECTION` 命令；旧 `control` 兼容流程见第 11 节。

1. 设备关闭新采样入口，等待正在生成的最后一条采样/病害图片完成本地持久化，然后冻结停止摘要。停止动作、采样计数和最后采样元数据必须一致，不能 ACK 后再产生一条新业务采样。
2. 第一次回执：`type=command_ack`、`schema_version=2.0`、`command=END_INSPECTION`、`status=ACCEPTED`、`phase=SYNCING`，复用本次 END 的 `command_id/inspection_id/device_id`。云端只进入 `SYNCING`，不得读取旧心跳零值直接完成。
3. 数据 MQTT 获得 Broker PUBACK、图片获得业务成功响应后，设备业务队列及在途数据/图片归零，持久化最终回执：同一命令标识，`status=COMPLETED`、`phase=COMPLETED`。PUBACK 仅表示 Broker 接收，不等同云端入库；最终回执仍需云端核验。

两个阶段都必须带 `summary`，字段冻结如下：

| 字段 | 类型与含义 |
|---|---|
| `sampling_stopped` | 布尔值，必须为 `true` |
| `last_data_id` | 本任务最后一条已本地持久化的业务采样 ID；零采样时为 `null` |
| `last_sequence` | 上述采样的非负整数序号；零采样时为 `null`，不规定旧设备序号从 0 或 1 起始 |
| `sample_count` | 本任务已本地持久化的唯一业务采样总数，非负整数；不是发布尝试次数 |
| `pending_sync_count` | 本任务待同步数据/图片及在途业务对象数；最终阶段必须为 `0`，不包含 ACK 自身 |

除 `pending_sync_count` 可从非负值降至 `0` 外，两阶段停止摘要必须相同。`sample_count=0` 时两项 last 字段必须同时为 `null`；有样本时两项必须同时有值。禁止为了使任务完成丢弃失败采样/图片或重算更小的停止摘要。

云端完成条件与乱序处理：

- 分别持久化 ACCEPTED 和 COMPLETED 两阶段证据，按 END `command_id` 关联既有命令、任务和认证设备。仅验证 ACK 内自报的 ID 不够，必须与持久化关联一致。
- 最终 ACK 先到时先保存，不伪造 ACCEPTED 证据；重复/重启重发允许，状态不倒退，已 ACCEPTED 不能阻挡后续 COMPLETED 阶段。
- 两阶段匹配、最终待同步数为零后，云端还须核验该设备该任务的最后 `data_id/sequence` 已入库，且任务唯一采样数与 `sample_count` 一致，避免只有最后一条到达但中间采样缺失。零采样任务只在两阶段匹配且库内确实无采样时完成。
- 最终 ACK 早于数据消费时保持 `SYNCING`，后续数据入库必须触发重新核验或持久化的有界核验机制；不能只在 ACK 到达瞬间判断一次。
- 普通 `status` 可更新设备/同步展示，但不能单独完成 V2.0 任务。云端任务及 END 命令仅在上述证据满足后进入 `COMPLETED`；云端二次模型推理状态单独记录，不等同设备补传状态。
- 设备持久化两阶段回执，允许断网、重启及重复 END 后重发；最终阶段重发需同时保证 ACCEPTED 证据可重新送达。不得清除全部任务元数据后失去最终通知能力。
- `expires_at` 控制尚未执行的新命令；已执行命令的缓存回执和已接受任务的最终补传不因原命令过期而失效。重复处理先查询持久化执行结果，不能将已执行命令重新判为未执行的过期命令。
- START 包含烟田快照，需校验快照 `field_id/version` 与命令一致。END 只需携带已有任务的 `field_id/field_version`，无需重复快照或 `run_mode`，设备使用持久化 START 快照。

## 7. 烟田数据模型与演示烟田

烟田至少保存：`field_id`、所有者、名称、状态、数据来源、校准状态、坐标系、底图、像素边界、WGS84 GeoJSON 边界、控制点、正反向坐标变换参数和版本。

本轮固定演示数据：

- 名称：`演示烟田 A-01`
- 归属：由导入命令的 `--phone` 参数指定已有正式账号（运行时查询用户，不硬编码个人手机号或 user_id）
- 数据来源：`DEMO_IMPORT`
- 校准状态：`SIMULATED`
- 状态：`READY`
- 坐标系：`WGS84`
- 底图：`assets/demo-field-a01.jpg`
- 边界：只取图片下方最大的一整块绿色烟草田；上方两块不属于 A-01

本轮 WGS84 边界与控制点允许固定、可复现地模拟生成，但必须明确标记为模拟数据。虚拟设备轨迹使用边界内缩缓冲区；加噪后若越界必须投影回安全区。

## 8. 采样与图片

采样保持向后兼容 V1.0/V1.1/V1.2，并新增可选字段：

```json
{
  "schema_version": "1.3",
  "device_id": "TLD_JETSON_001",
  "inspection_id": "INS_xxx",
  "field_id": "FIELD_A01",
  "field_version": 1,
  "data_id": "DATA_xxx",
  "sequence": 123,
  "timestamp": "2026-09-30T08:00:00.500Z",
  "run_mode": "REALTIME_SIMULATION",
  "data_provenance": "SIMULATED",
  "flight_status": {"progress": 0.42, "phase": "SURVEYING"},
  "location": {},
  "environment": {},
  "detection": {},
  "device_status": {}
}
```

完整 `location/environment/detection/device_status` 字段沿用 V1.2。HTTP 图片上传继续使用设备认证和 `inspection_id/data_id/image_id` 关联，只上传有病害检测结果的图片；重试复用 `image_id`。

### 8.1 无效硬件读数的空值兼容（V0.3）

- V1.0–V1.3 均允许 `location.latitude/longitude` 在无有效定位时为 `null`，此时 `position_valid=false`；`position_valid=true` 必须具备有限且范围合法的经纬度。有效数值配合 `position_valid=false` 可表示失效的最近读数，但不得作有效定位使用。
- `environment.sampled_at` 在从未取得环境样本时可为 `null`，此时 `valid=false`；有效环境块必须有真实采样时间和所要求的有效读数。部分传感器失败时保留仍有效的字段，整体 `valid=false`，不补零或虚构时间。
- Schema、数据库可空列、入库、实时与统计/空间计算须同时兼容；原始 JSON 保留 `null`，无效位置不生成轨迹/病害地图点，未知读数不算作零或有效样本。
- 硬件读数无效不等于业务采样不存在：已接受的结构化消息仍按唯一 `data_id` 计入第 6.3 节 `sample_count` 入库核验，但不计入有效定位/环境统计。
- 真实设备使用 `run_mode=REAL_DEVICE`、`data_provenance=DEVICE`；虚拟设备保持 `FAST_TEST/REALTIME_SIMULATION`、`SIMULATED`。真实设备来源不改变烟田 `calibration_status=SIMULATED` 的含义，不冒充真实地图标定或飞行进度。

## 9. 实时数据 API

浏览器与小程序不连接 MQTT。云端提供鉴权后的设备最新状态接口，例如：

```text
GET /api/devices/{device_id}/live
GET /api/inspections/{inspection_id}/live
```

返回原始最新 JSON、结构化展示数据、接收时间和陈旧度。原始数据不修改；展示层可做 3 点中值加 EMA。状态、告警和识别结果不平滑。建议 3 秒标记延迟，10 秒标记链路中断。

## 10. 小程序范围

本轮包含：局域网 IP 配置和连通性校验、手机号登录、扫码配对、设备状态、烟田列表/详情、选择烟田和设备、开始/结束任务、等待 ACK、运行状态、历史记录、烟田底图上的轨迹/风险分区和病害图片。

小程序不直接控制无人机，不直接连 MQTT，不把模拟任务描述为真实飞行。完整真实烟田采集/标定流程后续在同一烟田 API 上扩展；当前闭环使用预置 A-01。

## 11. 兼容策略

- 后端继续接受旧 MQTT V1.0/V1.1/V1.2 和旧设备主动 START/END，但新小程序只走 V2.0 云端命令流程。
- 新字段先按可选字段扩展；不得破坏历史设备接入。
- 4G/公网部署只替换 Base URL、Broker 地址和 TLS/ACL，不改变 REST/MQTT 业务语义。
- 本地开发 IP 配置必须集中封装，迁移公网时只更换配置，不修改业务页面。
- V0.3 只增补既有 ACK `summary` 字段与阶段语义，不更换 Topic/REST 或 `schema_version=2.0/1.3`。新 Web、真实 Jetson 和规范虚拟设备共同采用第 6.3 节；旧 V2.0 ACK 缺少停止摘要时仍可保存接受状态，但不能退回“心跳零值即完成”，需升级设备后补发证据，不伪造历史证据，不批量改写已完成历史任务。
- 旧设备主动 `control START/END` 保留原兼容分支，与持久化 V2.0 命令流程分开；不得用旧 `control` 消息绕过新任务的两阶段完成要求。
- 云端对尚未接受的 PENDING/DELIVERED 命令持久化有界重投递，复用原命令 ID、任务 ID、请求 ID 和有效期；收到接受/拒绝/终态证据后停止投递。HTTP 幂等响应不能被误认为已经重发成功。
