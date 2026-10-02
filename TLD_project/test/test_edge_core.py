# -*- coding: utf-8 -*-
"""不依赖 Jetson 硬件的边缘端核心测试。"""

import json
import errno
import logging
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib import error

from main import build_parser
from edge.cli import run_cli
from edge.config import DeviceConfig, LocalConfigStore
from edge.data_manager import DataManager
from edge.http_client import DeviceHttpClient, HttpClientError
from edge.latest import LatestValueCache
from edge.lifecycle import LifecycleController
from edge.logging_utils import RedactingFilter
from edge.network_config import (
    NetworkConfigError,
    build_backend_url,
    diagnose_http_health,
    diagnose_mqtt,
    ensure_network_change_allowed,
    network_form_values,
    normalize_remote_host,
)
from edge.protocol import Topics
from edge.runtime import EdgeRuntime
from edge.state import DeviceState, InvalidTransition, StateMachine
from edge.store import PersistentStore
from edge.upload_worker import ImageUploadWorker


class QuietLogger(object):
    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass

    def critical(self, message):
        pass


class ConfigStub(object):
    def __init__(self, state_dir):
        self.device_id = "TLD_SIM_002"
        self.state_dir = state_dir
        self.min_free_disk_mb = 1
        self.start_retries = 2
        self.start_ack_timeout_s = 0.02
        self.qr_dir = state_dir
        self.allow_legacy_control = True


class HardwareStub(object):
    def health(self):
        return {
            "camera": True,
            "yolo": True,
            "location": {"fix": "GPS Fix", "latitude": 34.0, "longitude": 110.0},
            "sensors": {"light": False, "air": True},
        }


class MqttStub(object):
    def __init__(self, acknowledge=True):
        self.connected = True
        self.topics = Topics("TLD_SIM_002")
        self.callbacks = []
        self.payloads = []
        self.acknowledge = acknowledge

    def add_downlink_callback(self, callback):
        self.callbacks.append(callback)

    def publish(self, topic, payload, retain=False):
        self.payloads.append(dict(payload))
        if self.acknowledge and payload.get("type") == "inspection_control" and payload.get("command") == "START":
            ack = {
                "type": "control_ack",
                "request_id": payload["request_id"],
                "inspection_id": payload["inspection_id"],
                "command": "START",
                "status": "ACCEPTED",
            }
            for callback in self.callbacks:
                callback(ack)
        return True


class HttpStub(object):
    pass


