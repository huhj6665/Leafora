# -*- coding: utf-8 -*-
"""
空气质量传感器模块
==================

驱动 Sensirion SCD41（CO2 + 温度 + 湿度），
通过 I2C 启动周期测量并读取结果。

硬件：
- 芯片：SCD41（SCD4x 系列）
- 接口：I2C
- 地址：0x62 (7-bit)
- 测量周期：约 5s

关键命令（16-bit）：
- start_periodic_measurement  0x21B1
- stop_periodic_measurement   0x3F86
- get_data_ready_status       0xE4B8
- read_measurement            0xEC05

用法::

    from sensors import AirSensor

    air = AirSensor()             # 默认 I2C 总线 1，地址 0x62
    env = air.read_environment()  # {"co2":..., "temperature":..., "humidity":...}
    air.close()
"""

import time

import smbus2
from smbus2 import i2c_msg

from . import SensorError


class AirSensor:
    """SCD41 CO2/温湿度传感器封装类。"""

    DEFAULT_ADDRESS = 0x62

    CMD_START_PERIODIC = 0x21B1    # 启动周期测量（间隔 5s）
    CMD_STOP_PERIODIC = 0x3F86     # 停止周期测量
    CMD_GET_DATA_READY = 0xE4B8    # 查询数据就绪状态
    CMD_READ_MEASUREMENT = 0xEC05  # 读取测量结果

    # SCD4x 上电后需约 1.2s 才能接受第一条 I2C 命令
    POWER_ON_DELAY_S = 1.2

    # 等待数据就绪的超时时间（略大于 5s 测量周期）
    DATA_READY_TIMEOUT_S = 7.0

    def __init__(self, bus_number=1, address=DEFAULT_ADDRESS):
        """
        初始化 SCD41 并启动周期测量。

        :param bus_number: I2C 总线号
        :param address:    设备 7-bit I2C 地址
        :raises SensorError: 总线不可用或设备不存在时抛出
        """
        self.address = address
        self.bus_number = bus_number
        self.bus = None
        self._started = False

        # 1. 打开 I2C 总线
        try:
            self.bus = smbus2.SMBus(bus_number)
        except FileNotFoundError:
            raise SensorError(
                "I2C 总线 /dev/i2c-{} 不存在，请检查 I2C 是否启用。".format(
                    bus_number
                )
            )

        # 2. 探测设备（上电后可能未就绪，失败则延时重试一次）
        self._probe()

        # 3. 启动周期测量
        self._start_periodic()

    # ------------------------------------------------------------------
    # 底层通信
    # ------------------------------------------------------------------
    def _send_command(self, command):
        """发送 16-bit 命令（大端）。"""
        write = i2c_msg.write(self.address, [command >> 8, command & 0xFF])
        self.bus.i2c_rdwr(write)

    def _read_words(self, command, word_count, delay_s=0.001):
        """
        发送命令并读取 word_count 个 16-bit 字（每个字后跟 1 字节 CRC8）。

        :param command:    16-bit 命令字
        :param word_count: 要读取的字数量
        :param delay_s:    命令执行延时（读命令约 1ms）
        :return: 校验通过后的字列表
        :raises OSError:     底层 I2C 错误
        :raises SensorError: CRC 校验失败
        """
        # 1. 发送命令
        self._send_command(command)

        # 2. 等待命令执行（SCD4x 读命令约需 1ms）
        time.sleep(delay_s)

        # 3. 纯读取数据（每字 = 2 字节数据 + 1 字节 CRC）
        read = i2c_msg.read(self.address, word_count * 3)
        self.bus.i2c_rdwr(read)

        data = list(read)
        words = []
        for i in range(0, len(data), 3):
            chunk = data[i:i + 3]
            word = (chunk[0] << 8) | chunk[1]
            if self._crc8(chunk[:2]) != chunk[2]:
                raise SensorError("SCD41 CRC8 校验失败")
            words.append(word)
        return words

    @staticmethod
    def _crc8(data):
        """计算 SCD4x CRC8（多项式 0x31，初值 0xFF）。"""
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x31) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    # ------------------------------------------------------------------
    # 初始化 / 生命周期
    # ------------------------------------------------------------------
    def _probe(self):
        """探测设备是否在线（读数据就绪状态）。"""
        for attempt in range(2):
            try:
                self._read_words(self.CMD_GET_DATA_READY, 1)
                return
            except OSError:
                if attempt == 0:
                    time.sleep(self.POWER_ON_DELAY_S)
                else:
                    self.close()
                    raise SensorError(
                        "未检测到 SCD41 (0x{:02X})，请检查：\n"
                        "  1) 设备地址是否正确；\n"
                        "  2) 接线与供电是否正常；\n"
                        "  3) 可用 i2cdetect -y -r {} 扫描确认。".format(
                            self.address, self.bus_number
                        )
                    )

    def _start_periodic(self):
        """启动周期测量。"""
        try:
            self._send_command(self.CMD_START_PERIODIC)
        except OSError:
            self.close()
            raise SensorError("SCD41 启动周期测量失败")
        self._started = True

    def _data_ready(self):
        """
        查询数据是否就绪。

        数据就绪标志为状态字低 11 位（掩码 0x07FF），非零表示就绪。
        """
        words = self._read_words(self.CMD_GET_DATA_READY, 1)
        return (words[0] & 0x07FF) != 0

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def read_environment(self):
        """
        读取 CO2、温度、湿度。

        内部会等待 SCD41 的周期测量结果就绪（最长约 5s）。

        :return: {"co2": int, "temperature": float, "humidity": float}
        :raises SensorError: 数据超时未就绪或读取失败
        """
        try:
            # 1. 等待数据就绪
            deadline = time.time() + self.DATA_READY_TIMEOUT_S
            while not self._data_ready():
                if time.time() >= deadline:
                    raise SensorError("SCD41 数据就绪超时")
                time.sleep(0.1)

            # 2. 读取并解析
            words = self._read_words(self.CMD_READ_MEASUREMENT, 3)
        except OSError as e:
            raise SensorError("读取 SCD41 数据失败: {}".format(e))

        co2 = words[0]
        temperature = -45.0 + 175.0 * words[1] / 65535.0
        humidity = 100.0 * words[2] / 65535.0

        return {
            "co2": int(co2),
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
        }

    def stop(self):
        """停止周期测量（回到空闲态）。"""
        if self._started and self.bus is not None:
            try:
                self._send_command(self.CMD_STOP_PERIODIC)
                time.sleep(0.5)  # stop 命令执行时间约 500ms
            except OSError:
                pass
            self._started = False

    def close(self):
        """停止测量并释放 I2C 总线。"""
        self.stop()
        if self.bus is not None:
            try:
                self.bus.close()
            except OSError:
                pass
            self.bus = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
