# 安装与运行

以下命令使用 Windows PowerShell；Linux 将虚拟环境解释器路径改为 `.venv/bin/python`。所有配置由部署者重新填写，不恢复私有备份中的用户数据到公开源码。

## 1. 前置环境

- 云端：Python 3.10+、PostgreSQL（可用数据库与最小权限账号）、Mosquitto。
- 前端：Node.js 22.12+（当前锁定 Vite 的要求为 `^20.19.0 || >=22.12.0`）、npm。
- 小程序：微信开发者工具；扫码、真机网络及正式登录需要自己的 AppID。
- Jetson：Python 3.6.9、JetPack 4.6.6、TensorRT 8.2.19、OpenCV 3.2.0，不能复用 Windows 虚拟环境。

## 2. 安装依赖与创建配置

在项目根目录运行：

```powershell
python -m venv Web/backend/.venv
Web/backend/.venv/Scripts/python.exe -m pip install -r Web/backend/requirements.txt
Copy-Item Web/backend/.env.example Web/backend/.env
Copy-Item Web/frontend/.env.example Web/frontend/.env
Copy-Item Web/scripts/mock_jetson/.env.example Web/scripts/mock_jetson/.env
Set-Location Web/frontend
npm ci
Set-Location ../..
```

复制操作仅用于首次部署；已有本地配置时不要覆盖。编辑 `Web/backend/.env`：

- 设置 `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`，数据库和账号需要预先创建。
- 设置随机 `JWT_SECRET_KEY`。可在私人终端使用 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成，不贴到日志或仓库。
- 设置非空 `MQTT_USERNAME/MQTT_PASSWORD`，虚拟设备 `.env` 使用相同 Broker 凭据。
- 本地开发使用 `SMS_PROVIDER=mock`；真实短信需自行配置供应商凭据、签名和模板。
- SMTP、大模型、天气和检索服务可选，缺少凭据时对应能力不可用；这不等于全功能演示已经部署。

高德浏览器配置在前端 `.env`；服务端 Key 不进入 `VITE_*`。后端代理默认 `http://127.0.0.1:8000`，其他目标可在启动终端设置 `VITE_DEV_API_TARGET`。

## 3. 数据库与服务

```powershell
Set-Location Web/backend
.venv/Scripts/python.exe -m alembic upgrade head
Set-Location ..
./scripts/lan/start_lan.ps1
```

局域网脚本生成带认证的 Broker 配置，启动 API、Consumer 和前端；详细选项、端口冲突和防火墙操作见 [局域网说明](../Web/scripts/lan/README.md)。不要重复启动已有服务，也不要在活动任务期间更换 Broker。

已有自己的 Broker 时可使用 `-SkipMosquitto`；后端 `.env` 的地址必须与启动参数一致。手动运行 API 与 Consumer 的方式（分别在独立终端、`Web/backend/` 目录）：

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
.venv/Scripts/python.exe -m workers.mqtt_consumer
```

前端在 `Web/frontend/` 目录运行 `npm run dev`。局域网脚本用于开发，公网部署另行配置反向代理、HTTPS、MQTT TLS / ACL，不能直接把开发端口全部暴露到互联网。

## 4. 小程序

导入 `weixinapp/`。源码模板使用 `touristappid`，正式真机和扫码需换为自己的 AppID；AppID 不是 AppSecret，不要写入任何 AppSecret。

将本地 AppID 写入已忽略的 `project.private.config.json`（开发者工具版本支持时），或只在本地修改 `project.config.json`，再次公开前恢复 `touristappid`。局域网测试仅在开发环境关闭合法域名校验并启用局域网调试；上线必须配置合法 HTTPS 域名。

首次进入“云端连接”填写运行 API 的电脑 IPv4，手机与电脑必须互通。完成手机号登录后扫码绑定设备。

```powershell
node weixinapp/test/run-tests.js
node weixinapp/test/check-project.js
# 配置正式 AppID 后可进一步严格检查
node weixinapp/test/check-project.js --require-appid
```

## 5. 虚拟设备与演示烟田

在 `Web/backend/` 目录登记虚拟设备：

```powershell
.venv/Scripts/python.exe scripts/seed_dev_device.py --sync-mock-env
```

首次生成的密钥只写入本地文件，数据库仅存摘要。已有设备不会自动重置密钥；不要为了演示随意轮换。

底图复制步骤见 [素材说明](../assets/README.md)。用自己的已创建手机号账号导入演示烟田：

```powershell
# Web/backend/ 目录；将占位内容换为自己的正式账号
.venv/Scripts/python.exe scripts/seed_demo_field.py --phone "<你的手机号>"
```

在 `Web/` 目录启动虚拟设备：

```powershell
backend/.venv/Scripts/python.exe scripts/mock_jetson/main.py
```

扫码工具与更多选项见 [虚拟设备说明](../Web/scripts/mock_jetson/README.md)。设备在收到云端命令前不会自行创建任务。病害图片测试素材自行放到模拟器指定目录，不随源码分发。

## 6. 真实 Jetson

在 `Web/backend/` 登记真实设备：

```powershell
.venv/Scripts/python.exe -m scripts.register_real_device
```

首次凭据写入 `Web/local/device_credentials/TLD_SIM_002.env`；该目录不得上传。将源码复制到 Jetson，不覆盖既有 `runtime/` 或模型。在 Jetson 运行：

```bash
cd ~/TLD_project
python3 main.py
# 网络向导、菜单 3 配置设备永久密钥、菜单 2 配对
# 退出通信模式后，静置硬件采集测试：
python3 main.py --hardware
```

网络向导填写云端电脑地址，不是 Jetson 自身 IP。菜单 `10` 检查绑定、在线、相机、识别、普通 GPS Fix 和存储；未配置 NTRIP / RTK 只影响精度提醒。详细兼容约束与实机步骤见 [Jetson 文档](../TLD_project/README.md)。

## 7. 可选云端模型与农业助手

模型环境独立安装，权重单独提供。见 [模型服务文档](../Web/model_service/README.md)，运行后设置后端 `MODEL_SERVICE_URL`。

助手的模型、天气、资料检索配置见 [助手配置与验收](../Web/docs/ASSISTANT_SETUP_AND_ACCEPTANCE.md)。运行时系统提示是业务代码的一部分，发布整理没有删除它们。

## 8. 验收边界

从小程序请求 START → 等待 ACCEPTED → 采样、识别和上传 → 请求 END → 补传 → 云端确认 COMPLETED。Broker PUBACK 不是云端入库成功证明。

Mock、模拟坐标和桌面硬件测试都不表示真实飞行验收已完成。数据权限、设备绑定及任务完成规则以 [通信协议](THREE_PARTY_COMMUNICATION_PROTOCOL.md) 为准。
