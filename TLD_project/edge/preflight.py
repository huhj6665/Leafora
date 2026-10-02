# -*- coding: utf-8 -*-
"""任务启动前硬性检查和警告检查。"""

import os
import shutil
from .data_manager import valid_position


class PreflightResult(object):
    def __init__(self):
        self.checks = []

    def add(self, name, passed, required=True, detail=""):
        self.checks.append({
            "name": name,
            "passed": bool(passed),
            "required": bool(required),
            "detail": detail,
        })

    @property
    def ok(self):
        return all(item["passed"] for item in self.checks if item["required"])

    @property
    def errors(self):
        return [item for item in self.checks if item["required"] and not item["passed"]]

    @property
    def warnings(self):
        return [item for item in self.checks if not item["required"] and not item["passed"]]


def run_preflight(bound, cloud_online, health, state_dir, min_free_disk_mb):
    result = PreflightResult()
    result.add("bound", bound, True, "设备已绑定" if bound else "设备尚未绑定")
    result.add("cloud", cloud_online, True, "云端在线" if cloud_online else "MQTT 尚未连接")
    result.add("camera", bool(health.get("camera")), True, health.get("camera_detail", ""))
    result.add("yolo", bool(health.get("yolo")), True, health.get("yolo_detail", ""))
    location = health.get("location") or {}
    gps_ok = valid_position(location)
    result.add("gps_fix", gps_ok, True, location.get("fix") or "无定位")
    try:
        free_mb = shutil.disk_usage(state_dir).free / (1024.0 * 1024.0)
        disk_ok = free_mb >= float(min_free_disk_mb)
        detail = "可用 {:.1f} MB，最低 {} MB".format(free_mb, min_free_disk_mb)
    except OSError as exc:
        disk_ok = False
        detail = str(exc)
    result.add("disk", disk_ok, True, detail)
    fix = location.get("fix")
    result.add("rtk", fix in ("RTK Float", "RTK Fixed"), False, fix or "NTRIP/RTK 未就绪")
    sensors = health.get("sensors") or {}
    result.add("light_sensor", sensors.get("light") is True, False, "VEML7700")
    result.add("air_sensor", sensors.get("air") is True, False, "SCD41")
    return result
