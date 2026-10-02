# -*- coding: utf-8 -*-
"""
传感器包
========

统一管理 TLD 项目中的各类外部传感器：

- LightSensor    环境光传感器 (DFRobot SEN0228 / VEML7700, I2C 0x10)
- AirSensor      CO2/温湿度传感器 (Sensirion SCD41, I2C 0x62)
- SensorManager  统一入口，聚合读取

后续扩展方向（预留）：

- GPS   定位
- IMU   姿态
- LCD   显示
- MQTT  数据上传
"""


class SensorError(RuntimeError):
    """传感器通用异常。

    用于区分 I2C 设备不存在、总线不可用、读取失败等底层错误，
    便于上层（SensorManager / main）统一捕获与处理。
    """


from .light_sensor import LightSensor
from .air_sensor import AirSensor
from .sensor_manager import SensorManager

__all__ = [
    "LightSensor",
    "AirSensor",
    "SensorManager",
    "SensorError",
]
