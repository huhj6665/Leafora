# 小程序巡检 API 契约（V2.0）

更新时间：2026-09-30。所有接口都使用正式手机号账号的 Bearer JWT；服务端从 JWT、设备绑定和烟田归属判定权限，不接受客户端传入 `user_id`。统一响应为 `{code,message,data}`。

## 烟田与设备

- `GET /api/fields`：当前用户烟田。
- `GET /api/fields/{field_id}`：烟田详情、版本、边界、控制点和转换参数。
- `GET /api/device/list`：已绑定设备；`standard_state=READY` 才能开始。
- `GET /api/fields/{field_id}/base-map`：鉴权底图。

## 开始任务

`POST /api/inspections/start`

```json
{"field_id":"FIELD_A01","device_id":"TLD_JETSON_001","client_request_id":"wx-start-0001","name":"A-01 上午巡检","run_mode":"FAST_TEST"}
```

`client_request_id` 在同一用户范围幂等；重试返回同一 `inspection_id` 和 `command_id`。`run_mode` 可为 `FAST_TEST`、`REALTIME_SIMULATION` 或 `REAL_DEVICE`。创建成功只代表云端记录和命令已持久化；仅当返回的 START 命令状态为 `ACCEPTED` 且任务为 `RUNNING` 时，小程序才显示“巡检已开始”。

离线、未绑定、烟田非 READY、设备非 READY 或冲突任务返回 HTTP 409，并在 `data.device_state` 提供可理解状态。命令一分钟未 ACK 进入 `EXPIRED`，任务进入 `FAILED`。

## 查询状态

- `GET /api/inspections/current?device_id=TLD_JETSON_001`
- `GET /api/inspections/{inspection_id}/status`
- `GET /api/inspections/history`
- `GET /api/inspections/{inspection_id}`

任务状态：`START_REQUESTED → STARTING → RUNNING ↔ RUNNING_OFFLINE → ENDING → SYNCING → COMPLETED`，异常终态为 `FAILED/CANCELLED`。

命令状态：`PENDING → DELIVERED → ACCEPTED → EXECUTING → COMPLETED`，异常终态为 `REJECTED/FAILED/EXPIRED/CANCELLED`。

## 结束任务

`POST /api/inspections/{inspection_id}/end`

```json
{"client_request_id":"wx-end-0001"}
```

同一任务重复结束复用同一个 END 命令。设备 ACK `ACCEPTED` 后任务进入 `SYNCING`；只有 END 已接受且设备状态上报 `pending_sync_count=0` 时才进入 `COMPLETED`。离线时不会假装结束成功。

## 实时与空间结果

- `GET /api/devices/{device_id}/live`
- `GET /api/inspections/{inspection_id}/live`
- `GET /api/inspections/{inspection_id}/spatial`

实时响应含原样 `raw`、三点中值加 EMA 的 `display`、`received_at`、`age_ms` 和 `link_state`。0–3 秒为 `LIVE`，3–10 秒为 `DELAYED`，超过 10 秒为 `DISCONNECTED`。状态、告警和检测结果不平滑。

空间响应含烟田快照、像素轨迹、风险网格、病害点和图片引用。网格公式为 `100 × Σ(每个有效采样点最高置信度) ÷ 有效采样点数`；少于 3 个有效样本为 `INSUFFICIENT`。阈值：`LOW <15`、`ATTENTION 15–<35`、`REVIEW 35–<60`、`HIGH >=60`。

## MQTT 依赖

云端向 `tld/device/{id}/downlink` 下发 `START_INSPECTION/END_INSPECTION`；设备向 `.../ack` 回执。新虚拟设备发送 MQTT V1.3，可选字段为 `field_id`、`field_version`、`run_mode`、`data_provenance`、`flight_status`。V1.0/V1.1/V1.2 和旧 `control START/END` 继续兼容。
