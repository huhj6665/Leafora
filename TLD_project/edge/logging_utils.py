# -*- coding: utf-8 -*-
"""带敏感信息脱敏的线程安全日志分发。"""

import logging
import builtins
import json
import os
import re
import threading
import sys
from logging.handlers import RotatingFileHandler

OUTPUT_LOCK = threading.RLock()


def console_print(*args, **kwargs):
    with OUTPUT_LOCK:
        builtins.print(*args, **kwargs)


class ConsoleHandler(logging.StreamHandler):
    def emit(self, record):
        with OUTPUT_LOCK:
            logging.StreamHandler.emit(self, record)


def print_sample(payload, config, stream=None):
    """仅输出实际入队采样，一次写入一整行，防止配置/认证字段泄漏。"""
    if not getattr(config, "print_sample_json", True):
        return
    secret_keys = ("secret", "password", "token", "authorization", "jwt", "header")

    def sanitize(value):
        if isinstance(value, dict):
            return dict((key, "<redacted>" if any(word in key.lower() for word in secret_keys)
                         else sanitize(item)) for key, item in value.items())
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, str):
            for key in ("device_secret", "mqtt_password", "ntrip_password"):
                secret = getattr(config, key, "")
                if secret and secret in value:
                    value = value.replace(secret, "<redacted>")
        return value

    rendered = json.dumps(sanitize(payload), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    with OUTPUT_LOCK:
        target = stream or sys.stdout
        target.write(rendered + "\n")
        target.flush()


class RedactingFilter(logging.Filter):
    PATTERNS = [
        re.compile(r"(?i)(device[_ -]?secret|password|token|authorization)(\s*[:=]\s*)([^\s,;]+)"),
        re.compile(r"(?i)(basic|bearer)\s+[A-Za-z0-9._~+/=-]+"),
    ]

    def filter(self, record):
        message = record.getMessage()
        for pattern in self.PATTERNS:
            if pattern.groups >= 3:
                message = pattern.sub(r"\1\2<redacted>", message)
            else:
                message = pattern.sub(r"\1 <redacted>", message)
        record.msg = message
        record.args = ()
        return True


class CallbackHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self._callbacks = []
        self._lock = threading.Lock()

    def add_callback(self, callback):
        with self._lock:
            self._callbacks.append(callback)

    def emit(self, record):
        rendered = self.format(record)
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(rendered, record.levelname)
            except Exception:
                pass


def build_logger(log_dir):
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("tld.edge")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    redactor = RedactingFilter()
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "edge.log"), maxBytes=2 * 1024 * 1024,
        backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    callback_handler = CallbackHandler()
    callback_handler.setFormatter(formatter)
    callback_handler.addFilter(redactor)
    stream_handler = ConsoleHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)
    logger.addHandler(file_handler)
    logger.addHandler(callback_handler)
    logger.addHandler(stream_handler)
    logger.callback_handler = callback_handler
    return logger


def close_logger(logger):
    """刷新并关闭全部日志句柄，允许运行时在同一进程内干净退出。"""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass
