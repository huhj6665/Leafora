# -*- coding: utf-8 -*-
"""
GPS 统一管理模块
================

统一管理 GPSReader（NMEA 读取）与 NTRIPClient（RTCM 差分），
按配置启动读取线程与可选的差分线程，互不影响。

启动时自动扫描 /dev/ttyACM* 与 /dev/ttyUSB*。

后续扩展（预留）：
- MQTT 上传
- HTTP 图片上传
- GPS + YOLO 结果绑定

用法::

    from gps import GPSManager

    manager = GPSManager()
    manager.start()
    pos = manager.get_position()
    manager.close()
"""

import serial
from edge.logging_utils import console_print as print

from .gps_config import (
    GPS_UART_PATH,
    RTCM_UART_PATH,
    GPS_BAUDRATE,
    RTCM_BAUDRATE,
    GPS_DEBUG,
    GPS_TEST_MODE,
    NTRIP_ENABLED,
    detect_gps_usb_port,
)
from .gps_reader import GPSReader
from .ntrip_client import NTRIPClient


class GPSManager:
    """统一管理 GPS NMEA 读取与 NTRIP/RTCM 差分回传。"""

    def __init__(self, gps_port=GPS_UART_PATH, rtcm_port=RTCM_UART_PATH,
                 gps_baudrate=GPS_BAUDRATE, rtcm_baudrate=RTCM_BAUDRATE,
                 ntrip_settings=None):
        self.reader = None
        self.ntrip = None
        ntrip_settings = dict(ntrip_settings or {})
        ntrip_enabled = bool(ntrip_settings.get("enabled", NTRIP_ENABLED))

        # 未指定端口时自动检测 ZED-F9P 原生 USB 串口。
        if not gps_port:
            gps_port = detect_gps_usb_port()

        if GPS_DEBUG:
            print("[DEBUG] 当前GPS端口: {}".format(gps_port))
            print("[DEBUG] RTCM UART: {}".format(rtcm_port))
            print("[DEBUG] NTRIP enabled: {}".format(ntrip_enabled))
            print("[DEBUG] GPS_TEST_MODE: {}".format(GPS_TEST_MODE))

        # 1. GPSReader：NMEA 读取（独立串口）
        if gps_port:
            try:
                self.reader = GPSReader(port=gps_port, baudrate=gps_baudrate)
            except (serial.SerialException, FileNotFoundError, OSError) as e:
                self.reader = None
                print("[GPSManager] GPSReader 初始化失败: {}".format(e))

        # 2. 原生 USB 模式复用 GPSReader 串口接收 NMEA、回写 RTCM。
        if ntrip_enabled and self.reader is not None:
            try:
                self.ntrip = NTRIPClient(
                    server=ntrip_settings.get("server", ""),
                    port=ntrip_settings.get("port", 2101),
                    username=ntrip_settings.get("username", ""),
                    password=ntrip_settings.get("password", ""),
                    mountpoint=ntrip_settings.get("mountpoint", ""),
                    uart_path=rtcm_port,
                    baudrate=rtcm_baudrate,
                    rtcm_writer=self.reader.write_rtcm,
                    gga_provider=self.reader.get_latest_gga,
                )
            except (serial.SerialException, FileNotFoundError, OSError) as e:
                self.ntrip = None
                print("[GPSManager] NTRIPClient 初始化失败: {}".format(e))
        elif not ntrip_enabled:
            print("[NTRIP] 未启用网络 RTK，使用普通 GPS")
        else:
            print("[NTRIP] skipped: GPS USB unavailable")

    def start(self):
        """启动 NMEA 读取线程，以及配置启用时的 RTCM 接收线程。"""
        if self.reader is not None:
            self.reader.start()
        if self.ntrip is not None:
            self.ntrip.start()

    def get_position(self):
        """
        获取定位数据。

        :return: {"latitude","longitude","altitude","fix","satellites"}
                 无数据时返回 None
        """
        if self.reader is None:
            return None
        return self.reader.get_position()

    @property
    def nmea_count(self):
        """累计收到的 NMEA 语句数量。"""
        return self.reader.nmea_count if self.reader is not None else 0

    @property
    def rtcm_bytes(self):
        """累计接收的 RTCM 字节数。"""
        return self.ntrip.bytes_received if self.ntrip is not None else 0

    @property
    def ntrip_connected(self):
        """NTRIP 是否已连接。"""
        return self.ntrip.is_connected if self.ntrip is not None else False

    def close(self):
        """停止线程并释放串口。"""
        if self.ntrip is not None:
            self.ntrip.close()
        if self.reader is not None:
            self.reader.close()

    def restart_ntrip(self, settings):
        """仅重启 NTRIP，不关闭或重复打开 GPSReader 串口。"""
        if self.ntrip is not None:
            self.ntrip.close()
            self.ntrip = None
        settings = dict(settings or {})
        if not settings.get("enabled") or self.reader is None:
            return False
        self.ntrip = NTRIPClient(
            server=settings.get("server", ""),
            port=settings.get("port", 2101),
            username=settings.get("username", ""),
            password=settings.get("password", ""),
            mountpoint=settings.get("mountpoint", ""),
            uart_path=None,
            baudrate=RTCM_BAUDRATE,
            rtcm_writer=self.reader.write_rtcm,
            gga_provider=self.reader.get_latest_gga,
        )
        self.ntrip.start()
        return True