class ConfigTests(unittest.TestCase):
    def test_local_config_round_trip_and_default_device(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "device.env")
            store = LocalConfigStore(path)
            store.save({"NTRIP_USERNAME": "user", "NTRIP_PASSWORD": "secret"})
            values = store.load()
            self.assertEqual(values["NTRIP_USERNAME"], "user")
            self.assertEqual(values["NTRIP_PASSWORD"], "secret")
            config = DeviceConfig.load(directory, path, environ={})
            self.assertEqual(config.device_id, "TLD_SIM_002")
            store.save({"NTRIP_ENABLED": "false"}, clear_keys=["NTRIP_PASSWORD"])
            self.assertNotIn("NTRIP_PASSWORD", store.load())

    def test_local_config_escaping_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "device.env")
            value = "a=b\\c"
            LocalConfigStore(path).save({"NTRIP_PASSWORD": value})
            self.assertEqual(LocalConfigStore(path).load()["NTRIP_PASSWORD"], value)

    def test_cloud_settings_are_not_source_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config = DeviceConfig.load(directory, os.path.join(directory, "none.env"), environ={})
            self.assertEqual(config.backend_url, "")
            self.assertEqual(config.mqtt_host, "")
            self.assertEqual(config.device_secret, "")

    def test_atomic_network_update_preserves_unrelated_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "device.env")
            store = LocalConfigStore(path)
            original = {
                "DEVICE_ID": "TLD_SIM_002",
                "DEVICE_SECRET": "device-secret",
                "MQTT_PASSWORD": "mqtt-secret",
                "NTRIP_PASSWORD": "ntrip-secret",
                "CAMERA_DEVICE": "/dev/video0",
            }
            store.save(original)
            store.save({
                "BACKEND_URL": "http://192.168.10.20:8000",
                "MQTT_HOST": "192.168.10.20",
                "MQTT_PORT": "1883",
            })
            values = store.load()
            for key, value in original.items():
                self.assertEqual(values[key], value)

    def test_failed_replace_keeps_original_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "device.env")
            store = LocalConfigStore(path)
            store.save({"DEVICE_ID": "TLD_SIM_002", "MQTT_HOST": "old-host"})
            with mock.patch("edge.config.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    store.save({"MQTT_HOST": "new-host"})
            self.assertEqual(store.load()["MQTT_HOST"], "old-host")
            self.assertFalse(os.path.exists(path + ".tmp"))


class NetworkConfigTests(unittest.TestCase):
    def test_network_unreachable_is_distinct_from_auth_and_port_refused(self):
        def unreachable_opener(req, timeout):
            raise error.URLError(OSError(errno.ENETUNREACH, "fixture"))
        def unreachable_tcp(host, port, timeout):
            raise OSError(errno.EHOSTUNREACH, "fixture")
        def unauthorized(req, timeout):
            raise error.HTTPError(req.full_url, 403, "fixture", None, None)
        self.assertEqual(diagnose_http_health("http://192.168.1.8:8000", opener=unreachable_opener)["category"], "network_unreachable")
        self.assertEqual(diagnose_http_health("http://192.168.1.8:8000", opener=unauthorized)["category"], "auth_failed")
        self.assertEqual(diagnose_mqtt("192.168.1.8", 18883, "", "", tcp_probe=unreachable_tcp)["category"], "network_unreachable")

    def test_remote_address_validation_and_url_generation(self):
        self.assertEqual(normalize_remote_host("192.168.1.8"), "192.168.1.8")
        self.assertEqual(normalize_remote_host("DEV-PC.local"), "dev-pc.local")
        self.assertEqual(build_backend_url("10.0.0.5", "8000"), "http://10.0.0.5:8000")
        for invalid in ("", "localhost", "127.0.0.1", "127.8.9.10", "0.0.0.0",
                        "http://192.168.1.8", "999.1.1.1"):
            with self.assertRaises(NetworkConfigError):
                normalize_remote_host(invalid)

    def test_complete_https_config_is_supported_and_password_is_masked(self):
        with tempfile.TemporaryDirectory() as directory:
            config = DeviceConfig({
                "BACKEND_URL": "https://api.example.com",
                "MQTT_HOST": "mqtt.example.com",
                "MQTT_PORT": "8883",
                "MQTT_USERNAME": "edge-user",
                "MQTT_PASSWORD": "never-render-this",
            }, directory, os.path.join(directory, "device.env"))
            rendered = json.dumps(network_form_values(config), ensure_ascii=False)
            self.assertIn("https://api.example.com", rendered)
            self.assertIn('"http_port": 443', rendered)
            self.assertNotIn("never-render-this", rendered)

    def test_http_diagnostics_report_success_timeout_and_refused(self):
        class Response(object):
            def getcode(self):
                return 200

            def read(self, size=None):
                return b'{"status":"ok"}'

            def close(self):
                pass

        success = diagnose_http_health(
            "http://192.168.1.8:8000", opener=lambda req, timeout: Response()
        )
        self.assertTrue(success["ok"])
        self.assertEqual(success["category"], "reachable")

        def timeout_opener(req, timeout):
            raise error.URLError(socket.timeout())

        def refused_opener(req, timeout):
            raise error.URLError(ConnectionRefusedError())

        self.assertEqual(
            diagnose_http_health("http://192.168.1.8:8000", opener=timeout_opener)["category"],
            "timeout",
        )
        self.assertEqual(
            diagnose_http_health("http://192.168.1.8:8000", opener=refused_opener)["category"],
            "refused",
        )

    def test_mqtt_auth_failure_is_classified_without_secret_output(self):
        class FakeClient(object):
            def __init__(self):
                self.on_connect = None
                self.on_connect_fail = None

            def username_pw_set(self, username, password):
                self.password = password

            def connect_async(self, host, port, keepalive):
                pass

            def loop_start(self):
                self.on_connect(self, None, {}, 4)

            def disconnect(self):
                pass

            def loop_stop(self):
                pass

        secret = "mqtt-password-must-not-leak"
        result = diagnose_mqtt(
            "192.168.1.8", 1883, "edge-user", secret,
            client_factory=lambda client_id: FakeClient(),
            tcp_probe=lambda host, port, timeout: None,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "auth_failed")
        self.assertEqual(result["connack"], 4)
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_network_switch_is_blocked_in_active_states(self):
        blocked = (
            DeviceState.STARTING, DeviceState.RUNNING, DeviceState.RUNNING_OFFLINE,
            DeviceState.ENDING, DeviceState.SYNCING,
        )
        for state in blocked:
            with self.assertRaises(NetworkConfigError):
                ensure_network_change_allowed(state)
        self.assertTrue(ensure_network_change_allowed(DeviceState.IDLE))
        self.assertTrue(ensure_network_change_allowed(DeviceState.UNBOUND))


class RuntimeNetworkTests(unittest.TestCase):
    def test_idle_save_rebuilds_clients_and_preserves_local_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "device.env")
            LocalConfigStore(config_path).save({
                "DEVICE_ID": "TLD_SIM_002",
                "DEVICE_SECRET": "device-secret",
                "MQTT_USERNAME": "edge-user",
                "MQTT_PASSWORD": "preseeded-password",
                "NTRIP_PASSWORD": "ntrip-secret",
                "CAMERA_DEVICE": "/dev/video0",
            })
            runtime = EdgeRuntime(directory, config_path=config_path)
            try:
                result = runtime.save_network(
                    "192.168.8.20", 8000, 1883, "edge-user", ""
                )
                self.assertTrue(result["saved"])
                self.assertTrue(result["reloaded"])
                self.assertNotIn("preseeded-password", json.dumps(result))
                values = LocalConfigStore(config_path).load()
                self.assertEqual(values["BACKEND_URL"], "http://192.168.8.20:8000")
                self.assertEqual(values["MQTT_PASSWORD"], "preseeded-password")
                self.assertEqual(values["DEVICE_SECRET"], "device-secret")
                self.assertEqual(values["NTRIP_PASSWORD"], "ntrip-secret")
                self.assertEqual(values["CAMERA_DEVICE"], "/dev/video0")
                self.assertIs(runtime.lifecycle.mqtt, runtime.mqtt)
                self.assertIs(runtime.lifecycle.http, runtime.http)
            finally:
                runtime.stop()

    def test_device_secret_can_be_saved_without_leaking_it(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "device.env")
            LocalConfigStore(config_path).save({
                "DEVICE_ID": "TLD_SIM_002",
                "BACKEND_URL": "http://192.168.8.20:8000",
                "MQTT_HOST": "192.168.8.20",
            })
            runtime = EdgeRuntime(directory, config_path=config_path)
            secret = "permanent-device-secret"
            try:
                result = runtime.save_device_secret(secret)
                self.assertTrue(result["saved"])
                self.assertTrue(result["device_secret_present"])
                self.assertNotIn(secret, json.dumps(result))
                values = LocalConfigStore(config_path).load()
                self.assertEqual(values["DEVICE_SECRET"], secret)
                self.assertTrue(runtime.credential_status()["device_secret_present"])
                self.assertIs(runtime.lifecycle.http, runtime.http)
            finally:
                runtime.stop()


