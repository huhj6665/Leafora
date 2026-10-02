# -*- coding: utf-8 -*-
"""设备本地配置。

敏感值只从进程环境或运行目录下的 ``device.env`` 读取。保存时在 Linux
上将权限收紧为 0600；日志层不得打印本对象的完整内容。
"""

import os
import stat
import threading


DEFAULT_DEVICE_ID = "TLD_SIM_002"


def _as_bool(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            following = value[index + 1]
            result.append("\n" if following == "n" else following)
            index += 2
        else:
            result.append(value[index])
            index += 1
    return "".join(result)


class LocalConfigStore(object):
    """最小化的 UTF-8 ``KEY=VALUE`` 配置读写器。"""

    SECRET_KEYS = set(["DEVICE_SECRET", "MQTT_PASSWORD", "NTRIP_PASSWORD"])

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._lock = threading.RLock()

    def load(self):
        values = {}
        if not os.path.isfile(self.path):
            return values
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    if key:
                        values[key] = _unquote(value)
        return values

    @staticmethod
    def _encode(value):
        value = str(value)
        value = value.replace("\\", "\\\\").replace("\n", "\\n")
        return value.replace("=", "\\=")

    def save(self, updates, clear_keys=None):
        clear_keys = set(clear_keys or [])
        with self._lock:
            current = self.load()
            for key in clear_keys:
                current.pop(key, None)
            for key, value in updates.items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[str(key)] = str(value)
            directory = os.path.dirname(self.path)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            temp_path = self.path + ".tmp"
            try:
                descriptor = os.open(
                    temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    stat.S_IRUSR | stat.S_IWUSR
                )
                try:
                    os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write("# TLD Jetson local configuration. Do not commit this file.\n")
                    for key in sorted(current):
                        handle.write("{}={}\n".format(key, self._encode(current[key])))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
            except Exception:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                raise
            try:
                os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass


class DeviceConfig(object):
    """运行配置快照；不在源码中保存服务器地址或凭据。"""

    def __init__(self, values, root_dir, config_path):
        self.root_dir = os.path.abspath(root_dir)
        self.config_path = os.path.abspath(config_path)
        self.device_id = values.get("DEVICE_ID", DEFAULT_DEVICE_ID).strip() or DEFAULT_DEVICE_ID
        if self.device_id != DEFAULT_DEVICE_ID:
            raise ValueError("真实 Jetson 只能使用 TLD_SIM_002，请核对本地 DEVICE_ID")
        self.device_secret = values.get("DEVICE_SECRET", "")
        self.backend_url = values.get("BACKEND_URL", "").rstrip("/")
        self.mqtt_host = values.get("MQTT_HOST", "")
        self.mqtt_port = _as_int(values.get("MQTT_PORT"), 1883)
        self.mqtt_username = values.get("MQTT_USERNAME", "")
        self.mqtt_password = values.get("MQTT_PASSWORD", "")
        self.mqtt_tls = _as_bool(values.get("MQTT_TLS"), False)
        self.mqtt_keepalive = _as_int(values.get("MQTT_KEEPALIVE"), 30)
        self.http_timeout_s = _as_float(values.get("HTTP_TIMEOUT_S"), 15.0)
        self.start_ack_timeout_s = _as_float(values.get("START_ACK_TIMEOUT_S"), 8.0)
        self.start_retries = _as_int(values.get("START_RETRIES"), 3)
        self.sample_interval_s = _as_float(values.get("SAMPLE_INTERVAL_S"), 0.5)
        self.print_sample_json = _as_bool(values.get("PRINT_SAMPLE_JSON"), True)
        self.allow_legacy_control = _as_bool(values.get("ALLOW_LEGACY_CONTROL"), False)
        self.normal_image_interval = _as_int(values.get("NORMAL_IMAGE_INTERVAL"), 20)
        self.min_free_disk_mb = _as_int(values.get("MIN_FREE_DISK_MB"), 512)
        self.camera_device = values.get("CAMERA_DEVICE", "/dev/video0")
        self.model_path = values.get(
            "MODEL_PATH", os.path.join(self.root_dir, "models", "train_best.engine")
        )
        self.gps_uart_path = values.get("GPS_UART_PATH", "") or None
        self.gps_baudrate = _as_int(values.get("GPS_BAUDRATE"), 38400)
        self.ntrip_enabled = _as_bool(values.get("NTRIP_ENABLED"), False)
        self.ntrip_server = values.get("NTRIP_SERVER", "")
        self.ntrip_port = _as_int(values.get("NTRIP_PORT"), 2101)
        self.ntrip_mountpoint = values.get("NTRIP_MOUNTPOINT", "")
        self.ntrip_username = values.get("NTRIP_USERNAME", "")
        self.ntrip_password = values.get("NTRIP_PASSWORD", "")
        state_dir = values.get("STATE_DIR", os.path.join(self.root_dir, "runtime"))
        self.state_dir = os.path.abspath(state_dir)
        self.db_path = os.path.join(self.state_dir, "edge_queue.sqlite3")
        self.image_dir = os.path.join(self.state_dir, "images")
        self.qr_dir = os.path.join(self.state_dir, "pairing")
        self.log_dir = os.path.join(self.state_dir, "logs")

    @classmethod
    def load(cls, root_dir, config_path=None, environ=None):
        if config_path is None:
            config_path = os.path.join(root_dir, "runtime", "device.env")
        store = LocalConfigStore(config_path)
        values = store.load()
        source = os.environ if environ is None else environ
        for key, value in source.items():
            if key.startswith("TLD_"):
                values[key[4:]] = value
        return cls(values, root_dir, config_path)

    def missing_cloud_settings(self):
        missing = []
        if not self.backend_url:
            missing.append("BACKEND_URL")
        if not self.device_secret:
            missing.append("DEVICE_SECRET")
        if not self.mqtt_host:
            missing.append("MQTT_HOST")
        return missing

    def ntrip_complete(self):
        return bool(
            self.ntrip_server and self.ntrip_port and self.ntrip_mountpoint
            and self.ntrip_username and self.ntrip_password
        )
