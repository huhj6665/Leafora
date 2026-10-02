# -*- coding: utf-8 -*-
"""线程安全的 Latest Value Cache。"""

import copy
import threading

from .protocol import utc_now

_AUTO_TIME = object()


class LatestValueCache(object):
    def __init__(self):
        self._values = {}
        self._lock = threading.RLock()

    def update(self, name, value, sampled_at=_AUTO_TIME, valid=True, error=None):
        entry = {
            "value": copy.deepcopy(value),
            "sampled_at": utc_now() if sampled_at is _AUTO_TIME else sampled_at,
            "valid": bool(valid),
            "error": str(error) if error else None,
        }
        with self._lock:
            self._values[name] = entry
        return entry

    def get(self, name):
        with self._lock:
            value = self._values.get(name)
            return copy.deepcopy(value) if value is not None else None

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._values)
