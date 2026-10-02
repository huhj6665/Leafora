# -*- coding: utf-8 -*-
"""
传感器统一管理模块
==================

SensorManager 聚合管理项目中的所有传感器，
对外提供统一读取接口 read_all()。

单个传感器初始化 / 读取失败不会影响其它传感器，
对应字段返回 None。

后续扩展（预留）：
- GPS   定位
- IMU   姿态
- LCD   显示
- MQTT  数据上传

用法::

    from sensors import SensorManager

    manager = SensorManager()
    data = manager.read_all()
    manager.close()
"""

from . import SensorError
from edge.logging_utils import console_print as print
from .light_sensor import LightSensor
from .air_sensor import AirSensor


class SensorManager:
    """统一管理多个传感器。"""

    def __init__(self, bus_number=1):
        """
        初始化所有传感器。

        单个传感器初始化失败时打印错误并跳过，
        不影响其它传感器的正常工作。

        :param bus_number: I2C 总线号
        """
        self.bus_number = bus_number
        self.light = None
        self.air = None

        # 环境光传感器
        try:
            self.light = LightSensor(bus_number=bus_number)
            print("[SensorManager] 环境光传感器 SEN0228 初始化成功")
        except (SensorError, OSError) as e:
            self.light = None
            print("[SensorManager] 环境光传感器初始化失败: {}".format(e))

        # CO2/温湿度传感器
        try:
            self.air = AirSensor(bus_number=bus_number)
            print("[SensorManager] 空气质量传感器 SCD41 初始化成功")
        except (SensorError, OSError) as e:
            self.air = None
            print("[SensorManager] 空气质量传感器初始化失败: {}".format(e))

    def read_all(self):
        """
        读取全部传感器的数据。

        :return: {"lux", "co2", "temperature", "humidity"}
                 某个传感器不可用或读取失败时，对应字段为 None
        """
        data = {
            "lux": None,
            "co2": None,
            "temperature": None,
            "humidity": None,
        }

        # 环境光
        if self.light is not None:
            try:
                data["lux"] = self.light.read_lux()
            except (SensorError, OSError) as e:
                print("[SensorManager] 读取光照失败: {}".format(e))

        # 空气质量
        if self.air is not None:
            try:
                env = self.air.read_environment()
                data["co2"] = env["co2"]
                data["temperature"] = env["temperature"]
                data["humidity"] = env["humidity"]
            except (SensorError, OSError) as e:
                print("[SensorManager] 读取空气质量失败: {}".format(e))

        return data

    def close(self):
        """释放所有传感器资源。"""
        if self.light is not None:
            self.light.close()
        if self.air is not None:
            self.air.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