class CommandLineEntryTests(unittest.TestCase):
    def test_default_entry_is_cli_without_hardware(self):
        args = build_parser().parse_args([])
        self.assertFalse(args.ui)
        self.assertFalse(args.hardware)

        class FakeRuntime(object):
            def __init__(self):
                self.start_hardware = None
                self.stopped = False

            def start(self, start_hardware=True):
                self.start_hardware = start_hardware

            def stop(self):
                self.stopped = True

        runtime = FakeRuntime()
        with mock.patch("builtins.input", return_value="0"):
            with mock.patch("edge.cli.startup_network_wizard", return_value=True):
                run_cli(runtime)
        self.assertFalse(runtime.start_hardware)
        self.assertTrue(runtime.stopped)


class ProtocolTests(unittest.TestCase):
    def test_topics(self):
        topics = Topics("TLD_SIM_002")
        self.assertEqual(topics.data, "tld/device/TLD_SIM_002/data")
        self.assertEqual(topics.control, "tld/device/TLD_SIM_002/control")
        self.assertEqual(topics.status, "tld/device/TLD_SIM_002/status")
        self.assertEqual(topics.downlink, "tld/device/TLD_SIM_002/downlink")
        self.assertEqual(topics.ack, "tld/device/TLD_SIM_002/ack")

    def test_pairing_qr_has_no_permanent_secret(self):
        client = DeviceHttpClient("http://host", "TLD_SIM_002", "permanent-secret")
        payload = client.pairing_payload("TLD_SIM_002", {
            "pairing_session_id": "PAIR_1",
            "pairing_token": "one-time",
            "expires_at": "2030-01-01T00:00:00Z",
        })
        rendered = json.dumps(payload)
        self.assertNotIn("permanent-secret", rendered)
        self.assertNotIn("device_secret", rendered)

    def test_log_filter_redacts_secrets_and_tokens(self):
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1,
            "password=abc token:xyz Authorization=BearerValue", (), None
        )
        RedactingFilter().filter(record)
        rendered = record.getMessage()
        self.assertNotIn("abc", rendered)
        self.assertNotIn("xyz", rendered)
        self.assertNotIn("BearerValue", rendered)


