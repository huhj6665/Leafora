"""Best-effort MQTT downlink publisher.

Publishing failures never roll back an already committed database transaction.
"""
import asyncio
import json
import logging
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger("app.mqtt_publisher")


def _publish_sync(device_id: str, payload: dict) -> bool:
    client = None
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(client_id=f"tld-cloud-{uuid4().hex[:12]}", protocol=mqtt.MQTTv311)
        client.connect_timeout = 5
        if settings.MQTT_USERNAME:
            client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=30)
        client.loop_start()
        topic = f"{settings.MQTT_TOPIC_PREFIX}/device/{device_id}/downlink"
        info = client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=False)
        info.wait_for_publish(timeout=5)
        ok = bool(info.is_published())
        return ok
    except Exception as exc:  # best effort by design
        logger.warning("MQTT_DOWNLINK_FAILED device_id=%s error=%s", device_id, type(exc).__name__)
        return False
    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                logger.warning("MQTT_DISCONNECT_FAILED device_id=%s", device_id)
            try:
                client.loop_stop()
            except Exception:
                logger.warning("MQTT_LOOP_STOP_FAILED device_id=%s", device_id)


async def publish_downlink(device_id: str, payload: dict) -> bool:
    if settings.APP_ENV == "test":
        return False
    return await asyncio.to_thread(_publish_sync, device_id, payload)
