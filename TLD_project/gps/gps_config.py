# -*- coding: utf-8 -*-
"""
GPS 配置模块
============

集中管理 ZED-F9P GPS 相关的所有参数：
- NTRIP CORS 服务器参数
- USB 串口参数（NMEA 读取 / RTCM 发送）
- 调试与测试开关
- 串口自动检测

所有可调参数集中在此，避免散落各处。
"""

import glob
import os

# ==========================
# NTRIP CORS 服务器参数
# ==========================
# 凭据只能由 edge.config 从 runtime/device.env 注入。这里保留空默认值，
# 确保本模块单独导入时不会携带任何真实账号或服务器配置。
NTRIP_SERVER = ""
NTRIP_PORT = 2101
NTRIP_USERNAME = ""
NTRIP_PASSWORD = ""
NTRIP_MOUNTPOINT = ""
NTRIP_ENABLED = False

# ==========================
# 串口参数（ZED-F9P 原生 USB 测试）
# ==========================

# GPS NMEA 读取串口。None 表示自动检测 /dev/ttyACM*、/dev/ttyUSB*。
GPS_UART_PATH = None

# 原生 USB 模式下由 NTRIPClient 复用 GPSReader 已打开的串口回写 RTCM，
# 因此不需要配置第二个串口。
RTCM_UART_PATH = None

# 两个串口分别独立配置
GPS_BAUDRATE = 38400
RTCM_BAUDRATE = 38400

# ==========================
# 调试 / 测试开关
# ==========================
GPS_DEBUG = False

# GPS 独立测试模式：开启后仅运行 GPS，
# 不启动 camera / YOLO / sensor / MQTT。
GPS_TEST_MODE = False


def _gps_usb_ports():
    """返回按使用优先级排序的 GPS USB 串口。"""
    acm_ports = sorted(glob.glob("/dev/ttyACM*"))
    usb_ports = sorted(glob.glob("/dev/ttyUSB*"))
    ports = acm_ports + usb_ports

    # 明确保证常见的两个设备名优先，其中 ttyACM0 优先级最高。
    priority = ["/dev/ttyACM0", "/dev/ttyUSB0"]
    return [p for p in priority if p in ports] + [
        p for p in ports if p not in priority
    ]


def detect_gps_usb_port():
    """
    自动检测 ZED-F9P USB 串口并返回实际设备路径。

    扫描 /dev/ttyACM* 与 /dev/ttyUSB*，优先使用 /dev/ttyACM0，
    其次使用 /dev/ttyUSB0。没有设备时返回 None 并输出接线提示。
    """
    ports = _gps_usb_ports()
    if ports:
        print("[GPS] USB GPS device detected:")
        print(ports[0])
        return ports[0]

    print("[ERROR]")
    print("No GPS USB device found.")
    print("检查：")
    print("1. Type-C是否为数据线")
    print("2. ZED-F9P是否供电")
    print("3. USB设备是否识别")
    return None


def detect_serial_ports():
    """
    启动时扫描并返回系统中可用的 USB 串口设备。

    扫描 /dev/ttyACM* 与 /dev/ttyUSB*。
    用于确认接线是否正确、设备是否被系统识别。

    输出示例::

        [GPS] detected serial ports:
              /dev/ttyUSB0

    无设备时输出::

        [GPS] detected serial ports:
              No USB GPS UART detected.

    :return: 排序后的串口路径列表，例如 ["/dev/ttyUSB0"]
    """
    ports = _gps_usb_ports()

    print("[GPS] detected serial ports:")
    if ports:
        for p in ports:
            print("      {}".format(p))
    else:
        print("      No GPS USB device found.")

    return ports


def check_prerequisites():
    """
    启动前检查。

    检查 GPS USB 设备是否存在并且具有读写权限。

    :return: 全部通过返回 True，否则返回 False
    """
    path = GPS_UART_PATH or detect_gps_usb_port()
    if path is None:
        return False
    if not os.path.exists(path):
        print("[ERROR]")
        print("GPS USB device unavailable: {}".format(path))
        return False
    if not os.access(path, os.R_OK | os.W_OK):
        print("[ERROR]")
        print("GPS USB device permission denied: {}".format(path))
        print("run: sudo usermod -aG dialout $USER  (re-login after)")
        return False
    return True