class StateAndDataTests(unittest.TestCase):
    def test_state_machine_rejects_invalid_transition(self):
        machine = StateMachine(DeviceState.UNBOUND)
        machine.transition(DeviceState.PAIRING)
        machine.transition(DeviceState.IDLE)
        with self.assertRaises(InvalidTransition):
            machine.transition(DeviceState.RUNNING)

    def test_data_manager_preserves_sensor_sample_time_and_nulls(self):
        cache = LatestValueCache()
        cache.update("location", {}, sampled_at="2026-01-01T00:00:00Z", valid=False)
        cache.update("environment", {
            "temperature": 20.5, "humidity": None, "co2": 410, "lux": None,
        }, sampled_at="2026-01-01T00:00:05Z", valid=True)
        cache.update("detection", [], sampled_at="2026-01-01T00:00:06Z", valid=True)
        cache.update("device_status", {}, valid=True)
        payload = DataManager("TLD_SIM_002", cache).build("INS_1", 7, data_id="DATA_1")
        self.assertEqual(payload["schema_version"], "1.3")
        self.assertIsNone(payload["location"]["latitude"])
        self.assertFalse(payload["location"]["position_valid"])
        self.assertEqual(payload["environment"]["sampled_at"], "2026-01-01T00:00:05Z")
        self.assertIsNone(payload["environment"]["humidity"])
        self.assertFalse(payload["environment"]["valid"])
        self.assertEqual(payload["sequence"], 7)


class StoreTests(unittest.TestCase):
    def test_message_and_image_ids_are_idempotent_and_image_waits_for_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue.db"))
            first = store.enqueue_message("data", "DATA_1", "topic", {"data_id": "DATA_1"})
            second = store.enqueue_message("data", "DATA_1", "topic", {"data_id": "DATA_1"})
            self.assertEqual(first, second)
            image_path = os.path.join(directory, "image.jpg")
            with open(image_path, "wb") as handle:
                handle.write(b"jpeg")
            store.enqueue_image("IMG_1", "INS_1", "DATA_1", "now", image_path)
            self.assertEqual(store.due_images(), [])
            store.mark_message_done(first)
            self.assertEqual(store.due_images()[0]["image_id"], "IMG_1")
            store.close()

    def test_completed_image_orphan_is_removed_on_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue.db"))
            message_id = store.enqueue_message("data", "DATA_1", "topic", {"data_id": "DATA_1"})
            store.mark_message_done(message_id)
            path = os.path.join(directory, "image.jpg")
            with open(path, "wb") as handle:
                handle.write(b"jpeg")
            image_row = store.enqueue_image("IMG_1", "INS_1", "DATA_1", "now", path)
            store.mark_image_done(image_row)
            self.assertEqual(store.cleanup_completed_image_files(), 1)
            self.assertFalse(os.path.exists(path))
            store.close()


class UploadTests(unittest.TestCase):
    def _prepare(self, directory):
        store = PersistentStore(os.path.join(directory, "queue.db"))
        message_id = store.enqueue_message("data", "DATA_1", "topic", {"data_id": "DATA_1"})
        store.mark_message_done(message_id)
        path = os.path.join(directory, "IMG_1.jpg")
        with open(path, "wb") as handle:
            handle.write(b"jpeg")
        store.enqueue_image("IMG_1", "INS_1", "DATA_1", "now", path)
        return store, path

    def test_success_marks_sqlite_then_deletes_file(self):
        class SuccessHttp(object):
            def upload_image(self, *args):
                return {"code": 0, "data": {"image_id": "IMG_1"}}
        with tempfile.TemporaryDirectory() as directory:
            store, path = self._prepare(directory)
            worker = ImageUploadWorker(store, SuccessHttp(), QuietLogger())
            worker.start()
            deadline = time.time() + 2.0
            while store.pending_counts()["images"] and time.time() < deadline:
                time.sleep(0.02)
            worker.stop()
            self.assertEqual(store.pending_counts()["images"], 0)
            self.assertFalse(os.path.exists(path))
            store.close()

    def test_uncertain_failure_keeps_file_and_queue(self):
        class FailureHttp(object):
            def upload_image(self, *args):
                raise RuntimeError("uncertain")
        with tempfile.TemporaryDirectory() as directory:
            store, path = self._prepare(directory)
            worker = ImageUploadWorker(store, FailureHttp(), QuietLogger())
            worker.start()
            time.sleep(0.15)
            worker.stop()
            self.assertEqual(store.pending_counts()["images"], 1)
            self.assertTrue(os.path.exists(path))
            store.close()

    def test_http_requires_code_zero_and_matching_image_id(self):
        class Client(DeviceHttpClient):
            def _call(self, method, path, body=None, content_type=None):
                return {"code": 0, "data": {"image_id": "OTHER"}}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "x.jpg")
            with open(path, "wb") as handle:
                handle.write(b"jpeg")
            client = Client("http://host", "TLD_SIM_002", "secret")
            with self.assertRaises(HttpClientError):
                client.upload_image("IMG_1", "INS_1", "DATA_1", "now", path)

    def test_http_accepts_idempotent_success_with_same_image_id(self):
        class Client(DeviceHttpClient):
            def _call(self, method, path, body=None, content_type=None):
                return {"code": 0, "data": {
                    "image_id": "IMG_1", "already_uploaded": True,
                }}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "x.jpg")
            with open(path, "wb") as handle:
                handle.write(b"jpeg")
            client = Client("http://host", "TLD_SIM_002", "secret")
            response = client.upload_image("IMG_1", "INS_1", "DATA_1", "now", path)
            self.assertTrue(response["data"]["already_uploaded"])


