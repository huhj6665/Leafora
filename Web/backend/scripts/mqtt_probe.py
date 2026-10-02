"""Read-only MQTT authentication probe used by LAN diagnostics."""
from __future__ import annotations

import argparse
import threading

from app.core.config import settings


def probe(
    host: str,
    port: int,
    timeout: float = 5.0,
    username: str | None = None,
    password: str | None = None,
) -> tuple[int, str]:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return 2, "MQTT_CLIENT_MISSING"

    connected = threading.Event()
    result: dict[str, int | None] = {"rc": None}

    def on_connect(client, userdata, flags, reason_code, properties):
        result["rc"] = int(reason_code.value)
        connected.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="tld-lan-diagnostic",
        protocol=mqtt.MQTTv311,
    )
    if username:
        client.username_pw_set(username, password or "")
    client.on_connect = on_connect
    try:
        client.connect(host, port, keepalive=10)
        client.loop_start()
        if not connected.wait(timeout):
            return 2, "MQTT_CONNECT_TIMEOUT"
        rc = result["rc"]
        if rc == 0:
            return 0, "MQTT_AUTH_OK"
        if rc in {4, 5, 134, 135}:
            return 3, "MQTT_AUTH_FAILED"
        return 2, f"MQTT_CONNECT_FAILED_RC_{rc}"
    except OSError:
        return 2, "MQTT_PORT_UNREACHABLE"
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="安全检查 MQTT 连接与认证，不发布消息")
    parser.add_argument("--host", default=settings.MQTT_HOST)
    parser.add_argument("--port", type=int, default=settings.MQTT_PORT)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--anonymous",
        action="store_true",
        help="不发送账号密码，用于确认 Broker 拒绝匿名连接",
    )
    args = parser.parse_args()
    username = None if args.anonymous else settings.MQTT_USERNAME
    password = None if args.anonymous else settings.MQTT_PASSWORD
    code, message = probe(args.host, args.port, args.timeout, username, password)
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
