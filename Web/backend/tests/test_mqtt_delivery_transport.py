"""No live broker: transport cleanup and DB-before-PUBACK checks."""
import asyncio
import json
import queue
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.services import mqtt_publisher
from app.services.inspection_service import IngestResult
from workers import mqtt_consumer


@pytest.mark.parametrize("success", [False, True])
def test_publish_timeout_always_closes_network_loop(monkeypatch, success):
    import paho.mqtt.client as mqtt
    calls = []

    class Message:
        def wait_for_publish(self, timeout):
            if not success:
                raise TimeoutError("test timeout")

        def is_published(self):
            return success

    class Client:
        def __init__(self, **kwargs):
            pass

        def username_pw_set(self, *args):
            pass

        def connect(self, *args, **kwargs):
            calls.append("connect")

        def loop_start(self):
            calls.append("loop_start")

        def publish(self, *args, **kwargs):
            assert kwargs["qos"] == 1 and kwargs["retain"] is False
            return Message()

        def disconnect(self):
            calls.append("disconnect")

        def loop_stop(self):
            calls.append("loop_stop")

    monkeypatch.setattr(mqtt, "Client", Client)
    assert mqtt_publisher._publish_sync("TLD_SIM_002", {"command_id": "CMD_FIXED"}) is success
    assert calls[-2:] == ["disconnect", "loop_stop"]


async def test_consumer_retries_db_failure_before_confirming_broker_delivery(monkeypatch):
    calls = []
    confirmed = asyncio.Event()

    class Session:
        async def rollback(self):
            calls.append("rollback")

    class Client:
        def ack(self, mid, qos):
            assert (mid, qos) == (42, 1)
            calls.append("broker_ack")
            confirmed.set()

    attempts = 0

    async def ingest(session, payload, topic):
        nonlocal attempts
        attempts += 1
        assert payload["data_id"] == "DATA_FIXED"
        if attempts == 1:
            raise OperationalError("test", {}, RuntimeError("temporarily unavailable"))
        calls.append("db_commit")
        return IngestResult(status="inserted", device_id="TLD_SIM_002", data_id="DATA_FIXED")

    monkeypatch.setattr(mqtt_consumer.inspection_service, "ingest_message", ingest)
    messages = queue.Queue()
    messages.put(SimpleNamespace(topic="tld/device/TLD_SIM_002/data", mid=42, qos=1,
                                 payload=json.dumps({"data_id": "DATA_FIXED"}).encode()))
    stats = mqtt_consumer.ConsumerStats()
    worker = asyncio.create_task(mqtt_consumer._process_message(Session(), messages, stats, Client()))
    try:
        await asyncio.wait_for(confirmed.wait(), 4)
    finally:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
    assert attempts == 2
    assert calls.index("db_commit") < calls.index("broker_ack")
    assert stats.received == 1 and stats.inserted == 1