class LifecycleTests(unittest.TestCase):
    def test_start_enters_running_only_after_matching_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue.db"))
            store.set_meta("bound", True)
            mqtt = MqttStub(acknowledge=True)
            lifecycle = LifecycleController(
                ConfigStub(directory), store, mqtt, HttpStub(), HardwareStub(), QuietLogger()
            )
            active = lifecycle.start_inspection("test", "local note")
            self.assertEqual(lifecycle.state.state, DeviceState.RUNNING)
            self.assertEqual(active["phase"], "RUNNING")
            controls = [item for item in mqtt.payloads if item.get("command") == "START"]
            self.assertTrue(controls)
            self.assertEqual(controls[0]["inspection_id"], active["inspection_id"])
            store.close()

    def test_start_retries_reuse_request_and_inspection_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue.db"))
            store.set_meta("bound", True)
            mqtt = MqttStub(acknowledge=False)
            lifecycle = LifecycleController(
                ConfigStub(directory), store, mqtt, HttpStub(), HardwareStub(), QuietLogger()
            )
            with self.assertRaises(RuntimeError):
                lifecycle.start_inspection("test", "")
            controls = [item for item in mqtt.payloads if item.get("command") == "START"]
            self.assertEqual(len(controls), 2)
            self.assertEqual(len(set(item["request_id"] for item in controls)), 1)
            self.assertEqual(len(set(item["inspection_id"] for item in controls)), 1)
            self.assertEqual(lifecycle.state.state, DeviceState.ERROR)
            store.close()

    def test_running_network_loss_and_offline_end_are_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue.db"))
            store.set_meta("bound", True)
            mqtt = MqttStub(acknowledge=True)
            lifecycle = LifecycleController(
                ConfigStub(directory), store, mqtt, HttpStub(), HardwareStub(), QuietLogger()
            )
            lifecycle.start_inspection("test", "")
            mqtt.connected = False
            lifecycle.network_tick()
            self.assertEqual(lifecycle.state.state, DeviceState.RUNNING_OFFLINE)
            active = lifecycle.end_inspection()
            self.assertEqual(lifecycle.state.state, DeviceState.SYNCING)
            self.assertEqual(active["phase"], "SYNCING")
            controls = [json.loads(row["payload_json"]) for row in store.due_messages(20)]
            end_messages = [item for item in controls if item.get("command") == "END"]
            self.assertEqual(len(end_messages), 1)
            self.assertEqual(end_messages[0]["request_id"], active["end_request_id"])
            store.close()

    def test_restart_recovers_running_task_as_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue.db"))
            store.set_meta("bound", True)
            store.set_meta("active_inspection", {
                "inspection_id": "INS_RECOVER", "phase": "RUNNING", "sequence": 9,
            })
            mqtt = MqttStub(acknowledge=False)
            mqtt.connected = False
            lifecycle = LifecycleController(
                ConfigStub(directory), store, mqtt, HttpStub(), HardwareStub(), QuietLogger()
            )
            self.assertEqual(lifecycle.state.state, DeviceState.RUNNING_OFFLINE)
            self.assertEqual(lifecycle.active["sequence"], 9)
            store.close()


if __name__ == "__main__":
    unittest.main()
