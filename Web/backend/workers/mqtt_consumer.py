"""MQTT Consumer（独立 worker）.

订阅 ``{prefix}/device/+/data``，消费 Jetson / 模拟设备上报的 V1.0 数据，
复用 ingest 管线完成完整校验（Topic / Schema / device_id / 设备身份 / 绑定 /
data_id 幂等）后写入 PostgreSQL。

设计要点：
    - 独立于 FastAPI HTTP 生命周期运行，作为单独进程启动。
    - 复用单一 AsyncSession（连接池），不每条消息重建连接。
    - paho-mqtt 网络线程通过线程安全队列桥接 async 处理循环。
    - 支持 Ctrl+C 优雅退出并打印统计。

运行（在 backend 目录）：
    python -m workers.mqtt_consumer
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import signal
import sys
import time

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.services import command_delivery, inspection_service
from app.services.inspection_service import (
    CONTROL_COMPLETED,
    CONTROL_DUPLICATE,
    CONTROL_STARTED,
    INGEST_DUPLICATE,
    INGEST_INSERTED,
    IngestResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("mqtt_consumer")


class ConsumerStats:
    """消费统计（线程安全计数）."""

    def __init__(self) -> None:
        self.received = 0
        self.inserted = 0
        self.duplicate = 0
        self.failed = 0
        self.invalid_topic = 0
        self.invalid_schema = 0
        self.device_mismatch = 0
        self.unknown_device = 0
        self.unbound_device = 0
        self.control_started = 0
        self.control_completed = 0
        self.control_duplicate = 0

    def apply(self, result: IngestResult) -> None:
        if result.status == INGEST_INSERTED:
            self.inserted += 1
        elif result.status == INGEST_DUPLICATE:
            self.duplicate += 1
        elif result.status == "invalid_topic":
            self.invalid_topic += 1
        elif result.status == "invalid_schema":
            self.invalid_schema += 1
        elif result.status == "device_mismatch":
            self.device_mismatch += 1
        elif result.status == "unknown_device":
            self.unknown_device += 1
        elif result.status == "unbound_device":
            self.unbound_device += 1
        elif result.status == "control_started":
            self.control_started += 1
        elif result.status == "control_completed":
            self.control_completed += 1
        elif result.status == "control_duplicate":
            self.control_duplicate += 1
        elif result.status not in {"status_updated", "ack_received"}:
            self.failed += 1

    def snapshot(self) -> dict:
        return {
            "received": self.received,
            "inserted": self.inserted,
            "duplicate": self.duplicate,
            "failed": self.failed,
            "invalid_topic": self.invalid_topic,
            "invalid_schema": self.invalid_schema,
            "device_mismatch": self.device_mismatch,
            "unknown_device": self.unknown_device,
            "unbound_device": self.unbound_device,
            "control_started": self.control_started,
            "control_completed": self.control_completed,
            "control_duplicate": self.control_duplicate,
        }


async def _process_message(
    session, msg_queue: "queue.Queue", stats: ConsumerStats, client=None
) -> None:
    """消费循环：从队列取消息 → ingest → 计数."""
    pending = None
    retries = 0
    while True:
        if pending is None:
            try:
                mqtt_msg = await asyncio.to_thread(msg_queue.get, True, 1)
            except queue.Empty:
                continue
            stats.received += 1
        else:
            mqtt_msg = pending
        try:
            topic = mqtt_msg.topic
            payload = json.loads(mqtt_msg.payload.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 非法 JSON 记 failed
            stats.failed += 1
            logger.warning("INVALID_JSON err=%s", exc)
            if client is not None:
                client.ack(mqtt_msg.mid, mqtt_msg.qos)
            pending, retries = None, 0
            continue

        try:
            if topic.endswith("/control"):
                result = await inspection_service.ingest_control_message(session, payload, topic)
            elif topic.endswith("/status"):
                result = await inspection_service.ingest_status_message(session, payload, topic)
            elif topic.endswith("/ack"):
                result = await inspection_service.ingest_ack_message(session, payload, topic)
            else:
                result = await inspection_service.ingest_message(session, payload, topic)
            # Services commit accepted messages. Release SELECT/row locks and
            # expired identity-map values after rejects and duplicate messages.
            await session.rollback()
            if client is not None:
                # Broker delivery is confirmed only after DB commit (or an
                # explicit validation reject); a restart can replay uncommitted QoS1.
                client.ack(mqtt_msg.mid, mqtt_msg.qos)
            pending, retries = None, 0
            stats.apply(result)
            if result.status in {INGEST_INSERTED, CONTROL_STARTED, CONTROL_COMPLETED}:
                logger.debug("INGEST inserted device=%s data_id=%s", result.device_id, result.data_id)
            elif result.status not in {INGEST_DUPLICATE, CONTROL_DUPLICATE, "status_updated", "ack_received"}:
                logger.warning(
                    "INGEST_%s device=%s data_id=%s reason=%s",
                    result.status, result.device_id, result.data_id, result.reason,
                )
        except SQLAlchemyError:
            stats.failed += 1
            logger.warning("INGEST_DB_RETRY device topic=%s", mqtt_msg.topic)
            await session.rollback()
            pending = mqtt_msg
            retries += 1
            await asyncio.sleep(min(30, 2 ** min(retries - 1, 5)))
        except Exception as exc:  # noqa: BLE001 - 单条失败不终止 worker
            stats.failed += 1
            logger.exception("INGEST_EXCEPTION err=%s", exc)
            await session.rollback()
            pending, retries = None, 0


async def run() -> None:
    """启动 MQTT Consumer."""
    try:
        import paho.mqtt.client as mqtt  # noqa: F401
    except ImportError:
        logger.error(
            "缺少 paho-mqtt，请先安装：pip install paho-mqtt==2.1.0"
        )
        sys.exit(1)

    data_topic = f"{settings.MQTT_TOPIC_PREFIX}/device/+/data"
    control_topic = f"{settings.MQTT_TOPIC_PREFIX}/device/+/control"
    status_topic = f"{settings.MQTT_TOPIC_PREFIX}/device/+/status"
    ack_topic = f"{settings.MQTT_TOPIC_PREFIX}/device/+/ack"
    logger.info(
        "MQTT Consumer 启动 host=%s port=%s topics=%s,%s",
        settings.MQTT_HOST, settings.MQTT_PORT, data_topic, control_topic,
    )

    # 线程安全队列作为网络线程与 async 循环的桥接
    msg_queue: "queue.Queue" = queue.Queue(maxsize=100_000)
    stats = ConsumerStats()

    stop_event = asyncio.Event()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT 已连接，订阅 data/control/status/ack")
            client.subscribe([(data_topic, 1), (control_topic, 1), (status_topic, 1), (ack_topic, 1)])
        else:
            logger.error("MQTT 连接失败 rc=%s", rc)

    def on_message(client, userdata, msg):
        try:
            msg_queue.put_nowait(msg)
        except queue.Full:
            stats.failed += 1
            logger.error("QUEUE_FULL 丢弃一条消息")

    client = mqtt.Client(client_id=settings.MQTT_CONSUMER_CLIENT_ID, clean_session=False, manual_ack=True)
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.max_inflight_messages_set(200)
    client.max_queued_messages_set(10_000)

    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
    client.loop_start()

    loop = asyncio.get_running_loop()

    def request_stop():
        logger.info("收到停止信号，正在退出…")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass

    started = time.time()
    last_log = time.time()
    try:
        async with AsyncSessionLocal() as session:
            consumer = asyncio.create_task(_process_message(session, msg_queue, stats, client))
            while not stop_event.is_set():
                await asyncio.sleep(1)
                # A separate session prevents concurrent use of the ingestion
                # session, and reuses this consumer rather than adding workers.
                try:
                    async with AsyncSessionLocal() as retry_session:
                        await command_delivery.retry_due_commands(retry_session)
                except Exception:
                    logger.exception("COMMAND_RETRY_FAILED")
                if time.time() - last_log >= 5:
                    last_log = time.time()
                    snap = stats.snapshot()
                    logger.info(
                        "STATS received=%d inserted=%d controls=%d/%d duplicate=%d failed=%d",
                        snap["received"], snap["inserted"], snap["control_started"],
                        snap["control_completed"], snap["duplicate"] + snap["control_duplicate"], snap["failed"],
                    )
            consumer.cancel()
            try:
                await consumer
            except asyncio.CancelledError:
                pass
    finally:
        client.loop_stop()
        client.disconnect()

    elapsed = time.time() - started
    snap = stats.snapshot()
    logger.info("Consumer 结束，最终统计：%s", snap)
    logger.info("Elapsed: %.2f s", elapsed)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
