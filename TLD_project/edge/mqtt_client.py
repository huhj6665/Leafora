# -*- coding: utf-8 -*-
"""MQTT 会话与 SQLite 出站消息补传线程。"""

import json
import threading
import time

from .protocol import Topics, utc_now


class MqttUnavailable(RuntimeError):
    pass


class MqttSession(object):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.topics = Topics(config.device_id)
        self._client = None
        self._connected = threading.Event()
        self._callbacks = []
        self.status_provider = None
        self.on_connected = None

    def status_payload(self, offline=False):
        payload = self.status_provider(offline=offline) if self.status_provider else {
            "type": "device_status", "device_id": self.config.device_id,
            "operating_status": "STARTUP", "sync_status": "IDLE", "pending_sync_count": 0,
            "camera_status": "NOT_STARTED", "inference_status": "NOT_STARTED",
            "gps_fix": "NO_FIX", "rtk_status": "NO_FIX", "inspection_id": None,
        }
        payload["communication_status"] = "OFFLINE" if offline else "ONLINE"
        payload["timestamp"] = utc_now()
        return payload

    @property
    def connected(self):
        return self._connected.is_set()

    def add_downlink_callback(self, callback):
        self._callbacks.append(callback)

    def start(self):
        if not self.config.mqtt_host:
            self.logger.warning("MQTT_HOST 未配置")
            return False
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise MqttUnavailable("缺少 paho-mqtt 依赖")
        self._client = mqtt.Client(client_id=self.config.device_id, clean_session=False)
        if self.config.mqtt_username:
            self._client.username_pw_set(
                self.config.mqtt_username, self.config.mqtt_password or None
            )
        if self.config.mqtt_tls:
            self._client.tls_set()
        will = self.status_payload(offline=True)
        self._client.will_set(
            self.topics.status, json.dumps(will, separators=(",", ":")),
            qos=1, retain=True
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        try:
            self._client.connect_async(
                self.config.mqtt_host, self.config.mqtt_port,
                keepalive=self.config.mqtt_keepalive
            )
            self._client.loop_start()
        except Exception as exc:
            self._client = None
            raise MqttUnavailable("MQTT 启动失败: {}".format(type(exc).__name__))
        return True

    def stop(self):
        client = self._client
        if self.connected and client is not None:
            self.publish(self.topics.status, self.status_payload(offline=True), retain=True, confirm=True)
        self._client = None
        self._connected.clear()
        if client is not None:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected.set()
            client.subscribe(self.topics.downlink, qos=1)
            self.publish(self.topics.status, self.status_payload(), retain=True)
            if self.on_connected:
                self.on_connected()
            self.logger.info("MQTT 已连接并订阅 downlink")
        else:
            self._connected.clear()
            self.logger.warning("MQTT 连接失败，返回码 {}".format(rc))

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        self.logger.warning("MQTT 已断开，返回码 {}".format(rc))

    def _on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self.logger.warning("忽略无法解析的 MQTT 下行消息")
            return
        for callback in list(self._callbacks):
            try:
                callback(payload)
            except Exception as exc:
                self.logger.error("MQTT 下行处理失败: {}".format(type(exc).__name__))

    def publish(self, topic, payload, retain=False, confirm=False):
        if not self.connected or self._client is None:
            return False
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            info = self._client.publish(topic, encoded, qos=1, retain=bool(retain))
            if info.rc != 0:
                return False
            if confirm:
                info.wait_for_publish(timeout=5.0)
                return bool(info.is_published())
            return True
        except Exception:
            return False


class MqttQueueWorker(object):
    def __init__(self, store, mqtt_session, logger):
        self.store = store
        self.mqtt = mqtt_session
        self.logger = logger
        self._running = False
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="MqttQueue", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join()
        self._thread = None

    def _loop(self):
        while self._running:
            if not self.mqtt.connected:
                time.sleep(0.5)
                continue
            rows = self.store.due_messages(20)
            if not rows:
                time.sleep(0.25)
                continue
            for row in rows:
                if not self._running:
                    break
                try:
                    payload = json.loads(row["payload_json"])
                    retain = row["kind"] == "status"
                    if row["attempts"]:
                        self.logger.info("[MQTT_RETRY] {} id={} attempt={}".format(row["kind"], row["business_id"], row["attempts"] + 1))
                    published = self.mqtt.publish(
                        row["topic"], payload, retain=retain, confirm=True
                    )
                    if not published:
                        self.store.fail_message(row["id"], "MQTT publish failed")
                        self.logger.warning("[MQTT_RETRY_FAILED] {} id={}".format(row["kind"], row["business_id"]))
                    elif row["kind"] == "control":
                        self.store.fail_message(row["id"], "waiting for control ACK")
                    else:
                        self.store.mark_message_done(row["id"])
                        self.logger.info("[BROKER_PUBACK] {} id={}（Broker 接收，不代表云端入库）".format(row["kind"], row["business_id"]))
                except Exception as exc:
                    self.store.fail_message(row["id"], type(exc).__name__)
