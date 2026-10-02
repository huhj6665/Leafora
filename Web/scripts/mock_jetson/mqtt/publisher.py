"""单连接 MQTT 会话，支持控制消息与采样消息交错发布。"""
from __future__ import annotations

import json
import queue
import time

from scripts.mock_jetson.config import MockConfig


class MQTTSession:
    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.client = None
        self._downlinks: "queue.Queue[dict]" = queue.Queue()

    def __enter__(self) -> "MQTTSession":
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("缺少 paho-mqtt，请安装 backend/requirements.txt") from exc
        client_id = f"virtual-jetson-{self.config.device_id}-{int(time.time() * 1000)}"
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if self.config.mqtt_username:
            self.client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                client.subscribe(self.config.downlink_topic(), qos=1)

        def on_message(client, userdata, message):
            try:
                self._downlinks.put_nowait(json.loads(message.payload.decode("utf-8")))
            except (ValueError, UnicodeDecodeError, queue.Full):
                return

        self.client.on_connect = on_connect
        self.client.on_message = on_message
        self.client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        self.client.loop_start()
        return self

    def publish(self, topic: str, payload: dict, timeout: float = 15.0) -> bool:
        if self.client is None:
            raise RuntimeError("MQTTSession 尚未连接")
        info = self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=self.config.qos)
        try:
            info.wait_for_publish(timeout=timeout)
        except RuntimeError:
            return False
        return bool(info.is_published())

    def publish_control(self, payload: dict) -> bool:
        return self.publish(self.config.control_topic(), payload)

    def publish_data(self, payload: dict) -> bool:
        return self.publish(self.config.topic(), payload)

    def publish_status(self, payload: dict) -> bool:
        return self.publish(self.config.status_topic(), payload)

    def publish_ack(self, payload: dict) -> bool:
        return self.publish(self.config.ack_topic(), payload)

    def next_downlink(self, timeout: float = 1.0) -> dict | None:
        try:
            return self._downlinks.get(timeout=timeout)
        except queue.Empty:
            return None

    def wait_control_ack(self, request_id: str, timeout: float = 10.0) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self._downlinks.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                return None
            if message.get("type") == "control_ack" and message.get("request_id") == request_id:
                return message
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
