"""MQTT 发布器（FAST MODE / 普通节奏 / benchmark / continuous）.

要点：
    - 单客户端连接，控制 inflight 与队列，不无限创建线程/队列/循环。
    - QoS1 以 PUBACK 计数，publish() 成功 ≠ 数据库已写入（数据库侧由 Consumer + DB 确认）。
    - fast 模式不 sleep；interval>0 时按节奏 sleep。
    - continuous 模式支持 Ctrl+C 优雅退出并打印统计。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from scripts.mock_jetson.config import MockConfig
from scripts.mock_jetson.data_generator import DataGenerator


@dataclass
class PublishStats:
    generated: int = 0
    published: int = 0  # QoS1 PUBACK 成功数
    failed: int = 0      # 立即失败 + PUBACK 失败
    elapsed: float = 0.0

    @property
    def rate(self) -> float:
        return self.published / self.elapsed if self.elapsed > 0 else 0.0

    def report(self, title: str = "") -> str:
        lines = [
            f"Generated: {self.generated}",
            f"Published: {self.published}",
            f"Failed: {self.failed}",
            f"Elapsed: {self.elapsed:.2f} s",
            f"Average rate: {self.rate:.0f} msg/s",
        ]
        if title:
            lines.insert(0, title)
        return "\n".join(lines)


class MQTTPublisher:
    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self._acked = 0
        self._ack_failed = 0
        self._send_errors = 0

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        # paho 2.x 传 reason_code；兼容 1.x 传 rc
        rc = reason_code
        if rc is None:
            rc = getattr(mid, "rc", 0)
        if rc == 0 or (isinstance(rc, int) and rc == 0):
            self._acked += 1
        else:
            self._ack_failed += 1

    def _build_client(self, mqtt):
        client_id = f"tld-sim-{self.config.device_id}-{int(time.time() * 1000)}"
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        if self.config.mqtt_username:
            client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        client.max_inflight_messages_set(200)
        client.max_queued_messages_set(100_000)
        client.on_publish = self._on_publish
        return client

    def publish(
        self,
        count: int,
        interval: float = 0.0,
        disease_rate: float | None = None,
        continuous: bool = False,
    ) -> PublishStats:
        """发布数据.

        count:      非 continuous 模式下的消息数量（必须显式指定）
        interval:   每条间隔秒数；0 表示 fast 模式（不 sleep）
        continuous: 无限模式（count 被忽略），Ctrl+C 退出
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise SystemExit(
                "缺少 paho-mqtt，请先安装：pip install paho-mqtt==2.1.0"
            )

        generator = DataGenerator(self.config)
        if disease_rate is not None:
            generator.config.disease_rate = disease_rate

        client = self._build_client(mqtt)
        client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        client.loop_start()

        topic = self.config.topic()
        stats = PublishStats()
        start = time.time()

        def send_one() -> bool:
            payload = json.dumps(generator.generate())
            info = client.publish(topic, payload, qos=self.config.qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self._send_errors += 1
                return False
            stats.generated += 1
            return True

        try:
            if continuous:
                while True:
                    send_one()
                    if interval > 0:
                        time.sleep(interval)
            else:
                for _ in range(count):
                    send_one()
                    if interval > 0:
                        time.sleep(interval)
        except KeyboardInterrupt:
            pass

        # 等待 inflight PUBACK 冲刷完成
        deadline = time.time() + 15
        while (self._acked + self._ack_failed) < stats.generated and time.time() < deadline:
            time.sleep(0.01)

        client.loop_stop()
        client.disconnect()

        stats.published = self._acked
        stats.failed = self._send_errors + self._ack_failed + (stats.generated - self._acked - self._ack_failed)
        stats.elapsed = time.time() - start
        return stats

    def publish_payloads(self, payloads: list[dict], interval: float = 0.0) -> PublishStats:
        """发布一组预构造 payload（每份对应独立 data_id），复用单一连接.

        用于「图片触发上传」：由调用方先确定 data_id，再构造 MQTT 消息与 HTTP 图片。
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise SystemExit(
                "缺少 paho-mqtt，请先安装：pip install paho-mqtt==2.1.0"
            )

        # 重置本实例计数，避免复用实例时统计串扰
        self._acked = 0
        self._ack_failed = 0
        self._send_errors = 0

        client = self._build_client(mqtt)
        client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        client.loop_start()

        topic = self.config.topic()
        stats = PublishStats()
        start = time.time()

        for payload in payloads:
            info = client.publish(topic, json.dumps(payload), qos=self.config.qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self._send_errors += 1
            else:
                stats.generated += 1
            if interval > 0:
                time.sleep(interval)

        # 等待 inflight PUBACK 冲刷完成
        deadline = time.time() + 15
        while (self._acked + self._ack_failed) < stats.generated and time.time() < deadline:
            time.sleep(0.01)

        client.loop_stop()
        client.disconnect()

        stats.published = self._acked
        stats.failed = self._send_errors + self._ack_failed + (stats.generated - self._acked - self._ack_failed)
        stats.elapsed = time.time() - start
        return stats
