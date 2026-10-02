# -*- coding: utf-8 -*-
"""V2.0 云端业务命令的 Python 3.6 校验，不执行飞行控制。"""

import re
import math
from datetime import datetime, timedelta, timezone


def parse_command_time(value):
    text = str(value or "")
    match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$", text)
    if not match:
        raise ValueError("INVALID_TIMESTAMP")
    stamp = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
    fraction = match.group(2)
    if fraction:
        stamp = stamp.replace(microsecond=int(fraction[1:].ljust(6, "0")))
    offset = match.group(3)
    if offset != "Z":
        if int(offset[1:3]) > 23 or int(offset[4:6]) > 59:
            raise ValueError("INVALID_TIMESTAMP")
        minutes = int(offset[1:3]) * 60 + int(offset[4:6])
        stamp -= timedelta(minutes=minutes if offset[0] == "+" else -minutes)
    return stamp.replace(tzinfo=timezone.utc).timestamp()


def validate_command(payload, device_id, now):
    if payload.get("device_id") != device_id:
        return "DEVICE_MISMATCH"
    if payload.get("schema_version") != "2.0":
        return "UNSUPPORTED_SCHEMA"
    if payload.get("command") not in ("START_INSPECTION", "END_INSPECTION"):
        return "UNSUPPORTED_COMMAND"
    for key in ("command_id", "inspection_id", "field_id"):
        if not isinstance(payload.get(key), str) or not re.match(r"^[A-Za-z0-9_.-]{1,64}$", payload[key]):
            return "INVALID_FIELDS"
    version = payload.get("field_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return "INVALID_FIELDS"
    try:
        expires = parse_command_time(payload.get("expires_at"))
        created = parse_command_time(payload.get("timestamp"))
    except (ValueError, TypeError, OverflowError):
        return "INVALID_TIMESTAMP"
    if expires <= now:
        return "COMMAND_EXPIRED"
    if created > now + 30 or expires <= created:
        return "INVALID_TIMESTAMP"
    if payload["command"] == "START_INSPECTION":
        if payload.get("run_mode") != "REAL_DEVICE":
            return "INVALID_RUN_MODE"
        snapshot = payload.get("field_snapshot")
        if not isinstance(snapshot, dict):
            return "INVALID_FIELD_SNAPSHOT"
        if (snapshot.get("field_id") != payload["field_id"] or
                type(snapshot.get("version")) is not int or snapshot.get("version") != version or
                snapshot.get("coordinate_system") != "WGS84"):
            return "FIELD_SNAPSHOT_MISMATCH"
        boundary = snapshot.get("geo_boundary")
        if not isinstance(boundary, dict) or boundary.get("type") != "Polygon" or not boundary.get("coordinates"):
            return "INVALID_FIELD_SNAPSHOT"
        for ring in boundary["coordinates"]:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                return "INVALID_FIELD_SNAPSHOT"
            for point in ring:
                if not isinstance(point, list) or len(point) < 2:
                    return "INVALID_FIELD_SNAPSHOT"
                lon, lat = point[:2]
                if (any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                        for value in (lon, lat)) or not -180 <= lon <= 180 or not -90 <= lat <= 90):
                    return "INVALID_FIELD_SNAPSHOT"
    return None
