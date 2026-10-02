# Leafora Windows 局域网启动与诊断

本目录只管理 `Web/` 侧的本机服务，不修改 Jetson、小程序或根目录配置。当前 DHCP 地址不会
写入源码；启动脚本每次从非虚拟网卡读取 IPv4 并打印可访问 URL。

## 1. 首次准备

1. 确认 `backend/.env` 与 `scripts/mock_jetson/.env` 已配置相同的
   `MQTT_USERNAME` / `MQTT_PASSWORD`；脚本只比较，不输出凭据。
2. 安装 Mosquitto 到 `C:\Program Files\Mosquitto`。
3. 确认没有运行中或待补传巡检后，处理占用 1883 的旧 Broker。若旧 Windows Mosquitto
   服务只监听回环地址，在管理员终端执行以下命令，将其停止并改为手动启动，避免重启电脑后
   再次抢占项目端口。脚本只处理预期安装路径的旧服务，不停止其它 Broker：

   ```powershell
   .\scripts\lan\prepare_mqtt_lan.ps1
   ```

   原服务状态保存在 `local/run/legacy-mosquitto-before.json`。需要恢复时，先停止项目
   Broker，再依据记录恢复服务启动类型；原先为 Auto 时使用
   `Set-Service mosquitto -StartupType Automatic`，原先为 Running 时再执行
   `Start-Service mosquitto`。不要让两个 Broker 同时占用 1883。

4. 如需手机或真实设备访问，以管理员身份单独执行防火墙脚本。启动脚本不会静默更改防火墙：

   ```powershell
   .\scripts\lan\configure_private_firewall.ps1 -Action Enable
   ```

   撤销：

   ```powershell
   .\scripts\lan\configure_private_firewall.ps1 -Action Remove
   ```

规则仅允许“专用网络”上的 TCP 8000 与 1883，不开放 PostgreSQL 5432。

Mosquitto 配置始终以不带 BOM 的 UTF-8 生成，兼容 Windows PowerShell 5.1 与
PowerShell 7。若日志出现 `Unknown configuration variable` 且指向首行，重新运行
`initialize_mosquitto.ps1` 后再启动 Broker，不要手动用带 BOM 的编码保存配置。

## 2. 从全停状态启动

首次从历史虚拟设备配置迁移时先运行：

```powershell
.\scripts\lan\migrate_virtual_device.ps1
```

它只把两份本地 `.env` 的默认设备编号切换为 `TLD_JETSON_001`，登记新设备并安全同步新
设备密钥；既有 `TLD_SIM_001` 和历史数据保持不变。

在 `Web` 目录运行：

```powershell
.\scripts\lan\start_lan.ps1
```

脚本依次检查 PostgreSQL、执行 Alembic 增量迁移、生成带认证的项目本地 Mosquitto 配置，
再启动 Broker、FastAPI、MQTT Consumer、Vue 和模型服务。脚本会等待模型权重真正加载完成，避免图片
已上传但云端推理尚未就绪。仅在明确不需要图片识别时可跳过：

```powershell
.\scripts\lan\start_lan.ps1 -SkipModelService
```

历史命令中的 `-IncludeModelService` 仍兼容，但现在已经不再需要显式传入。

进程在隐藏窗口运行，PID 和日志只写入被 Git 忽略的 `Web/local/`。启动成功后会打印所有可用
非虚拟 IPv4、`/api/health`、Web 地址和 MQTT 地址。手机小程序与真实设备使用这次打印的
IPv4，不把地址写入源码。

停止本脚本启动的进程：

```powershell
.\scripts\lan\stop_lan.ps1
```

脚本只读取 `Web/local/run` 中本轮管理记录，并拒绝处理无法验证的旧记录。

## 3. 只读诊断

```powershell
.\scripts\lan\diagnose_lan.ps1
```

诊断覆盖 PostgreSQL 连接、8000/1883 监听范围、FastAPI 健康检查、MQTT 认证、Consumer
进程、专用网络防火墙规则和非虚拟 IPv4，并区分：

- `PORT_NOT_LISTENING`：服务或端口未启动；
- `LOOPBACK_ONLY`：只允许本机访问；
- `MQTT_AUTH_FAILED`：Broker 可达但账号认证失败；
- `FIREWALL_RULE_MISSING`：本机监听正常，但手机/设备仍可能被防火墙阻断。

诊断不发布 MQTT 消息、不修改数据库、不修改防火墙，也不打印任何密码、设备密钥或 Token。

## 4. 虚拟设备闭环验收

服务与诊断通过后，先让规范虚拟设备走冻结的动态配对接口。开发脚本复用历史虚拟设备的
正式用户归属，不创建用户名账号，也不输出 JWT、配对 Token 或设备密钥：

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.pair_virtual_device_for_acceptance
cd ..
```

随后运行完整生命周期；默认 Broker 为 1883，隔离验收端口可在当前进程设置 `MQTT_PORT`：

```powershell
$env:MQTT_PORT=1883
backend\.venv\Scripts\python.exe scripts\mock_jetson\main.py --samples 10 --image-every 2
```

模拟器必须先收到 START ACK，随后发送 2 Hz V1.2 数据、状态与图片，最后发送 END 并等待 ACK。
最终以数据库中的事件、采样、图片、同步状态和重复 ID 数量为准，而不是只看发布侧计数。
使用模拟器输出的 `inspection_id` 做只读核验：

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.verify_virtual_inspection INS_xxx --expected-samples 10 --expected-images 1
```

断网缓存与恢复验收会在本地 SQLite outbox 中保留原始 `data_id`/`request_id`，恢复后故意重投
同一采样以验证云端幂等，最后上报待同步数量为零：

```powershell
cd ..
$env:MQTT_PORT=1883
backend\.venv\Scripts\python.exe scripts\mock_jetson\offline_replay.py --samples 3
```

再用输出的 `inspection_id` 运行只读数据库核验，要求 `duplicate_data_count=0`、
`pending_sync_count=0`、`status=COMPLETED`。
