# -*- coding: utf-8 -*-
"""设备生命周期状态机。"""

import threading


class DeviceState(object):
    UNBOUND = "UNBOUND"
    PAIRING = "PAIRING"
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    RUNNING_OFFLINE = "RUNNING_OFFLINE"
    ENDING = "ENDING"
    SYNCING = "SYNCING"
    ERROR = "ERROR"

    ALL = set([
        UNBOUND, PAIRING, IDLE, STARTING, RUNNING, RUNNING_OFFLINE,
        ENDING, SYNCING, ERROR,
    ])


TRANSITIONS = {
    DeviceState.UNBOUND: set([DeviceState.PAIRING, DeviceState.IDLE, DeviceState.ERROR]),
    DeviceState.PAIRING: set([DeviceState.UNBOUND, DeviceState.IDLE, DeviceState.ERROR]),
    DeviceState.IDLE: set([DeviceState.UNBOUND, DeviceState.PAIRING, DeviceState.STARTING, DeviceState.SYNCING, DeviceState.ERROR]),
    DeviceState.STARTING: set([DeviceState.IDLE, DeviceState.RUNNING, DeviceState.ERROR]),
    DeviceState.RUNNING: set([DeviceState.RUNNING_OFFLINE, DeviceState.ENDING, DeviceState.ERROR]),
    DeviceState.RUNNING_OFFLINE: set([DeviceState.RUNNING, DeviceState.ENDING, DeviceState.ERROR]),
    DeviceState.ENDING: set([DeviceState.SYNCING, DeviceState.ERROR]),
    DeviceState.SYNCING: set([DeviceState.IDLE, DeviceState.ERROR]),
    DeviceState.ERROR: set([DeviceState.UNBOUND, DeviceState.IDLE, DeviceState.SYNCING]),
}


class InvalidTransition(RuntimeError):
    pass


class StateMachine(object):
    def __init__(self, initial):
        if initial not in DeviceState.ALL:
            raise ValueError("unknown state: {}".format(initial))
        self._state = initial
        self._reason = ""
        self._lock = threading.RLock()
        self._callbacks = []

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def reason(self):
        with self._lock:
            return self._reason

    def add_callback(self, callback):
        with self._lock:
            self._callbacks.append(callback)

    def transition(self, target, reason="", force=False):
        with self._lock:
            current = self._state
            if target == current:
                self._reason = reason
                return current
            if target not in DeviceState.ALL:
                raise ValueError("unknown state: {}".format(target))
            if not force and target not in TRANSITIONS.get(current, set()):
                raise InvalidTransition("{} -> {} is not allowed".format(current, target))
            self._state = target
            self._reason = reason
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback(current, target, reason)
        return target
