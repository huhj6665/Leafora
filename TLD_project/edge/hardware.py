# -*- coding: utf-8 -*-
"""把既有硬件模块接入独立线程和 Latest Value Cache。"""

import glob
import os
import shutil
import threading
import time

from .protocol import utc_now


class DeviceStatusReader(object):
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self._last_cpu = self._read_cpu_times()

    @staticmethod
    def _read_cpu_times():
        try:
            with open("/proc/stat", "r") as handle:
                values = [int(value) for value in handle.readline().split()[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return sum(values), idle
        except (OSError, ValueError, IndexError):
            return None

    def _cpu_usage(self):
        current = self._read_cpu_times()
        previous = self._last_cpu
        self._last_cpu = current
        if current is None or previous is None:
            return None
        total = current[0] - previous[0]
        idle = current[1] - previous[1]
        return round(100.0 * (total - idle) / total, 1) if total > 0 else None

    @staticmethod
    def _memory_usage():
        try:
            values = {}
            with open("/proc/meminfo", "r") as handle:
                for line in handle:
                    key, value = line.split(":", 1)
                    values[key] = int(value.strip().split()[0])
            total = values["MemTotal"]
            available = values.get("MemAvailable", values.get("MemFree", 0))
            return round(100.0 * (total - available) / total, 1)
        except (OSError, KeyError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _temperature():
        for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
            try:
                with open(os.path.join(zone, "type"), "r") as handle:
                    kind = handle.read().strip().lower()
                if "cpu" not in kind:
                    continue
                with open(os.path.join(zone, "temp"), "r") as handle:
                    value = float(handle.read().strip())
                return round(value / 1000.0 if value > 1000 else value, 1)
            except (OSError, ValueError):
                continue
        return None

    def read(self, network_online):
        try:
            usage = shutil.disk_usage(self.root_dir)
            storage = round(100.0 * usage.used / usage.total, 1)
        except (OSError, ZeroDivisionError):
            storage = None
        return {
            "cpu_usage": self._cpu_usage(),
            "memory_usage": self._memory_usage(),
            "cpu_temperature": self._temperature(),
            "storage_usage": storage,
            "network_status": "online" if network_online else "offline",
        }


class HardwareSupervisor(object):
    def __init__(self, config, cache, logger, network_online_provider):
        self.config = config
        self.cache = cache
        self.logger = logger
        self.network_online_provider = network_online_provider
        self.camera = None
        self.engine = None
        self.gps = None
        self.sensors = None
        self._running = False
        self._threads = []
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._latest_frame_at = None
        self._detection_frame = None
        self._detection_frame_at = None
        self._detection_captured_at = None
        self._health_lock = threading.RLock()
        self._health = {
            "camera": False, "camera_detail": "尚未启动",
            "yolo": False, "yolo_detail": "尚未启动",
            "sensors": {"light": False, "air": False},
        }

    def _set_health(self, key, value, detail=None):
        with self._health_lock:
            self._health[key] = value
            if detail is not None:
                self._health[key + "_detail"] = detail

    def _ntrip_settings(self):
        return {
            "enabled": self.config.ntrip_enabled and self.config.ntrip_complete(),
            "server": self.config.ntrip_server,
            "port": self.config.ntrip_port,
            "mountpoint": self.config.ntrip_mountpoint,
            "username": self.config.ntrip_username,
            "password": self.config.ntrip_password,
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._initialize_modules()
        targets = [
            (self._camera_loop, "CameraWorker"),
            (self._inference_loop, "YoloWorker"),
            (self._gps_loop, "GpsCacheWorker"),
            (self._sensor_loop, "SensorWorker"),
            (self._status_loop, "DeviceStatusWorker"),
        ]
        for target, name in targets:
            thread = threading.Thread(target=target, name=name, daemon=False)
            thread.start()
            self._threads.append(thread)

    def _initialize_modules(self):
        try:
            from camera import Camera
            self.camera = Camera(device=self.config.camera_device, width=640, height=640, fps=30)
            self.camera.open()
            self._set_health("camera", True, "{}x{}".format(self.camera.width, self.camera.height))
            self.logger.info("Camera 已启动")
        except Exception as exc:
            self.camera = None
            self._set_health("camera", False, type(exc).__name__)
            self.logger.error("Camera 启动失败: {}".format(type(exc).__name__))
        try:
            from gps import GPSManager
            self.gps = GPSManager(
                gps_port=self.config.gps_uart_path,
                gps_baudrate=self.config.gps_baudrate,
                ntrip_settings=self._ntrip_settings(),
            )
            self.gps.start()
            self.logger.info("GPS 已启动")
        except Exception as exc:
            self.gps = None
            self.logger.error("GPS 启动失败: {}".format(type(exc).__name__))
        try:
            from sensors import SensorManager
            self.sensors = SensorManager(bus_number=1)
            with self._health_lock:
                self._health["sensors"] = {
                    "light": self.sensors.light is not None,
                    "air": self.sensors.air is not None,
                }
            self.logger.info("环境传感器初始化完成")
        except Exception as exc:
            self.sensors = None
            self.logger.error("环境传感器启动失败: {}".format(type(exc).__name__))

    def stop(self):
        self._running = False
        for thread in self._threads:
            thread.join()
        self._threads = []
        for module, method in ((self.camera, "release"),
                               (self.sensors, "close"), (self.gps, "close")):
            if module is not None:
                try:
                    getattr(module, method)()
                except Exception:
                    pass

    def restart_ntrip(self, config):
        self.config = config
        if self.gps is None:
            return False
        return self.gps.restart_ntrip(self._ntrip_settings())

    def _camera_loop(self):
        while self._running:
            if self.camera is None:
                time.sleep(1.0)
                continue
            try:
                frame = self.camera.read()
                if frame is None:
                    self._set_health("camera", False, "未收到视频帧")
                    time.sleep(0.05)
                    continue
                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_frame_at = utc_now()
                self._set_health("camera", True, "视频流正常")
            except Exception as exc:
                self._set_health("camera", False, type(exc).__name__)
                time.sleep(0.2)

    def _inference_loop(self):
        # 导入/创建 CUDA、加载 TRT、推理、释放全在唯一工作线程。
        try:
            from inference import InferenceEngine
            self.engine = InferenceEngine(self.config.model_path, 0.25, 0.45)
            self.engine.load()
            self._set_health("yolo", True, "TensorRT ready")
            self.logger.info("YOLO TensorRT 已启动")
            self._infer_frames()
        except Exception as exc:
            self._set_health("yolo", False, type(exc).__name__)
            self.logger.error("YOLO 工作线程异常: {}".format(type(exc).__name__))
        finally:
            if self.engine is not None:
                try:
                    self.engine.release()
                except Exception as exc:
                    self.logger.error("CUDA 所属线程释放失败: {}".format(type(exc).__name__))
                self.engine = None
            self._set_health("yolo", False, "推理线程已停止")

    def _infer_frames(self):
        last_frame_at = None
        while self._running:
            started = time.time()
            with self._frame_lock:
                frame = self._latest_frame.copy() if self._latest_frame is not None else None
                frame_at = self._latest_frame_at
            with self._health_lock:
                camera_ok = self._health.get("camera")
            if not camera_ok:
                previous = self.cache.get("detection") or {}
                self.cache.update("detection", None, sampled_at=previous.get("sampled_at"), valid=False, error="camera unavailable")
            elif frame is not None and frame_at != last_frame_at and self.engine is not None:
                sampled_at = utc_now()
                last_frame_at = frame_at
                try:
                    detections = self.engine.infer(frame)
                    self.cache.update("detection", detections, sampled_at=sampled_at, valid=True)
                    with self._frame_lock:
                        self._detection_frame = frame if detections else None
                        self._detection_frame_at = sampled_at if detections else None
                        self._detection_captured_at = frame_at if detections else None
                    self._set_health("yolo", True, "推理正常")
                except Exception as exc:
                    previous = self.cache.get("detection")
                    previous_at = previous.get("sampled_at") if previous else None
                    self.cache.update("detection", None, sampled_at=previous_at, valid=False, error=type(exc).__name__)
                    self._set_health("yolo", False, type(exc).__name__)
            time.sleep(max(0.01, 0.5 - (time.time() - started)))

    def _gps_loop(self):
        while self._running:
            position = None
            try:
                position = self.gps.get_position() if self.gps is not None else None
            except Exception:
                position = None
            if position is not None:
                sampled_at = position.pop("sampled_at", None)
                self.cache.update("location", position, sampled_at=sampled_at, valid=True)
            else:
                previous = self.cache.get("location")
                sampled_at = previous.get("sampled_at") if previous else None
                self.cache.update("location", {}, sampled_at=sampled_at, valid=False, error="GPS Fix unavailable")
            time.sleep(0.25)

    def _sensor_loop(self):
        while self._running:
            if self.sensors is None:
                self.cache.update("environment", {}, sampled_at=None, valid=False, error="sensors unavailable")
                time.sleep(2.0)
                continue
            try:
                values = self.sensors.read_all()
                valid = all(value is not None for value in values.values())
                self.cache.update("environment", values, sampled_at=utc_now(), valid=valid)
                with self._health_lock:
                    self._health["sensors"] = {
                        "light": values.get("lux") is not None,
                        "air": any(values.get(key) is not None for key in ("co2", "temperature", "humidity")),
                    }
            except Exception as exc:
                previous = self.cache.get("environment")
                sampled_at = previous.get("sampled_at") if previous else None
                self.cache.update("environment", {}, sampled_at=sampled_at, valid=False, error=type(exc).__name__)
            time.sleep(0.2)

    def _status_loop(self):
        reader = DeviceStatusReader(self.config.root_dir)
        while self._running:
            self.cache.update(
                "device_status", reader.read(bool(self.network_online_provider())), valid=True
            )
            time.sleep(1.0)

    def detection_frame(self, sampled_at):
        return self.detection_snapshot(sampled_at)[0]

    def detection_snapshot(self, sampled_at):
        with self._frame_lock:
            if sampled_at and sampled_at == self._detection_frame_at and self._detection_frame is not None:
                return self._detection_frame.copy(), self._detection_captured_at
        return None, None

    def preview_frame(self):
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def health(self):
        with self._health_lock:
            result = dict(self._health)
            result["sensors"] = dict(self._health.get("sensors") or {})
        location = self.cache.get("location")
        result["location"] = location.get("value") if location and location.get("valid") else {}
        result["ntrip_connected"] = bool(self.gps and self.gps.ntrip_connected)
        result["hardware_started"] = self._running
        return result
