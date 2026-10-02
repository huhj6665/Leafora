# -*- coding: utf-8 -*-
"""
GPS NMEA 读取模块
================

只负责：
- 打开 GPS_UART_PATH
- 读取 NMEA 数据
- 解析 GGA / RMC

禁止发送 RTCM（RTCM 由 NTRIPClient 通过独立串口发送）。

用法::

    from gps import GPSReader

    reader = GPSReader()
    reader.start()
    pos = reader.get_position()
    reader.close()
"""

import threading
import time
from datetime import datetime, timezone

import serial
import pynmea2
from edge.logging_utils import console_print as print

from .gps_config import (
    GPS_UART_PATH,
    GPS_BAUDRATE,
    GPS_DEBUG,
    detect_gps_usb_port,
)


class GPSReader:
    """NMEA 读取与解析类（独立线程，只读 GPS 串口）。"""

    # GGA 语句 fix quality -> 描述（u-blox F9）
    FIX_MAP = {
        0: "No Fix",
        1: "GPS Fix",
        2: "DGPS",
        4: "RTK Fixed",
        5: "RTK Float",
    }

    # 数据过期判定：超过该时长未收到新数据视为无数据
    DATA_TIMEOUT_S = 5.0

    def __init__(self, port=GPS_UART_PATH, baudrate=GPS_BAUDRATE):
        """
        :param port:     GPS NMEA 读取串口路径
        :param baudrate: 波特率
        :raises serial.SerialException: 串口不存在或无法打开
        """
        if not port:
            port = detect_gps_usb_port()
        if not port:
            raise serial.SerialException("No GPS USB device found")

        self.port = port
        self.baudrate = baudrate
        self.ser = None

        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self._serial_write_lock = threading.Lock()
        self._latest = {}
        self._latest_gga = None
        self._last_data_time = None
        self._latest_sampled_at = None
        self._nmea_count = 0

        # 打开串口
        self.ser = serial.Serial(port, baudrate, timeout=1.0)
        print("[GPS] Serial connected:")
        print(port)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self):
        """启动后台读取线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop, name="GPSReader", daemon=True
        )
        self._thread.start()

    def stop(self):
        """停止读取线程。"""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def close(self):
        """停止线程并释放串口。"""
        self.stop()
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    # ------------------------------------------------------------------
    # 读取与解析
    # ------------------------------------------------------------------
    def _read_loop(self):
        while self._running:
            try:
                line = self.ser.readline()
            except serial.SerialException as e:
                print("[GPS] UART error: {}".format(e))
                break
            if not line:
                continue
            self._parse_line(line)

    def _parse_line(self, raw_line):
        try:
            self._parse_line_inner(raw_line)
        except Exception:
            # 忽略单条解析异常的句子，保证读取线程不中断
            pass

    def _parse_line_inner(self, raw_line):
        try:
            line = raw_line.decode("ascii", errors="ignore").strip()
        except Exception:
            return

        if not line.startswith("$"):
            return

        # USB 通信测试阶段直接显示目标 NMEA 语句，便于确认真实串口数据。
        if GPS_DEBUG and (line.startswith("$GNGGA") or
                          line.startswith("$GNRMC")):
            print(line)

        try:
            msg = pynmea2.parse(line)
        except pynmea2.ParseError:
            return

        # 成功解析一条 NMEA
        self._nmea_count += 1
        if self._nmea_count == 1:
            print("[GPS] NMEA received")

        if isinstance(msg, pynmea2.GGA):
            with self._lock:
                self._latest_gga = line
            self._on_gga(msg)
        elif isinstance(msg, pynmea2.RMC):
            self._on_rmc(msg)

    def _on_gga(self, msg):
        """处理 GGA 语句（含高度、卫星数、fix 质量）。"""
        try:
            satellites = int(msg.num_sats) if msg.num_sats else None
        except (TypeError, ValueError):
            satellites = None
        try:
            fix_quality = int(msg.gps_qual) if msg.gps_qual else -1
        except (TypeError, ValueError):
            fix_quality = -1

        with self._lock:
            self._latest.update({
                "latitude": msg.latitude,
                "longitude": msg.longitude,
                "altitude": msg.altitude,
                "satellites": satellites,
                "fix": self.FIX_MAP.get(fix_quality, "Unknown"),
            })
            self._last_data_time = time.time()
            self._latest_sampled_at = datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )

    def _on_rmc(self, msg):
        """处理 RMC 语句（经纬度、速度、航向与有效状态）。"""
        try:
            # NMEA RMC 地速单位为节，云端 JSON 统一换算为 m/s。
            speed = (float(msg.spd_over_grnd) * 0.514444
                     if msg.spd_over_grnd else None)
        except (TypeError, ValueError):
            speed = None
        try:
            heading = float(msg.true_course) if msg.true_course else None
        except (TypeError, ValueError):
            heading = None

        with self._lock:
            self._latest.update({
                "latitude": msg.latitude,
                "longitude": msg.longitude,
                "speed": round(speed, 3) if speed is not None else None,
                "heading": round(heading, 2) if heading is not None else None,
                "status": msg.status,
            })
            if msg.status != "A":
                self._latest["fix"] = "No Fix"
            self._last_data_time = time.time()
            self._latest_sampled_at = datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    @property
    def nmea_count(self):
        """累计收到的 NMEA 语句数量。"""
        return self._nmea_count

    def get_latest_gga(self):
        """返回最近收到的真实 GGA 语句，供 NTRIP caster 定位使用。"""
        with self._lock:
            return self._latest_gga

    def write_rtcm(self, data):
        """通过已打开的 ZED-F9P USB 串口回写 RTCM 数据。"""
        if self.ser is None:
            raise serial.SerialException("GPS serial port is closed")
        with self._serial_write_lock:
            return self.ser.write(data)

    def get_position(self):
        """
        获取最近一次定位数据。

        :return: {"latitude","longitude","altitude","fix","satellites",
                  "speed","heading"}
                 无数据或数据过期时返回 None
        """
        with self._lock:
            if not self._latest:
                return None
            if (self._last_data_time is not None and
                    time.time() - self._last_data_time > self.DATA_TIMEOUT_S):
                return None
            return {
                "latitude": self._latest.get("latitude"),
                "longitude": self._latest.get("longitude"),
                "altitude": self._latest.get("altitude"),
                "fix": self._latest.get("fix"),
                "satellites": self._latest.get("satellites"),
                "speed": self._latest.get("speed"),
                "heading": self._latest.get("heading"),
                "sampled_at": self._latest_sampled_at,
            }
