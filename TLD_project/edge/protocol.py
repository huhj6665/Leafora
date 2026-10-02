# -*- coding: utf-8 -*-
"""冻结通信协议的常量与通用 ID/时间工具。"""

import uuid
from datetime import datetime, timezone


SCHEMA_VERSION = "1.3"
PAIRING_QR_VERSION = "2.0"


def utc_now(microseconds=True):
    value = datetime.now(timezone.utc)
    if not microseconds:
        value = value.replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def new_id(prefix):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return "{}_{}_{}".format(prefix, stamp, uuid.uuid4().hex[:8].upper())


class Topics(object):
    def __init__(self, device_id):
        root = "tld/device/{}".format(device_id)
        self.data = root + "/data"
        self.control = root + "/control"
        self.status = root + "/status"
        self.downlink = root + "/downlink"
        self.ack = root + "/ack"

    def all(self):
        return {
            "data": self.data,
            "control": self.control,
            "status": self.status,
            "downlink": self.downlink,
            "ack": self.ack,
        }
