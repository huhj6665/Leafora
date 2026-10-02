# -*- coding: utf-8 -*-
"""
NTRIP 客户端模块
================

只负责：
- 连接 CORS NTRIP 服务器
- 接收 RTCM3 差分数据
- 写入 RTCM_UART_PATH

不与 GPSReader 共享串口。

原生 USB 模式可通过 GPSReader 提供的写入接口回传 RTCM，避免重复
打开同一个串口。既没有写入接口也没有 RTCM_UART_PATH 时不启动线程。

用法::

    from gps import NTRIPClient

    client = NTRIPClient()
    client.start()
    client.stop()
"""

import base64
import socket
import threading
import time

import serial
from edge.logging_utils import console_print as print

from .gps_config import (
    NTRIP_SERVER,
    NTRIP_PORT,
    NTRIP_USERNAME,
    NTRIP_PASSWORD,
    NTRIP_MOUNTPOINT,
    RTCM_UART_PATH,
    RTCM_BAUDRATE,
)


class NTRIPClient:
    """NTRIP 差分数据客户端（独立线程，断线自动重连）。"""

    RECONNECT_DELAY_S = 5.0    # 断线重连间隔（秒）
    RECV_BUFFER = 4096         # 接收缓冲区大小
    STATS_INTERVAL_S = 10.0    # 字节数打印间隔（秒）
    GGA_INTERVAL_S = 10.0      # 向 NTRIP caster 发送 GGA 的间隔（秒）

    def __init__(self, server=NTRIP_SERVER, port=NTRIP_PORT,
                 username=NTRIP_USERNAME, password=NTRIP_PASSWORD,
                 mountpoint=NTRIP_MOUNTPOINT,
                 uart_path=RTCM_UART_PATH, baudrate=RTCM_BAUDRATE,
                 rtcm_writer=None, gga_provider=None):
        """
        :param uart_path: 独立 RTCM 发送串口路径（原生USB模式可为None）
        :param baudrate:  串口波特率
        :param rtcm_writer: 复用 GPSReader 串口的 RTCM 写入函数
        :param gga_provider: 返回最新真实 GGA 语句的函数
        :raises serial.SerialException: 串口不存在或无法打开
        """
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.mountpoint = mountpoint
        self.ser = None
        self._rtcm_writer = rtcm_writer
        self._gga_provider = gga_provider

        self._thread = None
        self._running = False
        self._bytes_received = 0
        self._connected = False
        self._enabled = bool(uart_path or rtcm_writer)

        # 打开 RTCM 发送串口（独立于 GPS 串口）
        # 未配置第二路串口时禁用串口写入，仅统计接收字节。
        if rtcm_writer is not None:
            print("[NTRIP] RTCM output: GPS USB")
        elif uart_path:
            self.ser = serial.Serial(uart_path, baudrate, timeout=1.0)
        else:
            print("[NTRIP] RTCM disabled in GPS USB test mode")

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self):
        """启动后台线程。"""
        if not self._enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="NTRIPClient", daemon=True
        )
        self._thread.start()

    def stop(self):
        """停止后台线程。"""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
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

    @property
    def is_connected(self):
        """是否已连接 NTRIP 服务器。"""
        return self._connected

    @property
    def bytes_received(self):
        """累计接收的 RTCM 字节数。"""
        return self._bytes_received

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def _build_request(self):
        """构造 NTRIP HTTP 请求（含 Basic 认证）。"""
        auth = base64.b64encode(
            "{}:{}".format(self.username, self.password).encode("utf-8")
        ).decode("ascii")
        return (
            "GET /{} HTTP/1.1\r\n"
            "Host: {}\r\n"
            "User-Agent: NTRIP TLD-GPS/1.0\r\n"
            "Accept: */*\r\n"
            "Authorization: Basic {}\r\n"
            "Ntrip-Version: Ntrip/2.0\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(self.mountpoint, self.server, auth).encode("ascii")

    def _connect(self):
        """TCP 连接并完成 NTRIP 握手，返回 socket。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((self.server, self.port))
        sock.sendall(self._build_request())

        header = self._read_header(sock)
        # 兼容 "HTTP/1.1 200 OK" 与 "ICY 200 OK"
        if b"200 OK" not in header:
            raise RuntimeError("NTRIP 握手被拒绝，请核对认证和挂载点")
        return sock

    def test_connection(self):
        """只验证 TCP、认证和 Mountpoint 握手，不启动线程或记录凭据。"""
        sock = None
        try:
            sock = self._connect()
            return True
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    def _read_header(self, sock):
        """读取 HTTP 响应头（直到空行）。"""
        header = b""
        while b"\r\n\r\n" not in header and b"\n\n" not in header:
            chunk = sock.recv(1)
            if not chunk:
                break
            header += chunk
            if len(header) > 8192:
                break
        return header

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def _run(self):
        """连接 - 接收 - 转发 - 断线重连。"""
        while self._running:
            sock = None
            try:
                print("[NTRIP] Connecting...")
                sock = self._connect()
                self._connected = True
                print("[NTRIP] Connected")
                self._receive(sock)
            except Exception as e:
                print("[NTRIP] Connection failed: {}".format(type(e).__name__))
            finally:
                self._connected = False
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

            if self._running:
                time.sleep(self.RECONNECT_DELAY_S)

    def _receive(self, sock):
        """接收 RTCM3 数据、回写GPS，并定期发送最新GGA。"""
        sock.settimeout(1.0)
        last_print = time.time()
        last_gga_send = 0.0

        while self._running:
            try:
                data = sock.recv(self.RECV_BUFFER)
            except socket.timeout:
                last_gga_send = self._send_gga(
                    sock, last_gga_send, time.time()
                )
                continue
            except OSError as e:
                raise RuntimeError("接收错误: {}".format(e))

            if not data:
                raise RuntimeError("连接被服务器关闭")

            self._bytes_received += len(data)

            if self._rtcm_writer is not None:
                try:
                    self._rtcm_writer(data)
                except (serial.SerialException, OSError) as e:
                    raise RuntimeError("GPS USB 写入失败: {}".format(e))
            elif self.ser is not None:
                try:
                    self.ser.write(data)
                except serial.SerialException as e:
                    raise RuntimeError("UART 写入失败: {}".format(e))

            now = time.time()
            last_gga_send = self._send_gga(sock, last_gga_send, now)
            if now - last_print >= self.STATS_INTERVAL_S:
                print("[NTRIP] RTCM received {} bytes".format(self._bytes_received))
                last_print = now

    def _send_gga(self, sock, last_send, now):
        """有真实GGA时按固定间隔发送给 NTRIP caster。"""
        if self._gga_provider is None:
            return last_send
        if now - last_send < self.GGA_INTERVAL_S:
            return last_send

        gga = self._gga_provider()
        if not gga:
            return last_send
        if isinstance(gga, str):
            gga = gga.encode("ascii", errors="ignore")
        sock.sendall(gga.rstrip(b"\r\n") + b"\r\n")
        return now
