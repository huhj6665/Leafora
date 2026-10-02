"""Exercise RUNNING_OFFLINE caching and idempotent recovery against local cloud."""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.mock_jetson.config import load_config
from scripts.mock_jetson.generators import DataBuilder
from scripts.mock_jetson.mqtt import MQTTSession
from scripts.mock_jetson.outbox import PersistentOutbox
from scripts.mock_jetson.simulator import VirtualJetsonSimulator

WEB_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTBOX = WEB_ROOT / "local" / "mock_jetson" / "outbox.sqlite3"


def run(sample_count: int, outbox_path: Path) -> dict:
    config = load_config()
    inspection_id = VirtualJetsonSimulator.new_inspection_id()
    started = datetime.now(timezone.utc)
    start_request_id = f"REQ_{uuid.uuid4().hex}"
    end_request_id = f"REQ_{uuid.uuid4().hex}"

    start_payload = {
        "type": "inspection_control",
        "schema_version": "1.1",
        "request_id": start_request_id,
        "command": "START",
        "inspection_id": inspection_id,
        "device_id": config.device_id,
        "timestamp": started.isoformat().replace("+00:00", "Z"),
        "name": f"{config.device_name} 离线恢复验收",
    }
    with MQTTSession(config) as session:
        if not session.publish_control(start_payload):
            raise RuntimeError("START 发布失败")
        ack = session.wait_control_ack(start_request_id)
        if not ack or ack.get("status") != "ACCEPTED":
            raise RuntimeError("START ACK 未收到，拒绝进入离线运行")

    builder = DataBuilder(config)
    with PersistentOutbox(outbox_path) as outbox:
        for index in range(sample_count):
            captured = started + timedelta(seconds=index * config.sample_interval)
            timestamp = captured.isoformat().replace("+00:00", "Z")
            data_id = f"DATA_OFFLINE_{uuid.uuid4().hex}"
            payload = builder.build(
                inspection_id, index, sample_count, timestamp, data_id=data_id
            ).payload
            outbox.enqueue("data", data_id, payload)

        ended = started + timedelta(seconds=(sample_count - 1) * config.sample_interval)
        end_payload = {
            "type": "inspection_control",
            "schema_version": "1.1",
            "request_id": end_request_id,
            "command": "END",
            "inspection_id": inspection_id,
            "device_id": config.device_id,
            "timestamp": ended.isoformat().replace("+00:00", "Z"),
            "pending_sync_count": sample_count,
        }
        outbox.enqueue("control", end_request_id, end_payload)
        cached_count = outbox.count()

        duplicate_retry_sent = False
        with MQTTSession(config) as session:
            session.publish_status(
                {
                    "type": "device_status",
                    "device_id": config.device_id,
                    "inspection_id": inspection_id,
                    "operating_status": "RUNNING",
                    "communication_status": "ONLINE",
                    "sync_status": "PENDING",
                    "pending_sync_count": cached_count,
                }
            )
            for item in outbox.items():
                if item.kind == "data":
                    published = session.publish_data(item.payload)
                    if published and not duplicate_retry_sent:
                        # Simulate a lost local acknowledgement: retry the exact same
                        # business object without allocating a new data_id.
                        published = session.publish_data(item.payload)
                        duplicate_retry_sent = True
                else:
                    published = session.publish_control(item.payload)
                    if published:
                        control_ack = session.wait_control_ack(item.business_id)
                        published = bool(control_ack and control_ack.get("status") == "ACCEPTED")
                if not published:
                    raise RuntimeError(f"补传失败，项目保留在 outbox：{item.kind}/{item.business_id}")
                outbox.acknowledge(item.kind, item.business_id)

            session.publish_status(
                {
                    "type": "device_status",
                    "device_id": config.device_id,
                    "inspection_id": inspection_id,
                    "operating_status": "SHUTDOWN",
                    "communication_status": "ONLINE",
                    "sync_status": "SYNCED",
                    "pending_sync_count": 0,
                }
            )
        remaining = outbox.count()

    return {
        "inspection_id": inspection_id,
        "cached_count": cached_count,
        "remaining_count": remaining,
        "duplicate_retry_sent": duplicate_retry_sent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="虚拟设备断网缓存与幂等补传验收")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--outbox", type=Path, default=DEFAULT_OUTBOX)
    args = parser.parse_args()
    result = run(max(2, args.samples), args.outbox)
    print("=== Offline Recovery Summary ===")
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0 if result["remaining_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
