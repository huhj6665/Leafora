"""Downlink-driven normative virtual Jetson for protocol V2.0."""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from scripts.mock_jetson.config import MockConfig
from scripts.mock_jetson.field_route import build_route
from scripts.mock_jetson.generators import DataBuilder
from scripts.mock_jetson.http_client import ImageUploader
from scripts.mock_jetson.mqtt import MQTTSession
from scripts.mock_jetson.outbox import OutboxItem, PersistentOutbox

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class SimulatorState(str, Enum):
    STANDBY = "STANDBY"
    RUNNING = "RUNNING"
    SYNCING = "SYNCING"
    COMPLETED = "COMPLETED"


@dataclass
class SimulationStats:
    inspection_id: str
    samples: int = 0
    mqtt_published: int = 0
    images_attempted: int = 0
    images_uploaded: int = 0
    disease_samples: int = 0
    cloud_completed: int = 0
    failed: int = 0


class ImageCatalog:
    def __init__(self, config: MockConfig) -> None:
        self.disease = self._files(config.disease_images_dir) or self._files(config.test_images_dir)
        self.normal = self._files(config.normal_images_dir) or self._files(config.test_images_dir)

    @staticmethod
    def _files(directory: str) -> list[Path]:
        path = Path(directory)
        return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS) if path.is_dir() else []

    def select(self, has_disease: bool, index: int) -> Path | None:
        items = self.disease if has_disease else self.normal
        return items[index % len(items)] if items else None


