# -*- coding: utf-8 -*-
"""
GPS 模块包
==========

ZED-F9P GPS (RTK) 双 UART 接入：

- GPSReader    通过 ZED-F9P 原生 USB 读取并解析 NMEA 定位数据
- NTRIPClient  连接 CORS 服务器，接收并转发 RTCM 差分数据（当前禁用）
- GPSManager   统一管理
- detect_gps_usb_port  自动选择 /dev/ttyACM* 或 /dev/ttyUSB*

后续扩展（预留）：
- MQTT 上传
- HTTP 图片上传
- GPS + YOLO 结果绑定
"""

from .gps_reader import GPSReader
from .ntrip_client import NTRIPClient
from .gps_manager import GPSManager
from .gps_config import (
    check_prerequisites,
    detect_gps_usb_port,
    detect_serial_ports,
)

__all__ = [
    "GPSReader",
    "NTRIPClient",
    "GPSManager",
    "check_prerequisites",
    "detect_gps_usb_port",
    "detect_serial_ports",
]
