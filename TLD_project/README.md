# TLD 真实 Jetson 边缘端

目标：Python 3.6.9、JetPack 4.6.6、TensorRT 8.2.19、OpenCV 3.2.0。
真实设备固定 TLD_SIM_002，禁止混用虚拟设备 TLD_JETSON_001。
采用根协议 V0.3，接收 V2.0 云端命令，发送 V1.3 REAL_DEVICE/DEVICE 数据。
边缘端负责数据采集与识别，不实现无人机控制；不建议升级目标设备的系统库。

## 启动方式

在 Jetson 现有目录中手动运行：

    cd ~/TLD_project
    python3 main.py

默认是通信配置/配对模式，不加载 Camera、CUDA、GPS、I2C，不需要 DISPLAY。
python3 main.py --cli 是同义兼容写法。
实际桌面采集使用：

    python3 main.py --hardware

两种模式都先经过网络向导；确认通过后才连接业务会话，--hardware 此后才启动硬件。
--ui 仅提示暂停并退出，UI 源码保留；不安装开机服务。

1. 第一项填写“运行云端服务的电脑局域网 IPv4”，不是 Jetson 的 IP、手机网关、localhost 或 127.0.0.1。
2. 已保存地址回车确认；首次空地址必须填写。HTTP 默认8000、MQTT默认1883；实际部署若为18883，必须填写18883。
3. MQTT 凭据来自部署者的本地受限配置；密码不回显，留空保留原值。既有 HTTPS、独立 TLS Broker 地址及 TLS 开关保留。
4. 分别检查 HTTP /api/health 与 MQTT CONNACK。拒绝连接核对端口/服务/防火墙，超时核对网络，auth_failed 为认证失败；失败可重试或退出。
5. 活动任务/补传期间只能确认原地址，不能更换；仅已有任务可在网络失败时选 O 按原配置离线恢复。恢复采样需 --hardware，默认通信模式只通信/补传、不采样。
6. 待命提示“任务由小程序发起，Jetson 等待云端命令”。菜单1状态、2动态配对、3安全设置设备密钥，硬件模式另有10前检查；没有正常业务的本地启停菜单。

health/CONNACK 成功不代表设备密钥、硬件或业务入库成功。缺密钥时先用菜单3输入云端现有 TLD_SIM_002 永久密钥，不生成新设备身份。

## 增量复制（保留设备配置、模型和缓存）

先在 Jetson 手动退出旧程序，保留整个 runtime/、活动任务、绑定、缓存和模型。
以下在 Windows PowerShell 执行；JETSON_IP 是 Jetson 的上传地址，不是向导要填的电脑地址。用户名按实际调整：

    Set-Location .\TLD_project
    $jetsonTarget = 'yzh@JETSON_IP'
    scp main.py device.env.example requirements-jetson.txt README.md JETSON_ACCEPTANCE.md "${jetsonTarget}:~/TLD_project/"
    foreach ($jetsonFolder in @('edge', 'inference', 'gps', 'sensors', 'test', 'tools')) {
        Get-ChildItem -LiteralPath $jetsonFolder -Filter '*.py' -File | ForEach-Object {
            scp $_.FullName "${jetsonTarget}:~/TLD_project/$jetsonFolder/"
        }
    }

适用于已有完整工程且各目录已存在的 Jetson。只复制源码和文档，不传 Windows __pycache__、
runtime/device.env、SQLite、缓存图片或 models/train_best.engine。不要整目录覆盖设备。
若设备没有配置文件才创建空凭据模板：

    cd ~/TLD_project
    mkdir -p runtime
    test -f runtime/device.env || cp device.env.example runtime/device.env
    chmod 600 runtime/device.env

轻依赖见 requirements-jetson.txt；已有依赖不重装，缺少时使用原 Python3.6 环境：

    python3 -m pip install -r requirements-jetson.txt

不升级 pip、系统 CUDA/TensorRT/PyCUDA/NumPy/OpenCV，不用 opencv-python 覆盖 OpenCV3.2.0。
--config /absolute/path/device.env 可指定受限配置；已有 TLD_* 环境覆盖项时先核对地址是否被覆盖。

## 闭环与日志

小程序申请 → 云端创建任务/命令/快照 → START_INSPECTION → Jetson校验并持久化 → ACCEPTED/RUNNING → 采样。
启动需绑定、在线、设备密钥、Camera/YOLO、真实GPS Fix/合法坐标及足够磁盘；RTK、单传感器异常只警告。
未配置NTRIP提示“未启用网络 RTK，使用普通 GPS”，保留已有配置，本轮不提供NTRIP修改菜单。

- 任务序号、唯一采样计数、data_id、图片及任务状态在同一SQLite事务提交；离线继续采样，恢复/重启重试保持原ID。
- 每条实际入队采样默认打印一整行紧凑JSON，与出站业务对象一致，不另读传感器。PRINT_SAMPLE_JSON=false 可关闭。
- DATA_ENQUEUED 是本地入队；BROKER_PUBACK 只表示Broker接收，不是云端入库。
- MQTT_RETRY / MQTT_RETRY_FAILED、IMAGE_RETRY / IMAGE_RETRY_FAILED 保留原ID。
- IMAGE_HTTP_SUCCESS 在HTTP code=0且同image_id后出现；先SQLite完成再删除文件。
- V1.3带field_id/version和REAL_DEVICE/DEVICE，无飞行进度/模拟轨迹/伪造RTK；异常读数为null，保留真实sampled_at和有效标识。
- 只有检测原始帧落盘，图片使用相机取帧时间；相机失败不将旧帧重复识别成新图片。
- CUDA创建、TRT加载、推理与释放均属同一YOLO线程，停止等待该线程清理。

小程序 END → 与最后采样/图片入库互斥 → 持久化停止摘要 → ACCEPTED/SYNCING。
本任务 data/images（包括在途）完成后，发送同一END命令 COMPLETED/COMPLETED、pending=0。
两阶段证据均持久化；重启/重复END/重连及周期重发同时保证原ACCEPTED和最终COMPLETED可送达。
最终Broker PUBACK后本地归档但不删除命令证据；云端核验最后ID/序号和唯一采样数后，才由小程序显示完成。

旧 control START/END 只保留诊断兼容，默认 ALLOW_LEGACY_CONTROL=false，不作为正式业务入口。

## 验证与部署前置

    python3 -m unittest discover -s test -p 'test_*.py' -v
    python3 tools/check_py36_syntax.py
    python3 main.py --help

逐项实机步骤见 JETSON_ACCEPTANCE.md。
Windows无硬件测试不代表真实硬件/Broker/HTTP/手机联调通过。