class VirtualJetsonSimulator:
    """A deterministic device that never creates cloud tasks on its own."""

    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.state = SimulatorState.STANDBY
        self.builder = DataBuilder(config)
        self.images = ImageCatalog(config)
        self.uploader = ImageUploader(config)
        self.active: dict | None = None
        self.route: list[dict] = []
        self.index = 0
        self.ack_cache: dict[str, dict] = {}
        self.final_ack_cache: dict[str, dict] = {}
        self.end_command: dict | None = None
        self.network_pause_until = 0.0
        self.blocked_images: set[str] = set()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _ack(self, command: dict, status: str, phase: str, reason: str | None = None) -> dict:
        return {
            "type": "command_ack", "schema_version": "2.0",
            "command_id": command.get("command_id"), "inspection_id": command.get("inspection_id"),
            "device_id": self.config.device_id, "command": command.get("command"),
            "status": status, "phase": phase, "reason_code": reason, "timestamp": self._now(),
        }

    def accept_command(self, command: dict, pending_sync_count: int = 0) -> dict:
        command_id = str(command.get("command_id") or "")
        if command_id in self.ack_cache:
            return self.ack_cache[command_id]
        expired = False
        if command.get("expires_at"):
            try:
                expires = datetime.fromisoformat(command["expires_at"].replace("Z", "+00:00"))
                expired = expires.replace(tzinfo=expires.tzinfo or timezone.utc) <= datetime.now(timezone.utc)
            except (ValueError, TypeError):
                expired = True
        if expired:
            ack = self._ack(command, "REJECTED", self.state.value, "COMMAND_EXPIRED")
        elif command.get("type") != "inspection_command" or command.get("device_id") != self.config.device_id:
            ack = self._ack(command, "REJECTED", self.state.value, "INVALID_COMMAND")
        elif command.get("command") == "START_INSPECTION":
            snapshot = command.get("field_snapshot") or {}
            if self.state != SimulatorState.STANDBY:
                ack = self._ack(command, "REJECTED", self.state.value, "DEVICE_BUSY")
            elif not snapshot.get("pixel_boundary") or not snapshot.get("transform_params"):
                ack = self._ack(command, "REJECTED", self.state.value, "FIELD_SNAPSHOT_MISSING")
            elif snapshot.get("field_id") != command.get("field_id") or snapshot.get("version") != command.get("field_version"):
                ack = self._ack(command, "REJECTED", self.state.value, "FIELD_VERSION_MISMATCH")
            else:
                mode = command.get("run_mode") or "FAST_TEST"
                sample_count = 1800 if mode == "REALTIME_SIMULATION" else 90
                self.active = command
                self.route = build_route(snapshot, sample_count)
                self.index = 0
                self.end_command = None
                first, last = self.route[0], self.route[-1]
                self.config.start_lat, self.config.start_lon = first["latitude"], first["longitude"]
                self.config.end_lat, self.config.end_lon = last["latitude"], last["longitude"]
                self.config.sample_interval = 0.5 if mode == "REALTIME_SIMULATION" else 1.0
                self.builder = DataBuilder(self.config)
                self.state = SimulatorState.RUNNING
                ack = self._ack(command, "ACCEPTED", "RUNNING")
        elif command.get("command") == "END_INSPECTION":
            if not self.active or command.get("inspection_id") != self.active.get("inspection_id"):
                ack = self._ack(command, "REJECTED", self.state.value, "TASK_NOT_RUNNING")
            elif self.state not in {SimulatorState.RUNNING, SimulatorState.SYNCING}:
                ack = self._ack(command, "REJECTED", self.state.value, "INVALID_STATE")
            else:
                self.state = SimulatorState.SYNCING
                self.end_command = command
                ack = self._ack(command, "ACCEPTED", "SYNCING")
                ack["summary"] = {
                    "sampling_stopped": True, "sample_count": self.index,
                    "last_data_id": f"DATA_{self.active['inspection_id']}_{self.index - 1:06d}" if self.index else None,
                    "last_sequence": self.index - 1 if self.index else None,
                    "pending_sync_count": pending_sync_count,
                }
        else:
            ack = self._ack(command, "REJECTED", self.state.value, "UNKNOWN_COMMAND")
        self.ack_cache[command_id] = ack
        return ack

    def _checkpoint(self, outbox: PersistentOutbox, items=()) -> None:
        outbox.checkpoint(self.config.device_id, {
            "active": self.active, "state": self.state.value, "index": self.index,
            "ack_cache": self.ack_cache, "final_ack_cache": self.final_ack_cache,
            "end_command": self.end_command,
        }, items)

    def _restore(self, outbox: PersistentOutbox) -> None:
        saved = outbox.load_checkpoint(self.config.device_id)
        if saved is None:
            if outbox.business_count():
                raise RuntimeError("Legacy outbox lacks task checkpoint; preserve it and resolve before starting new tasks")
            return
        self.active, self.index = saved["active"], saved["index"]
        self.state = SimulatorState(saved["state"])
        self.ack_cache = saved.get("ack_cache", {})
        self.final_ack_cache = saved.get("final_ack_cache", {})
        self.end_command = saved.get("end_command")
        if self.active:
            mode = self.active.get("run_mode") or "FAST_TEST"
            self.route = build_route(self.active["field_snapshot"], 1800 if mode == "REALTIME_SIMULATION" else 90)
            first, last = self.route[0], self.route[-1]
            self.config.start_lat, self.config.start_lon = first["latitude"], first["longitude"]
            self.config.end_lat, self.config.end_lon = last["latitude"], last["longitude"]
            self.config.sample_interval = .5 if mode == "REALTIME_SIMULATION" else 1.0
            self.builder = DataBuilder(self.config)

    @staticmethod
    def _ack_item(ack):
        # Two phases have different local outbox keys, identical wire command IDs.
        return OutboxItem("ack", f"{ack['command_id']}:{ack['status']}", ack)

    def _finish_end(self, outbox: PersistentOutbox) -> bool:
        if (self.state != SimulatorState.SYNCING or not self.active or not self.end_command
                or outbox.business_count(self.active["inspection_id"])):
            return False
        accepted = self.ack_cache[self.end_command["command_id"]]
        final = self._ack(self.end_command, "COMPLETED", "COMPLETED")
        final["summary"] = {**accepted["summary"], "pending_sync_count": 0}
        self.final_ack_cache[final["command_id"]] = final
        self.state, self.active = SimulatorState.STANDBY, None
        self._checkpoint(outbox, [self._ack_item(accepted), self._ack_item(final)])
        return True

    def _requeue_end_receipts(self, outbox: PersistentOutbox) -> None:
        if self.end_command:
            command_id = self.end_command["command_id"]
            items = [self._ack_item(self.ack_cache[command_id])]
            if command_id in self.final_ack_cache:
                items.append(self._ack_item(self.final_ack_cache[command_id]))
            self._checkpoint(outbox, items)

    def next_sample(self):
        if self.state != SimulatorState.RUNNING or not self.active or self.index >= len(self.route):
            return None
        timestamp = self._now()
        data_id = f"DATA_{self.active['inspection_id']}_{self.index:06d}"
        built = self.builder.build(
            self.active["inspection_id"], self.index, len(self.route), timestamp,
            data_id=data_id, task=self.active, route_point=self.route[self.index],
        )
        self.index += 1
        return built

    def _status(self, pending: int = 0) -> dict:
        return {
            "type": "device_status", "device_id": self.config.device_id, "timestamp": self._now(),
            "operating_status": "RUNNING" if self.state == SimulatorState.RUNNING else "SHUTDOWN",
            "communication_status": "ONLINE", "sync_status": "PENDING" if pending else "SYNCED" if self.end_command else "IDLE",
            "pending_sync_count": pending,
            "inspection_id": (self.active or self.end_command or {}).get("inspection_id"),
            "gps_fix": "GPS_FIX", "rtk_status": "RTK_FIXED",
            "camera_status": "READY", "inference_status": "READY",
            "storage_usage": 28.0,
        }

    def _prepare_image(self, built) -> OutboxItem | None:
        source = self.images.select(built.has_disease, self.index - 1)
        if source is None:
            return
        image_id = f"IMG_{built.payload['data_id']}"
        temp_dir = Path(self.config.outbox_path).parent / "images"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temporary = temp_dir / f"{image_id}{source.suffix.lower()}"
        if not temporary.exists():
            shutil.copy2(source, temporary)
        return OutboxItem("image", image_id, {
            "data_id": built.payload["data_id"], "image_id": image_id,
            "path": str(temporary), "inspection_id": built.payload["inspection_id"],
            "timestamp": built.payload["timestamp"],
        })

    def _flush(self, session: MQTTSession, outbox: PersistentOutbox) -> None:
        for item in outbox.items():
            if item.kind == "data" and session.publish_data(item.payload):
                outbox.acknowledge(item.kind, item.business_id)
            elif item.kind == "ack" and session.publish_ack(item.payload):
                outbox.acknowledge(item.kind, item.business_id)
            elif item.kind == "image":
                if item.business_id in self.blocked_images:
                    continue
                path = Path(item.payload["path"])
                if path.is_file():
                    result = self.uploader.upload(
                        item.payload["data_id"], item.payload["image_id"], path,
                        inspection_id=item.payload["inspection_id"], timestamp=item.payload["timestamp"],
                    )
                    if result["http_status"] == 200:
                        outbox.acknowledge(item.kind, item.business_id)
                        path.unlink(missing_ok=True)
                    elif 400 <= result["http_status"] < 500 and result["http_status"] != 404:
                        # Authentication/schema/binding conflicts do not recover
                        # through rapid retries.  Keep the local file + outbox row
                        # for diagnosis/restart, but stop hammering the backend.
                        self.blocked_images.add(item.business_id)

    def serve(self) -> None:
        next_sample_at = time.monotonic()
        next_heartbeat_at = time.monotonic()
        next_flush_at = time.monotonic()
        with PersistentOutbox(self.config.outbox_path) as outbox:
            self._restore(outbox)
            self._serve_restored(outbox, next_sample_at, next_heartbeat_at, next_flush_at)

    def _serve_restored(self, outbox, next_sample_at, next_heartbeat_at, next_flush_at):
        def pending():
            return outbox.business_count(self.active["inspection_id"] if self.active else None)

        with MQTTSession(self.config) as session:
            self._requeue_end_receipts(outbox)
            session.publish_status(self._status(pending()))
            try:
                while True:
                    now = time.monotonic()
                    if now >= next_heartbeat_at:
                        self._requeue_end_receipts(outbox)
                        session.publish_status(self._status(pending()))
                        next_heartbeat_at = now + 3.0
                    message = session.next_downlink(timeout=0.1)
                    if message and message.get("type") == "inspection_command":
                        ack = self.accept_command(message, pending())
                        items = [self._ack_item(ack)]
                        if ack["command_id"] in self.final_ack_cache:
                            items.append(self._ack_item(self.final_ack_cache[ack["command_id"]]))
                        self._checkpoint(outbox, items)
                    if self.state == SimulatorState.RUNNING and time.monotonic() >= next_sample_at:
                        built = self.next_sample()
                        if built is not None:
                            # Persist every sample (including images) and cursor
                            # before publishing. A restart cannot lose or recount it.
                            items = [OutboxItem("data", built.payload["data_id"], built.payload)]
                            if built.has_disease:
                                image = self._prepare_image(built)
                                if image:
                                    items.append(image)
                            self._checkpoint(outbox, items)
                            simulated_jitter = self.index % 37 == 0
                            if simulated_jitter:
                                self.network_pause_until = time.monotonic() + 2.0
                            session.publish_status(self._status(pending()))
                        next_sample_at = time.monotonic() + self.config.sample_interval
                    if time.monotonic() >= self.network_pause_until and time.monotonic() >= next_flush_at:
                        self._flush(session, outbox)
                        if self._finish_end(outbox):
                            self._flush(session, outbox)
                            session.publish_status(self._status(pending()))
                        next_flush_at = time.monotonic() + 3.0
            except KeyboardInterrupt:
                session.publish_status({**self._status(pending()), "communication_status": "OFFLINE"})

    def run(self, mode: str = "fast", samples: int | None = None, upload_images: bool = True,
            dry_run: bool = False, bind_owner: bool = False, inspection_id: str | None = None) -> SimulationStats:
        if not dry_run:
            self.serve()
            return SimulationStats(inspection_id="")
        inspection_id = inspection_id or "INS_DRY_PREVIEW"
        sample_count = max(2, samples or 5)
        snapshot = {
            "field_id": "FIELD_A01", "version": 1,
            "pixel_boundary": [[126, 517], [221, 466], [489, 489], [522, 531], [1002, 578], [1121, 1094], [144, 1096], [126, 517]],
            "transform_params": {"image_width": 1600, "image_height": 1105, "origin_longitude": 113.123,
                                 "origin_latitude": 23.4565, "longitude_per_pixel": 0.000001,
                                 "latitude_per_pixel": -0.0000008},
        }
        command = {"type": "inspection_command", "command_id": "CMD_DRY_START", "command": "START_INSPECTION",
                   "inspection_id": inspection_id, "device_id": self.config.device_id, "field_id": "FIELD_A01",
                   "field_version": 1, "field_snapshot": snapshot, "run_mode": "FAST_TEST"}
        print(json.dumps({"dry_run_input": "cloud downlink", "command": "START", "request_id": "REQ_COMPAT_PREVIEW"}, ensure_ascii=False))
        print(json.dumps(self.accept_command(command), ensure_ascii=False))
        self.route = build_route(snapshot, sample_count)
        stats = SimulationStats(inspection_id)
        while self.index < len(self.route):
            built = self.next_sample()
            if built:
                stats.samples += 1
                stats.mqtt_published += 1
                stats.disease_samples += int(built.has_disease)
                if stats.samples <= 3 or stats.samples == len(self.route):
                    print(json.dumps(built.payload, ensure_ascii=False))
        end = {"type": "inspection_command", "command_id": "CMD_DRY_END", "command": "END_INSPECTION",
               "inspection_id": inspection_id, "device_id": self.config.device_id}
        print(json.dumps({"dry_run_input": "cloud downlink", "command": "END"}, ensure_ascii=False))
        print(json.dumps(self.accept_command(end), ensure_ascii=False))
        self.state = SimulatorState.COMPLETED
        return stats
