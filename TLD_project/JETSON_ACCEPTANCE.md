# 真实 Jetson 验收（V0.3）

本轮只有本机无硬件证据；下列项目全部待实测，不预先标记通过。
实机验收记录：时间、通过/失败、现象、脱敏日志和业务ID；不记录凭据/配对Token。
先做不飞行的桌面采集，不接电机、姿态、自动起降或航线。

## A. 复制、环境与设备回归

按 README 增量复制源码，保留设备 runtime/、绑定、SQLite、缓存、NTRIP和模型。
退出旧程序不自动结束云端任务，恢复采样应使用 --hardware。

    cd ~/TLD_project
    python3 --version
    python3 -c "import cv2; print(cv2.__version__)"
    python3 -c "import tensorrt as trt; print(trt.__version__)"
    python3 -c "import pycuda.driver; print('pycuda import OK')"
    ls -l /dev/video0 /dev/ttyACM0 /dev/i2c-1
    groups
    python3 -m unittest discover -s test -p 'test_*.py' -v
    python3 tools/check_py36_syntax.py

期望 Python3.6.9/OpenCV3.2.0/TRT8.2.19、现有PyCUDA可导入，用户有video/dialout/i2c权限。
本机65项通过、45文件语法通过；Jetson上的实际执行结果另记，不升级任何系统计算/视觉库。

## B. 先网络向导，再低负载配对

1. 电脑先运行Web LAN API、Broker、Consumer和数据库，查电脑IPv4、实际MQTT端口与防火墙。
   当前Web反馈1883仅loopback、18883未运行，必须先由总监/Web完成部署；不在Jetson绕过认证。
2. python3 main.py 不依赖DISPLAY。第一步询问电脑IP，首次留空拒绝，已保存可回车。
3. HTTP通常8000，MQTT填实际1883或18883；密码不回显、留空保留。永久密钥/NTRIP/硬件配置不被清空。
4. HTTP health、MQTT CONNACK分别成功后才进菜单；不得出现Camera/YOLO/GPS/I2C初始化。
5. 安全测试错误端口、关闭服务、错误临时认证、不可达地址，再改正重试；超时不能单独证明端口错误。
6. localhost、127/8、非法IP/端口拒绝；stat -c '%a %n' runtime/device.env 应为600，不展示文件内容。
7. 菜单3设置云端现有TLD_SIM_002永久密钥；菜单2动态二维码，用手机号登录小程序扫码确认。
8. 显示已绑定/用户昵称；QR不含永久密钥，终端不输出Token文本；已有绑定不重新配对。
9. 通信在线但未加载硬件应 STARTUP、Camera/Inference NOT_STARTED，云端不得误报READY。
10. 正常退出不出现CUDA错误；--ui只提示暂停，不加载硬件。

## C. 硬件和CUDA（实机必要项）

退出通信模式后：

    python3 main.py --hardware

1. 再确认电脑IP/端口并通过诊断，随后才启动Camera、YOLO、GPS、传感器。
2. 菜单10前检查：Camera视频、TRT8.2旧binding推理、普通GPS Fix/合法坐标、绑定/MQTT/存储通过。
3. NTRIP未配置提示“未启用网络 RTK，使用普通 GPS”；不新增、清除或修改已有NTRIP凭据。
4. SCD41温湿度/CO2、VEML7700 lux真实读取；环境慢采样时间保持，不把每次聚合当新传感器采样。
5. 没有GPS Fix不得开始；小程序先阻挡非READY，若授权测试命令送达，设备应REJECTED/GPS_NO_FIX。
6. 启动→退出至少10轮，覆盖任务前/运行中退出并恢复/END同步时退出；检查context stack not empty/core dump是否消失。
7. 退出等待所属线程完成推理/释放和在途上传，记录耗时；相机read卡死或线程不能退出时保留日志报告，不能宣称稳定。

## D. 小程序START与实际JSON

1. 同一配对用户登录，选择烟田和TLD_SIM_002，run_mode=REAL_DEVICE，不选TLD_JETSON_001。
2. 硬件就绪、心跳新鲜后由小程序开始；Web仅管理/监控。
3. Jetson使用云端inspection_id/command_id/field_id/version/snapshot，持久化后ACCEPTED/RUNNING，不创建另一个本地任务。
4. 约0.5秒一条DATA_ENQUEUED与完整单行JSON，随后可能BROKER_PUBACK。对照Web原始JSON的ID/序号/任务字段与真实读数。
5. PUBACK不是入库证明；查看Consumer、Web实时页和业务入库。无飞控时无flight_status，不使用模拟烟田坐标生成真实轨迹。
6. 授权重复同一START，ID/序号不重置；过期新命令、模拟run_mode、快照不符、忙状态拒绝。测试不打印认证Header。

## E. 图片、模块异常、离线与重启

1. 无目标普通帧不落盘；有目标保存匹配原始帧和真实相机时间。
2. MQTT数据Broker确认后才HTTP图片上传；超时/404/业务失败保留原image_id/data_id及文件。
3. 仅code=0且同image_id（含already_uploaded）后先SQLite完成再删除文件；不确定响应不能提前删除。
4. 任务中短暂断网：RUNNING_OFFLINE仍采样，SQLite积压增长；恢复自动補传，同ID无重复业务。
5. 保留runtime后重启 --hardware，确认原地址；云端不可达可选O恢复已有任务。inspection_id不变、sequence继续增长，重传ID不变。
6. 活动/补传期间改地址拒绝，不清活动任务、绑定或缓存；默认通信模式保留任务但不恢复采样。
7. 安全模拟GPS/单传感器/Camera异常：null/有效性false，其它模块继续；相机失效不反复推理旧帧产生新图片。
8. 异常终止测试仅在安全桌面环境执行；被系统强杀的退出不能替代正常CUDA stop清理验收。

## F. END两阶段和云端最终核验

1. 小程序结束→云端END；手机离线时尚未送达的结束不能显示成功。
2. Jetson与最后正在生成的数据/图片事务互斥；最后一条持久化后停止新采样、冻结摘要、ACCEPTED/SYNCING。
3. summary=sampling_stopped:true,last_data_id,last_sequence,sample_count,pending_sync_count。
   零采样last两项null/count0；END后不新增data_id/sequence。
4. 有待传数据/图片或在途对象时保持SYNCING、不假归零；全部确认后同END command_id COMPLETED/COMPLETED、pending0。
5. 两阶段摘要除pending外一致；重启/重复END/重连仍重发原ACCEPTED与COMPLETED，不重复执行、不因原命令过期拒绝重发。
6. Jetson最终Broker PUBACK不代表云端完成；云端核验两阶段、最后ID/sequence、唯一采样总数后，小程序/Web才COMPLETED。
7. Web需验收最终ACK先到、数据晚到、采样缺口、两阶段乱序/重复、旧心跳零值、跨任务错配及零采样；Jetson不能绕过云端核验。

## 实机记录

| 项目 | 状态 | 时间/现象（脱敏） |
|---|---|---|
| Python3.6设备回归 | 待测 | |
| 先IP向导/HTTP/MQTT/配对 | 待测 | |
| Camera/YOLO/GPS/SCD41/lux | 待测 | |
| 正常CUDA清理10轮 | 待测 | |
| 小程序START/JSON/图片HTTP | 待测 | |
| 断网/重启/地址保护 | 待测 | |
| END最后采样/两阶段/云端核验 | 待测 | |
