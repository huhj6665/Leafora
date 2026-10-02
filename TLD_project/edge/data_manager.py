# -*- coding: utf-8 -*-
"""按协议 V1.3 聚合 Latest Value Cache，不构造飞行状态。"""

import math

from .protocol import SCHEMA_VERSION, new_id, utc_now


FIX_QUALITY = {
    "No Fix": 0,
    "GPS Fix": 1,
    "DGPS": 2,
    "RTK Fixed": 4,
    "RTK Float": 5,
}
RTK_STATUS = {
    "No Fix": "NO_FIX",
    "GPS Fix": "GPS_FIX",
    "DGPS": "DGPS",
    "RTK Fixed": "RTK_FIXED",
    "RTK Float": "RTK_FLOAT",
}


def finite_number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def valid_position(location):
    lat = finite_number(location.get("latitude"))
    lon = finite_number(location.get("longitude"))
    return (location.get("fix") in ("GPS Fix", "DGPS", "RTK Fixed", "RTK Float") and
            lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180)


class DataManager(object):
    def __init__(self, device_id, cache):
        self.device_id = device_id
        self.cache = cache

    @staticmethod
    def _value(entry, default):
        if entry is None or not entry.get("valid"):
            return default
        value = entry.get("value")
        return value if value is not None else default

    def build(self, inspection_id, sequence, data_id=None, timestamp=None, task=None):
        snapshot = self.cache.snapshot()
        location_entry = snapshot.get("location")
        environment_entry = snapshot.get("environment")
        detection_entry = snapshot.get("detection")
        status_entry = snapshot.get("device_status")
        location = self._value(location_entry, {})
        # 环境块允许单传感器失效：保留仍可用的字段，同时把 valid 设为 false。
        environment = dict((key, finite_number(value)) for key, value in
                           (((environment_entry or {}).get("value") or {}).items()))
        detections = self._value(detection_entry, [])
        device_status = self._value(status_entry, {})
        fix = location.get("fix")
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        position_valid = bool(
            location_entry and location_entry.get("valid") and valid_position(location)
        )
        if not position_valid:
            latitude = None
            longitude = None
            location = {}
        else:
            location = dict((key, value if key == "fix" else finite_number(value)) for key, value in location.items())
        device_status = dict((key, value if key == "network_status" else finite_number(value))
                             for key, value in device_status.items())
        results = []
        for item in detections or []:
            if hasattr(item, "class_name"):
                results.append({
                    "class": item.class_name,
                    "confidence": round(float(item.confidence), 4),
                    "bbox": [int(round(value)) for value in item.bbox],
                })
            else:
                results.append({
                    "class": item.get("class", item.get("class_name", "unknown")),
                    "confidence": item.get("confidence"),
                    "bbox": item.get("bbox"),
                })
        env_valid = bool(
            environment_entry and environment_entry.get("valid")
            and environment_entry.get("sampled_at")
            and all(environment.get(key) is not None
                    for key in ("temperature", "humidity", "co2", "lux"))
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "device_id": self.device_id,
            "inspection_id": inspection_id,
            "data_id": data_id or new_id("DATA"),
            "sequence": int(sequence),
            "run_mode": "REAL_DEVICE",
            "data_provenance": "DEVICE",
            "timestamp": timestamp or utc_now(),
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "altitude_msl_m": location.get("altitude"),
                "height_ellipsoid_m": location.get("height_ellipsoid_m"),
                "fix_quality": FIX_QUALITY.get(fix, 0),
                "rtk_status": RTK_STATUS.get(fix, "NO_FIX"),
                "satellites_used": location.get("satellites"),
                "horizontal_accuracy_m": location.get("horizontal_accuracy_m"),
                "vertical_accuracy_m": location.get("vertical_accuracy_m"),
                "ground_speed_mps": location.get("speed"),
                "course_over_ground_deg": location.get("heading"),
                "correction_age_s": location.get("correction_age_s"),
                "position_valid": position_valid,
                "sampled_at": location_entry.get("sampled_at") if location_entry else None,
            },
            "environment": {
                "temperature": environment.get("temperature"),
                "humidity": environment.get("humidity"),
                "co2": environment.get("co2"),
                "light": environment.get("lux", environment.get("light")),
                "sampled_at": environment_entry.get("sampled_at") if environment_entry else None,
                "valid": env_valid,
            },
            "detection": {
                "has_target": bool(results),
                "sampled_at": detection_entry.get("sampled_at") if detection_entry else None,
                "results": results,
            },
            "device_status": {
                "cpu_usage": device_status.get("cpu_usage"),
                "memory_usage": device_status.get("memory_usage"),
                "temperature": device_status.get("cpu_temperature"),
                "storage_usage": device_status.get("storage_usage"),
                "network_status": device_status.get("network_status"),
            },
        }
        if task:
            payload["field_id"] = task.get("field_id")
            payload["field_version"] = task.get("field_version")
        return payload
