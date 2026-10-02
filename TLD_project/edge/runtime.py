# -*- coding: utf-8 -*-
"""真实 Jetson 边缘端运行时编排。"""

import os
import shutil
import threading
import time

from .config import DeviceConfig, LocalConfigStore
from .data_manager import DataManager
from .hardware import HardwareSupervisor
from .http_client import DeviceHttpClient
from .latest import LatestValueCache
from .lifecycle import LifecycleController
from .logging_utils import build_logger, close_logger, print_sample
from .mqtt_client import MqttQueueWorker, MqttSession
from .network_config import (
    build_backend_url,
    diagnose_http_health,
    diagnose_mqtt,
    ensure_network_change_allowed,
    network_form_values,
    normalize_remote_host,
    validate_port,
)
from .protocol import new_id, utc_now
from .state import DeviceState
from .store import PersistentStore
from .upload_worker import ImageUploadWorker


class EdgeRuntime(object):
    def __init__(self, root_dir, config_path=None):
        self.root_dir = os.path.abspath(root_dir)
        self.config = DeviceConfig.load(self.root_dir, config_path=config_path)
        for directory in (self.config.state_dir, self.config.image_dir,
                          self.config.qr_dir, self.config.log_dir):
            if not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
        self.logger = build_logger(self.config.log_dir)
        self.store = PersistentStore(self.config.db_path)
        self.store.cleanup_completed_image_files()
        self.cache = LatestValueCache()
        self.data_manager = DataManager(self.config.device_id, self.cache)
        self.http = DeviceHttpClient(
            self.config.backend_url, self.config.device_id,
            self.config.device_secret, self.config.http_timeout_s
        )
        self.mqtt = MqttSession(self.config, self.logger)
        self.hardware = HardwareSupervisor(
            self.config, self.cache, self.logger, lambda: self.mqtt.connected
        )
        self.lifecycle = LifecycleController(
            self.config, self.store, self.mqtt, self.http,
            self.hardware, self.logger
        )
        self.mqtt_worker = MqttQueueWorker(self.store, self.mqtt, self.logger)
        self.upload_worker = ImageUploadWorker(self.store, self.http, self.logger)
        self._running = False
        self._start_stop_lock = threading.RLock()
        self._network_lock = threading.RLock()
        self._network_status_lock = threading.RLock()
        self._network_status = {
            "save": {"ok": None, "category": "not_saved", "message": "本轮尚未保存"},
            "http": {"ok": None, "category": "not_tested", "message": "尚未测试 HTTP"},
            "mqtt": {"ok": None, "category": "not_tested", "message": "尚未测试 MQTT"},
        }
        self._threads = []
        self._last_image_detection_at = None
        self._hardware_started = False
        self.mqtt.status_provider = self.heartbeat
        self.mqtt.on_connected = self.lifecycle.request_final_replay

    def start(self, start_hardware=False):
        """启动边缘运行时。

        ``start_hardware=False`` 用于局域网配置和动态配对：只启动网络会话、
        补传线程和状态心跳，不导入或启动 Camera/TensorRT/GPS/I2C。这样配置阶段
        不会占用 Jetson 算力，也不会触发尚待修复的 CUDA 上下文生命周期问题。
        """
        with self._start_stop_lock:
            if self._running:
                return
            self._running = True
            missing = self.config.missing_cloud_settings()
            if missing:
                self.logger.warning("云端配置不完整: {}".format(", ".join(missing)))
            try:
                self.mqtt.start()
            except Exception as exc:
                self.logger.error("MQTT 不可用: {}".format(str(exc)))
            self.mqtt_worker.start()
            self.upload_worker.start()
            self.lifecycle.start_command_worker()
            self._hardware_started = bool(start_hardware)
            if self._hardware_started:
                self.hardware.start()
            targets = [(self._monitor_loop, "RuntimeMonitor")]
            if self._hardware_started:
                targets.insert(0, (self._sample_loop, "SampleWorker"))
            for target, name in targets:
                thread = threading.Thread(target=target, name=name, daemon=True)
                thread.start()
                self._threads.append(thread)
            mode = "完整硬件" if self._hardware_started else "通信配置"
            self.logger.info("TLD Jetson {}模式已启动".format(mode))

    def stop(self):
        with self._start_stop_lock:
            self._running = False
            self.lifecycle.stop_command_worker()
            for thread in self._threads:
                thread.join()
            self._threads = []
            if self._hardware_started:
                self.hardware.stop()
            self._hardware_started = False
            self.upload_worker.stop()
            self.mqtt_worker.stop()
            self.mqtt.stop()
            self.store.close()
            self.logger.info("TLD Jetson 运行时已停止")
            close_logger(self.logger)

    def _monitor_loop(self):
        last_status = 0.0
        while self._running:
            try:
                self.lifecycle.network_tick()
                if time.time() - last_status >= 5.0 and self.mqtt.connected:
                    payload = self.heartbeat()
                    self.mqtt.publish(self.mqtt.topics.status, payload, retain=True)
                    last_status = time.time()
            except Exception as exc:
                self.logger.error("运行状态监控异常: {}".format(type(exc).__name__))
            time.sleep(0.5)

    def _sample_loop(self):
        while self._running:
            cycle_start = time.time()
            state = self.lifecycle.state.state
            if state in (DeviceState.RUNNING, DeviceState.RUNNING_OFFLINE):
                try:
                    self._sample_once()
                except Exception as exc:
                    with self.lifecycle.execution_lock:
                        active = self.lifecycle.active
                        if active:
                            active["errors"] = active.get("errors", 0) + 1
                            self.store.set_meta("active_inspection", active)
                    self.logger.error("采样周期失败: {}".format(type(exc).__name__))
            delay = self.config.sample_interval_s - (time.time() - cycle_start)
            time.sleep(max(0.02, delay))

    def _sample_once(self):
        with self.lifecycle.execution_lock:
            return self._sample_once_locked()

    def _sample_once_locked(self):
        active = self.lifecycle.active
        if not active or active.get("phase") not in ("RUNNING", "RUNNING_OFFLINE"):
            return
        sequence = int(active.get("sequence", 0)) + 1
        data_id = new_id("DATA")
        payload = self.data_manager.build(active["inspection_id"], sequence, data_id=data_id, task=active)
        active["sequence"] = sequence
        active["samples"] = int(active.get("samples", 0)) + 1
        active["last_data_id"] = data_id
        results = payload["detection"]["results"]
        active["targets"] = int(active.get("targets", 0)) + len(results)
        detection_at = payload["detection"].get("sampled_at")
        image = None
        if results and detection_at and detection_at != self._last_image_detection_at:
            image = self._save_detection_image(active["inspection_id"], data_id,
                                               payload["timestamp"], detection_at)
            if image:
                active["images"] = int(active.get("images", 0)) + 1
        try:
            self.store.commit_sample(active, self.mqtt.topics.data, payload, image)
        except Exception:
            if image:
                try:
                    os.remove(image["path"])
                except OSError:
                    pass
            raise
        if image:
            self._last_image_detection_at = detection_at
        self.logger.info("[DATA_ENQUEUED] data_id={} sequence={}".format(data_id, sequence))
        print_sample(payload, self.config)
        return payload

    def _save_detection_image(self, inspection_id, data_id, captured_at, detection_at):
        try:
            free_mb = shutil.disk_usage(self.config.image_dir).free / (1024.0 * 1024.0)
        except OSError:
            free_mb = 0
        if free_mb < self.config.min_free_disk_mb:
            self.logger.critical("磁盘空间不足，停止保存新的病害图片；结构化数据继续")
            return False
        frame, frame_captured_at = self.hardware.detection_snapshot(detection_at)
        if frame is None or not frame_captured_at:
            self.logger.warning("检测帧已更新，未保存病害图片")
            return False
        try:
            import cv2
        except ImportError:
            self.logger.error("OpenCV 不可用，无法保存病害图片")
            return False
        image_id = new_id("IMG")
        path = os.path.join(self.config.image_dir, image_id + ".jpg")
        if not cv2.imwrite(path, frame):
            self.logger.error("病害原图写入失败")
            return False
        return {"image_id": image_id, "path": path,
                "captured_at": frame_captured_at}

    def heartbeat(self, offline=False):
        health = self.hardware.health()
        active = self.lifecycle.active
        state = self.lifecycle.state.state
        pending = (self.store.pending_data_for_inspection(active["inspection_id"]) if active
                   else self.store.pending_business_count())
        ready = (self._hardware_started and bool(self.config.device_secret and self.config.backend_url)
                 and self.lifecycle.preflight().ok)
        if self._hardware_started and state in (DeviceState.RUNNING, DeviceState.RUNNING_OFFLINE):
            operating = "RUNNING"
        elif state == DeviceState.ERROR:
            operating = "ERROR"
        elif ready and not active:
            operating = "SHUTDOWN"
        else:
            operating = "STARTUP"
        fix = (health.get("location") or {}).get("fix", "No Fix")
        from .data_manager import RTK_STATUS
        fix_code = RTK_STATUS.get(fix, "NO_FIX")
        return {
            "type": "device_status", "device_id": self.config.device_id, "timestamp": utc_now(),
            "communication_status": "OFFLINE" if offline or not self.mqtt.connected else "ONLINE",
            "operating_status": operating,
            "sync_status": "PENDING" if pending else "SYNCED" if active else "IDLE",
            "pending_sync_count": pending, "inspection_id": active.get("inspection_id") if active else None,
            "gps_fix": fix_code, "rtk_status": fix_code,
            "camera_status": "NOT_STARTED" if not self._hardware_started else "READY" if health.get("camera") else "ERROR",
            "inference_status": "NOT_STARTED" if not self._hardware_started else "READY" if health.get("yolo") else "ERROR",
            "storage_usage": ((self.cache.get("device_status") or {}).get("value") or {}).get("storage_usage"),
        }

    def snapshot(self):
        active = self.lifecycle.active
        cache = self.cache.snapshot()
        with self._network_status_lock:
            network_status = dict(
                (key, dict(value)) for key, value in self._network_status.items()
            )
        network_status["backend_url"] = self.config.backend_url
        network_status["mqtt_host"] = self.config.mqtt_host
        network_status["mqtt_port"] = self.config.mqtt_port
        network_status["live_mqtt_connected"] = self.mqtt.connected
        return {
            "device_id": self.config.device_id,
            "state": self.lifecycle.state.state,
            "state_reason": self.lifecycle.state.reason,
            "bound": self.lifecycle.bound,
            "owner_nickname": self.lifecycle.owner_nickname,
            "mqtt_connected": self.mqtt.connected,
            "network": network_status,
            "active": active,
            "queues": self.store.pending_counts(),
            "health": self.hardware.health(),
            "cache": cache,
        }

    def create_pairing(self):
        with self._network_lock:
            return self.lifecycle.create_pairing()

    def pairing_status(self):
        return self.lifecycle.pairing_status()

    def cancel_pairing(self):
        self.lifecycle.cancel_pairing()

    def preflight(self):
        return self.lifecycle.preflight()

    def start_inspection(self, name="", location_note=""):
        with self._network_lock:
            return self.lifecycle.start_inspection(name, location_note)

    def end_inspection(self):
        with self._network_lock:
            return self.lifecycle.end_inspection()

    def network_form(self):
        """返回可展示的网络字段；永不返回 MQTT 密码。"""
        return network_form_values(self.config)

    def credential_status(self):
        """返回可安全展示的设备凭据状态，不返回永久密钥。"""
        return {
            "device_id": self.config.device_id,
            "device_secret_present": bool(self.config.device_secret),
        }

    def save_device_secret(self, device_secret):
        """安全保存永久设备密钥并热重建已认证的网络客户端。"""
        secret = str(device_secret or "").strip()
        if not secret:
            raise ValueError("设备永久密钥不能为空")
        with self._network_lock:
            ensure_network_change_allowed(self.lifecycle.state.state)
            LocalConfigStore(self.config.config_path).save({"DEVICE_SECRET": secret})
            new_config = DeviceConfig.load(self.root_dir, self.config.config_path)
            reloaded, reload_message = self._rebuild_network_clients(new_config)
            self.logger.info("设备永久密钥已安全保存")
            return {
                "saved": True,
                "reloaded": reloaded,
                "device_id": new_config.device_id,
                "device_secret_present": True,
                "message": reload_message,
            }

    def _set_network_status(self, channel, result):
        with self._network_status_lock:
            self._network_status[channel] = dict(result)

    def save_network(self, host, http_port, mqtt_port, mqtt_username,
                     mqtt_password="", scheme="http", mqtt_host=None):
        """原子保存局域网设置，并在安全状态热重建 HTTP/MQTT 客户端。"""
        with self.lifecycle.execution_lock, self._network_lock:
            ensure_network_change_allowed(self.lifecycle.state.state)
            if self.store.pending_counts()["total"]:
                raise RuntimeError("仍有补传队列，禁止修改云端地址")
            normalized_host = normalize_remote_host(host)
            http_port = validate_port(http_port, "HTTP 端口")
            mqtt_port = validate_port(mqtt_port, "MQTT 端口")
            backend_url = build_backend_url(normalized_host, http_port, scheme)
            password = mqtt_password
            if password == "":
                password = self.config.mqtt_password
            updates = {
                "BACKEND_URL": backend_url,
                "MQTT_HOST": normalize_remote_host(mqtt_host or normalized_host),
                "MQTT_PORT": str(mqtt_port),
                "MQTT_USERNAME": str(mqtt_username or "").strip(),
                "MQTT_PASSWORD": password,
            }

            # 保存前后均检查状态，避免用户在校验期间启动任务。
            ensure_network_change_allowed(self.lifecycle.state.state)
            LocalConfigStore(self.config.config_path).save(updates)
            new_config = DeviceConfig.load(self.root_dir, self.config.config_path)
            reloaded, reload_message = self._rebuild_network_clients(new_config)
            result = {
                "saved": True,
                "reloaded": reloaded,
                "restart_required": not reloaded,
                "backend_url": new_config.backend_url,
                "mqtt_host": new_config.mqtt_host,
                "mqtt_port": new_config.mqtt_port,
                "password_saved": bool(new_config.mqtt_password),
                "message": reload_message,
            }
            self._set_network_status("save", {
                "ok": True,
                "category": "reloaded" if reloaded else "restart_required",
                "message": reload_message,
            })
            self.logger.info("云端网络配置已保存；{}".format(reload_message))
            return result

    def _rebuild_network_clients(self, new_config):
        """仅替换网络对象，不重启 Camera、YOLO、GPS 或传感器。"""
        new_http = DeviceHttpClient(
            new_config.backend_url, new_config.device_id,
            new_config.device_secret, new_config.http_timeout_s
        )
        new_mqtt = MqttSession(new_config, self.logger)
        new_mqtt.status_provider = self.heartbeat
        new_mqtt.on_connected = self.lifecycle.request_final_replay
        new_mqtt.add_downlink_callback(self.lifecycle.handle_downlink)
        new_mqtt_worker = MqttQueueWorker(self.store, new_mqtt, self.logger)
        new_upload_worker = ImageUploadWorker(self.store, new_http, self.logger)

        with self._start_stop_lock:
            was_running = self._running
            self.upload_worker.stop()
            self.mqtt_worker.stop()
            self.mqtt.stop()
            self.config = new_config
            self.http = new_http
            self.mqtt = new_mqtt
            self.mqtt_worker = new_mqtt_worker
            self.upload_worker = new_upload_worker
            self.lifecycle.config = new_config
            self.lifecycle.http = new_http
            self.lifecycle.mqtt = new_mqtt
            self.hardware.config = new_config
            if not was_running:
                return True, "配置已加载，将在运行时启动时生效"

            mqtt_started = False
            try:
                mqtt_started = bool(self.mqtt.start())
            except Exception as exc:
                self.logger.error("新 MQTT 客户端启动失败: {}".format(type(exc).__name__))
            self.mqtt_worker.start()
            self.upload_worker.start()
            if mqtt_started:
                return True, "网络客户端已安全重建；连接状态请分别测试"
            return False, "配置已安全保存，但 MQTT 客户端未启动，请安装依赖或重启后再测"

    def test_http_network(self, host, http_port, scheme="http"):
        try:
            target = build_backend_url(host, http_port, scheme)
            result = diagnose_http_health(target, timeout_s=min(self.config.http_timeout_s, 8.0))
        except Exception:
            result = {"ok": False, "category": "invalid_address", "message": "HTTP 地址无效"}
        self._set_network_status("http", result)
        return result

    def test_mqtt_network(self, host, mqtt_port, mqtt_username, mqtt_password=""):
        password = mqtt_password if mqtt_password != "" else self.config.mqtt_password
        result = diagnose_mqtt(
            host, mqtt_port, mqtt_username, password,
            use_tls=self.config.mqtt_tls, timeout_s=8.0
        )
        self._set_network_status("mqtt", result)
        return result

    def save_ntrip(self, server, port, mountpoint, username, password, enabled=True):
        if password == "" and self.config.ntrip_password:
            password = self.config.ntrip_password
        updates = {
            "NTRIP_ENABLED": "true" if enabled else "false",
            "NTRIP_SERVER": server.strip(),
            "NTRIP_PORT": str(int(port)),
            "NTRIP_MOUNTPOINT": mountpoint.strip(),
            "NTRIP_USERNAME": username.strip(),
            "NTRIP_PASSWORD": password,
        }
        LocalConfigStore(self.config.config_path).save(updates)
        self.config = DeviceConfig.load(self.root_dir, self.config.config_path)
        self.hardware.restart_ntrip(self.config)
        self.logger.info("NTRIP 本地配置已保存，NTRIP Client 已重启")

    def clear_ntrip(self):
        LocalConfigStore(self.config.config_path).save(
            {"NTRIP_ENABLED": "false"},
            clear_keys=["NTRIP_SERVER", "NTRIP_PORT", "NTRIP_MOUNTPOINT",
                        "NTRIP_USERNAME", "NTRIP_PASSWORD"]
        )
        self.config = DeviceConfig.load(self.root_dir, self.config.config_path)
        self.hardware.restart_ntrip(self.config)
        self.logger.info("NTRIP 本地凭据已清除")

    @staticmethod
    def test_ntrip(server, port, mountpoint, username, password):
        from gps.ntrip_client import NTRIPClient
        client = NTRIPClient(
            server=server, port=int(port), mountpoint=mountpoint,
            username=username, password=password, rtcm_writer=lambda data: len(data)
        )
        try:
            return client.test_connection()
        finally:
            client.close()
