# -*- coding: utf-8 -*-
"""
环境光传感器模块
================

驱动 DFRobot SEN0228（核心芯片 VEML7700），
通过 I2C 读取环境光照度，返回 Lux。

硬件：
- 芯片：VEML7700
- 接口：I2C
- 地址：0x10 (7-bit)
- 量程：0 ~ 120000 Lux

关键寄存器：
- 0x00 ALS_CONF  配置（增益 / 积分时间 / 关断）
- 0x04 ALS       光照数据（16-bit）

用法::

    from sensors import LightSensor

    light = LightSensor()      # 默认 I2C 总线 1，地址 0x10
    lux = light.read_lux()     # 返回 float (Lux)
    light.close()
"""

import smbus2

from . import SensorError


class LightSensor:
    """VEML7700 环境光传感器封装类。"""

    DEFAULT_ADDRESS = 0x10

    REG_ALS_CONF = 0x00   # 配置寄存器
    REG_ALS_DATA = 0x04   # 光照数据寄存器

    # 配置字：增益 x1、积分时间 100ms、正常上电（非关断）
    # 各字段均为默认值，故整字为 0x0000：
    #   bit[12:11] ALS_GAIN = 00b   (x1)
    #   bit[9:6]   ALS_IT   = 0000b (100ms)
    #   bit[0]     ALS_SD   = 0     (power on)
    ALS_CONFIG = 0x0000

    # 分辨率：增益 x1 / 积分时间 100ms 时，1 count = 0.0576 Lux
    # 通用公式：resolution = 0.0036 * (2 / gain) * (800 / integration_ms)
    RESOLUTION = 0.0576

    def __init__(self, bus_number=1, address=DEFAULT_ADDRESS):
        """
        初始化环境光传感器。

        :param bus_number: I2C 总线号，Jetson Nano 40-pin 引脚默认总线 1
        :param address:    设备 7-bit I2C 地址
        :raises SensorError: 总线不可用或设备不存在时抛出
        """
        self.address = address
        self.bus_number = bus_number
        self.bus = None

        # 1. 打开 I2C 总线
        try:
            self.bus = smbus2.SMBus(bus_number)
        except FileNotFoundError:
            raise SensorError(
                "I2C 总线 /dev/i2c-{} 不存在，请检查：\n"
                "  1) 是否已启用 I2C（Jetson-IO / dtb）；\n"
                "  2) 接线是否正确（SEN0228 -> SDA/SCL/3.3V/GND）。".format(
                    bus_number
                )
            )

        # 2. 探测设备并写入默认配置
        self._init_device()

    # ------------------------------------------------------------------
    # 底层读写
    # ------------------------------------------------------------------
    def _write_register(self, register, value):
        """写 16-bit 寄存器（大端，先发高字节）。"""
        self.bus.write_i2c_block_data(
            self.address, register, [value >> 8, value & 0xFF]
        )

    def _read_register(self, register):
        """读 16-bit 寄存器（大端）。"""
        data = self.bus.read_i2c_block_data(self.address, register, 2)
        return (data[0] << 8) | data[1]

    def _init_device(self):
        """探测设备是否在线，并写入默认配置。"""
        try:
            # 读一次配置寄存器以确认设备在线
            self._read_register(self.REG_ALS_CONF)
            # 写入默认配置：增益 x1、积分时间 100ms、上电
            self._write_register(self.REG_ALS_CONF, self.ALS_CONFIG)
        except OSError:
            self.close()
            raise SensorError(
                "未检测到环境光传感器 SEN0228 (0x{:02X})，请检查：\n"
                "  1) 设备地址是否正确；\n"
                "  2) 接线与供电是否正常；\n"
                "  3) 可用 i2cdetect -y -r {} 扫描确认。".format(
                    self.address, self.bus_number
                )
            )

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def read_lux(self):
        """
        读取环境光照度。

        :return: 光照度 (float, 单位 Lux)
        :raises SensorError: 读取失败时抛出
        """
        try:
            raw = self._read_register(self.REG_ALS_DATA)
        except OSError as e:
            raise SensorError("读取环境光数据失败: {}".format(e))
        return raw * self.RESOLUTION

    def close(self):
        """释放 I2C 总线。"""
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
