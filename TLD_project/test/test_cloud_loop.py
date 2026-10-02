# -*- coding: utf-8 -*-
"""V0.3/V2.0 真实设备闭环回归；不连接硬件或真实服务。"""

import copy
import importlib.util
import io
import json
import os
import sys
import sqlite3
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from edge.cli import run_cli, startup_network_wizard
from edge.commands import validate_command
from edge.config import DeviceConfig, LocalConfigStore
from edge.data_manager import DataManager
from edge.hardware import HardwareSupervisor
from edge.latest import LatestValueCache
from edge.lifecycle import LifecycleController
from edge.logging_utils import print_sample
from edge.mqtt_client import MqttQueueWorker, MqttSession
from edge.protocol import Topics
from edge.runtime import EdgeRuntime
from edge.state import DeviceState
from edge.store import PersistentStore
from test.test_edge_core import ConfigStub, HardwareStub, HttpStub, MqttStub, QuietLogger


class QuietRuntimeLogger(QuietLogger):
    handlers = ()


def command(name="START_INSPECTION", command_id="CMD_START", inspection_id="INS_CLOUD"):
    now = datetime.now(timezone.utc)
    payload = {
        "type": "inspection_command", "schema_version": "2.0", "device_id": "TLD_SIM_002",
        "command_id": command_id, "inspection_id": inspection_id, "command": name,
        "field_id": "FIELD_1", "field_version": 3,
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
    }
    if name == "START_INSPECTION":
        payload["run_mode"] = "REAL_DEVICE"
        payload["field_snapshot"] = {
            "field_id": "FIELD_1", "version": 3, "coordinate_system": "WGS84",
            "geo_boundary": {"type": "Polygon", "coordinates": [[[110, 34], [111, 34], [111, 35], [110, 34]]]},
        }
    return payload


class CloudCommandsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "queue.sqlite3")
        self.store = PersistentStore(self.path)
        self.store.set_meta("bound", True)
        self.mqtt = MqttStub()
        self.config = ConfigStub(self.directory.name)
        self.config.allow_legacy_control = False
        self.hardware = HardwareStub()
        self.controller = self.make_controller()

    def make_controller(self):
        return LifecycleController(self.config, self.store, self.mqtt, HttpStub(), self.hardware, QuietLogger())

    def tearDown(self):
        self.controller.stop_command_worker()
        self.store.close()
        self.directory.cleanup()

    def test_start_preserves_cloud_identity_snapshot_and_idempotent_result(self):
        payload = command()
        first = self.controller.process_command(payload)
        self.assertEqual((first["status"], first["phase"]), ("ACCEPTED", "RUNNING"))
        self.assertEqual(self.controller.active["inspection_id"], "INS_CLOUD")
        self.assertEqual(self.controller.active["field_snapshot"], payload["field_snapshot"])
        self.assertEqual(self.controller.active["data_provenance"], "DEVICE")
        duplicate = copy.deepcopy(payload)
        duplicate["expires_at"] = "2000-01-01T00:00:00Z"
        self.assertEqual(self.controller.process_command(duplicate), first)
        self.assertEqual(self.controller.active["sequence"], 0)
        self.assertEqual(len(self.store.command_evidence("CMD_START")), 1)
        self.assertEqual(len(self.store.due_messages()), 1)

    def test_rejections_are_durable_and_do_not_create_task(self):
        cases = [
            ({"expires_at": "2000-01-01T00:00:00Z"}, "COMMAND_EXPIRED"),
            ({"run_mode": "REALTIME_SIMULATION"}, "INVALID_RUN_MODE"),
            ({"schema_version": "1.0"}, "UNSUPPORTED_SCHEMA"),
            ({"field_version": None}, "INVALID_FIELDS"),
            ({"device_id": "TLD_JETSON_001"}, "DEVICE_MISMATCH"),
        ]
        for index, (updates, reason) in enumerate(cases):
            payload = command(command_id="CMD_REJECT_{}".format(index))
            payload.update(updates)
            ack = self.controller.process_command(payload)
            self.assertEqual(ack["status"], "REJECTED")
            self.assertEqual(ack["reason_code"], reason)
            self.assertIsNone(self.controller.active)
            self.assertEqual(self.store.command_result(payload["command_id"]), ack)

    def test_snapshot_consistency_and_boundary_validation(self):
        for bad_value in (9, True, None):
            payload = command()
            payload["field_snapshot"]["version"] = bad_value
            self.assertEqual(validate_command(payload, "TLD_SIM_002", time.time()), "FIELD_SNAPSHOT_MISMATCH")
        payload = command()
        payload["field_snapshot"]["geo_boundary"]["coordinates"] = [[[0, 0], [999, 34], [111, 35], [0, 0]]]
        self.assertEqual(validate_command(payload, "TLD_SIM_002", time.time()), "INVALID_FIELD_SNAPSHOT")

    def test_no_fix_unbound_offline_and_busy_reject(self):
        self.store.set_meta("bound", False)
        self.assertEqual(self.controller.process_command(command(command_id="CMD_UNBOUND"))["reason_code"], "DEVICE_UNBOUND")
        self.store.set_meta("bound", True)
        self.mqtt.connected = False
        self.assertEqual(self.controller.process_command(command(command_id="CMD_OFFLINE"))["reason_code"], "CLOUD_OFFLINE")
        self.mqtt.connected = True
        with mock.patch.object(self.hardware, "health", return_value={"camera": True, "yolo": True, "location": {"fix": "No Fix"}}):
            self.assertEqual(self.controller.process_command(command(command_id="CMD_NO_FIX"))["reason_code"], "GPS_NO_FIX")
        self.controller.state.transition(DeviceState.IDLE, force=True)
        self.controller.process_command(command())
        self.assertEqual(self.controller.process_command(command(command_id="CMD_BUSY", inspection_id="INS_OTHER"))["reason_code"], "DEVICE_BUSY")

    def test_callback_enqueues_without_running_preflight(self):
        with mock.patch.object(self.controller, "preflight", side_effect=AssertionError("callback must not preflight")):
            self.controller.handle_downlink(command())
        self.assertIsNone(self.controller.active)
        self.assertEqual(len(self.store.pending_commands()), 1)
        self.controller.start_command_worker()
        deadline = time.time() + 2
        while not self.controller.active and time.time() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(self.controller.active)
        self.assertFalse(self.store.pending_commands())

    def test_restart_recovers_pending_command_and_previous_execution(self):
        payload = command()
        self.controller.handle_downlink(payload)
        self.store.close()
        self.store = PersistentStore(self.path)
        self.controller = self.make_controller()
        result = self.controller.process_command(self.store.pending_commands()[0])
        self.store.close()
        self.store = PersistentStore(self.path)
        self.controller = self.make_controller()
        self.assertEqual(self.controller.state.state, DeviceState.RUNNING_OFFLINE)
        self.assertEqual(self.controller.process_command(payload), result)
        self.assertEqual(self.controller.active["inspection_id"], "INS_CLOUD")

    def test_end_empty_task_two_phase_evidence_and_restart_replay(self):
        self.controller.process_command(command())
        end = command("END_INSPECTION", "CMD_END")
        accepted = self.controller.process_command(end)
        self.assertEqual(accepted["phase"], "SYNCING")
        self.assertEqual(accepted["summary"], {"sampling_stopped": True, "last_data_id": None,
                                              "last_sequence": None, "sample_count": 0, "pending_sync_count": 0})
        self.controller.network_tick()
        completed = self.store.command_result("CMD_END")
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(accepted["summary"], completed["summary"])
        self.store.mark_message_done_by_business("ack", "CMD_END:COMPLETED")
        self.controller.network_tick()
        self.assertIsNone(self.controller.active)
        self.assertEqual(self.store.get_meta("last_inspection")["inspection_id"], "INS_CLOUD")
        self.store.close()
        self.store = PersistentStore(self.path)
        self.controller = self.make_controller()
        end["expires_at"] = "2000-01-01T00:00:00Z"
        self.assertEqual(self.controller.process_command(end), completed)
        evidence = self.store.command_evidence("CMD_END")
        self.assertEqual([item["status"] for item in evidence], ["ACCEPTED", "COMPLETED"])
        self.assertFalse(self.store.message_done("ack", "CMD_END:COMPLETED"))
        self.assertFalse(self.store.message_done("ack", "CMD_END:ACCEPTED"))

    def test_end_wrong_task_or_field_is_rejected(self):
        self.controller.process_command(command())
        end = command("END_INSPECTION", "CMD_WRONG", "INS_WRONG")
        self.assertEqual(self.controller.process_command(end)["reason_code"], "INSPECTION_MISMATCH")
        end = command("END_INSPECTION", "CMD_WRONG_FIELD")
        end["field_version"] = 99
        self.assertEqual(self.controller.process_command(end)["reason_code"], "FIELD_SNAPSHOT_MISMATCH")
        self.assertEqual(self.controller.active["phase"], "RUNNING")

    def test_legacy_start_is_explicitly_disabled(self):
        with self.assertRaises(RuntimeError):
            self.controller.start_inspection()

    def test_old_unconfirmed_task_is_not_cleared_after_network_confirmation(self):
        active = {"inspection_id": "INS_OLD", "phase": "STARTING", "sequence": 0}
        self.store.set_meta("active_inspection", active)
        self.controller = self.make_controller()
        self.assertEqual(self.controller.state.state, DeviceState.STARTING)
        self.controller.network_tick()
        self.assertEqual(self.controller.active, active)

    def test_restart_syncing_resumes_both_end_phases_and_reconnect_replay(self):
        self.controller.process_command(command())
        end = command("END_INSPECTION", "CMD_END")
        accepted = self.controller.process_command(end)
        self.store.close()
        self.store = PersistentStore(self.path)
        self.controller = self.make_controller()
        self.assertEqual(self.controller.state.state, DeviceState.SYNCING)
        self.assertEqual(self.controller.process_command(end), accepted)
        self.controller.network_tick()
        completed = self.store.command_result("CMD_END")
        self.assertEqual(completed["status"], "COMPLETED")
        for ack in self.store.command_evidence("CMD_END"):
            self.store.mark_message_done_by_business("ack", ack["command_id"] + ":" + ack["status"])
        self.controller.request_final_replay()
        self.controller.start_command_worker()
        deadline = time.time() + 2
        while self.store.message_done("ack", "CMD_END:COMPLETED") and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.store.message_done("ack", "CMD_END:ACCEPTED"))
        self.assertFalse(self.store.message_done("ack", "CMD_END:COMPLETED"))


class RuntimeCloudTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "device.env")
        LocalConfigStore(self.path).save({"DEVICE_ID": "TLD_SIM_002", "MIN_FREE_DISK_MB": "1",
                                         "DEVICE_SECRET": "test-only-credential",
                                         "BACKEND_URL": "http://192.168.1.8:8000", "MQTT_HOST": "192.168.1.8"})
        self.runtime = EdgeRuntime(self.directory.name, self.path)
        self.runtime.logger = QuietRuntimeLogger()
        self.runtime.lifecycle.logger = QuietLogger()

    def tearDown(self):
        # Runtime owns its build_logger; close safely even when no thread was started.
        from edge.logging_utils import close_logger
        import logging
        self.runtime.stop()
        close_logger(logging.getLogger("tld.edge"))
        self.directory.cleanup()

    def prepare_task(self):
        self.runtime.store.set_meta("bound", True)
        self.runtime.lifecycle.state.transition(DeviceState.IDLE, force=True)
        self.runtime.mqtt._connected.set()
        self.runtime._hardware_started = True
        self.runtime.hardware.health = HardwareStub().health
        return self.runtime.lifecycle.process_command(command())

    def test_heartbeat_not_ready_in_communication_mode_lwt_offline(self):
        self.runtime.mqtt._connected.set()
        status = self.runtime.heartbeat()
        self.assertEqual(status["communication_status"], "ONLINE")
        self.assertEqual(status["operating_status"], "STARTUP")
        self.assertEqual(status["camera_status"], "NOT_STARTED")
        self.assertEqual(status["inference_status"], "NOT_STARTED")
        self.assertEqual(self.runtime.mqtt.status_payload(offline=True)["communication_status"], "OFFLINE")

    def test_missing_device_credential_rejects_start_not_fake_ready(self):
        self.runtime.config.device_secret = ""
        self.assertEqual(self.prepare_task()["reason_code"], "DEVICE_CREDENTIALS_MISSING")
        self.assertEqual(self.runtime.heartbeat()["operating_status"], "STARTUP")

    def test_heartbeat_pending_excludes_ack_and_uses_current_inspection(self):
        self.prepare_task()
        status = self.runtime.heartbeat()
        self.assertEqual(status["operating_status"], "RUNNING")
        self.assertEqual(status["gps_fix"], "GPS_FIX")
        self.assertEqual(status["inspection_id"], "INS_CLOUD")
        self.assertEqual(status["pending_sync_count"], 0)
        self.assertEqual(status["sync_status"], "SYNCED")
        self.runtime.store.enqueue_message("data", "OLD_DATA", self.runtime.mqtt.topics.data,
                                           {"inspection_id": "INS_OTHER", "data_id": "OLD_DATA"})
        self.assertEqual(self.runtime.heartbeat()["pending_sync_count"], 0)

    def test_enqueued_json_is_identical_and_offline_sequence_survives_restart(self):
        self.prepare_task()
        self.runtime.mqtt._connected.clear()
        self.runtime.lifecycle.network_tick()
        with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            payload = self.runtime._sample_once()
        self.assertEqual(json.loads(output.getvalue()), payload)
        row = [row for row in self.runtime.store.due_messages() if row["kind"] == "data"][0]
        self.assertEqual(json.loads(row["payload_json"]), payload)
        self.assertEqual((payload["schema_version"], payload["run_mode"], payload["data_provenance"]),
                         ("1.3", "REAL_DEVICE", "DEVICE"))
        self.assertEqual((payload["field_id"], payload["field_version"]), ("FIELD_1", 3))
        self.assertNotIn("flight_status", payload)
        self.assertIsNone(payload["location"]["latitude"])
        self.assertIsNone(payload["environment"]["sampled_at"])
        self.assertFalse(payload["environment"]["valid"])
        self.assertEqual(self.runtime.lifecycle.state.state, DeviceState.RUNNING_OFFLINE)
        self.runtime.stop()
        self.runtime = EdgeRuntime(self.directory.name, self.path)
        self.runtime.logger = QuietRuntimeLogger()
        self.runtime.lifecycle.logger = QuietLogger()
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            second = self.runtime._sample_once()
        self.assertEqual(second["sequence"], 2)
        self.assertNotEqual(second["data_id"], payload["data_id"])
        self.assertEqual(self.runtime.store.pending_data_for_inspection("INS_CLOUD"), 2)
        recovered = [json.loads(row["payload_json"]) for row in self.runtime.store.due_messages() if row["kind"] == "data"]
        self.assertEqual(recovered[0]["data_id"], payload["data_id"])

    def test_end_waits_for_last_sample_and_image_transaction(self):
        self.prepare_task()
        entered, release, ended = threading.Event(), threading.Event(), threading.Event()
        errors, result = [], {}
        original_build = self.runtime.data_manager.build

        def slow_build(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("sample test timeout")
            payload = original_build(*args, **kwargs)
            payload["detection"] = {"has_target": True, "sampled_at": "real_frame_time", "results": [{"class": "disease", "confidence": 0.8, "bbox": [1, 1, 2, 2]}]}
            return payload

        def last_image(*args):
            return {"image_id": "IMG_LAST", "path": os.path.join(self.directory.name, "last.jpg")}

        def sample():
            try:
                result["sample"] = self.runtime._sample_once()
            except Exception as exc:
                errors.append(exc)

        def end():
            try:
                result["end"] = self.runtime.lifecycle.process_command(command("END_INSPECTION", "CMD_END"))
            except Exception as exc:
                errors.append(exc)
            finally:
                ended.set()

        with mock.patch.object(self.runtime.data_manager, "build", side_effect=slow_build), mock.patch.object(self.runtime, "_save_detection_image", side_effect=last_image), mock.patch("sys.stdout", new_callable=io.StringIO):
            sampler = threading.Thread(target=sample)
            stopper = threading.Thread(target=end)
            sampler.start()
            self.assertTrue(entered.wait(2))
            stopper.start()
            self.assertFalse(ended.wait(0.05))
            release.set()
            sampler.join(3)
            stopper.join(3)
        self.assertFalse(errors)
        self.assertFalse(sampler.is_alive() or stopper.is_alive())
        summary = result["end"]["summary"]
        self.assertEqual(summary["last_data_id"], result["sample"]["data_id"])
        self.assertEqual((summary["last_sequence"], summary["sample_count"], summary["pending_sync_count"]), (1, 1, 2))
        self.assertIsNone(self.runtime._sample_once())
        self.runtime.lifecycle.network_tick()
        self.assertEqual(self.runtime.store.command_result("CMD_END")["status"], "ACCEPTED")
        self.runtime.store.mark_message_done_by_business("data", result["sample"]["data_id"])
        self.runtime.lifecycle.network_tick()
        self.assertEqual(self.runtime.store.command_result("CMD_END")["status"], "ACCEPTED")
        self.runtime.store.mark_image_done(self.runtime.store.due_images()[0]["id"])
        self.runtime.lifecycle.network_tick()
        completed = self.runtime.store.command_result("CMD_END")
        self.assertEqual(completed["status"], "COMPLETED")
        for key in ("last_data_id", "last_sequence", "sample_count", "sampling_stopped"):
            self.assertEqual(completed["summary"][key], summary[key])
        self.assertEqual(completed["summary"]["pending_sync_count"], 0)

    def test_active_or_pending_cache_prevents_address_change(self):
        self.prepare_task()
        with self.assertRaises(RuntimeError):
            self.runtime.save_network("192.168.1.9", 8000, 18883, "")
        self.assertEqual(self.runtime.config.mqtt_host, "192.168.1.8")
        self.runtime.store.delete_meta("active_inspection")
        self.runtime.lifecycle.state.transition(DeviceState.IDLE, force=True)
        self.runtime.store.enqueue_message("data", "D_PENDING", self.runtime.mqtt.topics.data, {"inspection_id": "INS_OLD"})
        with self.assertRaises(RuntimeError):
            self.runtime.save_network("192.168.1.9", 8000, 18883, "")

    def test_wizard_confirms_saved_address_before_start_or_hardware(self):
        for hardware in (False, True):
            events = []
            def http(*args):
                events.append("http")
                return {"ok": True, "category": "reachable", "message": "ok"}
            def mqtt(*args):
                events.append("mqtt")
                return {"ok": True, "category": "connected", "message": "ok"}
            with mock.patch("builtins.input", side_effect=["", "", "", "", "0"]), mock.patch("getpass.getpass", return_value=""), mock.patch.object(self.runtime, "test_http_network", side_effect=http), mock.patch.object(self.runtime, "test_mqtt_network", side_effect=mqtt), mock.patch.object(self.runtime, "start", side_effect=lambda **kwargs: events.append(("start", kwargs["start_hardware"]))), mock.patch.object(self.runtime, "stop"), mock.patch("sys.stdout", new_callable=io.StringIO):
                run_cli(self.runtime, start_hardware=hardware)
            self.assertEqual(events, ["http", "mqtt", ("start", hardware)])

    def test_wizard_rejects_empty_first_address_and_retries_then_supports_18883(self):
        self.runtime.config.backend_url = ""
        self.runtime.config.mqtt_host = ""
        events = []
        def fail_http(*args):
            events.append("http")
            return {"ok": False, "category": "refused", "message": "port refused"}
        def ok_mqtt(*args):
            events.append("mqtt")
            return {"ok": True, "category": "connected", "message": "ok"}
        with mock.patch("builtins.input", side_effect=["", "192.168.1.8", "8000", "18883", "", "0"]), mock.patch("getpass.getpass", return_value=""), mock.patch.object(self.runtime, "test_http_network", side_effect=fail_http), mock.patch.object(self.runtime, "test_mqtt_network", side_effect=ok_mqtt), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertFalse(startup_network_wizard(self.runtime))
        self.assertEqual(events, ["http", "mqtt"])
        self.assertEqual(self.runtime.config.mqtt_port, 18883)
        self.assertIn("IPv4", output.getvalue())

    def test_wizard_confirms_active_without_erasing_binding_or_cache(self):
        self.prepare_task()
        active = self.runtime.lifecycle.active
        with mock.patch("builtins.input", side_effect=["", "", "", ""]), mock.patch("getpass.getpass", return_value=""), mock.patch.object(self.runtime, "test_http_network", return_value={"ok": True, "category": "reachable", "message": "ok"}), mock.patch.object(self.runtime, "test_mqtt_network", return_value={"ok": True, "category": "connected", "message": "ok"}), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(startup_network_wizard(self.runtime))
        self.assertEqual(self.runtime.lifecycle.active, active)
        self.assertTrue(self.runtime.lifecycle.bound)

    def test_wizard_tls_preserves_separate_https_and_broker_host(self):
        LocalConfigStore(self.path).save({"BACKEND_URL": "https://api.example.com", "MQTT_HOST": "mqtt.example.com", "MQTT_TLS": "true", "MQTT_PORT": "8883"})
        self.runtime._rebuild_network_clients(DeviceConfig.load(self.directory.name, self.path, environ={}))
        with mock.patch("builtins.input", side_effect=["", "", "", "", ""]), mock.patch("getpass.getpass", return_value=""), mock.patch.object(self.runtime, "test_http_network", return_value={"ok": True, "category": "reachable", "message": "ok"}), mock.patch.object(self.runtime, "test_mqtt_network", return_value={"ok": True, "category": "connected", "message": "ok"}) as mqtt, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(startup_network_wizard(self.runtime))
        mqtt.assert_called_once_with("mqtt.example.com", 8883, "", "")
        self.assertTrue(self.runtime.config.mqtt_tls)
        self.assertEqual(self.runtime.config.backend_url, "https://api.example.com")

    def test_wizard_failure_does_not_block_existing_offline_task_recovery(self):
        self.prepare_task()
        active = self.runtime.lifecycle.active
        failed = {"ok": False, "category": "timeout", "message": "unreachable"}
        with mock.patch("builtins.input", side_effect=["", "", "", "", "O"]), mock.patch("getpass.getpass", return_value=""), mock.patch.object(self.runtime, "test_http_network", return_value=failed), mock.patch.object(self.runtime, "test_mqtt_network", return_value=failed), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(startup_network_wizard(self.runtime))
        self.assertEqual(self.runtime.lifecycle.active, active)


class DataAndOutputTests(unittest.TestCase):
    def test_nulls_and_nonfinite_values_not_zero_or_new_sensor_timestamp(self):
        cache = LatestValueCache()
        cache.update("location", {"fix": "GPS Fix", "latitude": float("nan"), "longitude": 110}, valid=True)
        cache.update("environment", {"temperature": float("inf"), "humidity": 40, "co2": 420, "lux": None}, sampled_at=None, valid=True)
        payload = DataManager("TLD_SIM_002", cache).build("INS", 1)
        self.assertIsNone(payload["location"]["latitude"])
        self.assertIsNone(payload["location"]["longitude"])
        self.assertFalse(payload["location"]["position_valid"])
        self.assertIsNone(payload["environment"]["temperature"])
        self.assertEqual(payload["environment"]["humidity"], 40)
        self.assertIsNone(payload["environment"]["sampled_at"])
        self.assertFalse(payload["environment"]["valid"])
        json.dumps(payload, allow_nan=False)

    def test_json_print_redaction_off_switch_and_atomic_concurrent_lines(self):
        config = types.SimpleNamespace(device_secret="permanent-fixture", mqtt_password="mqtt-fixture",
                                       ntrip_password="ntrip-fixture", print_sample_json=True)
        payload = {"data_id": "DATA_1", "nested": {"JWT": "jwt-fixture", "pairing_token": "pair-fixture", "Authorization": "auth-fixture"}, "unexpected": "permanent-fixture mqtt-fixture ntrip-fixture"}
        output = io.StringIO()
        print_sample(payload, config, output)
        text = output.getvalue()
        for secret in ("permanent-fixture", "mqtt-fixture", "ntrip-fixture", "jwt-fixture", "pair-fixture", "auth-fixture"):
            self.assertNotIn(secret, text)
        self.assertEqual(json.loads(text)["data_id"], "DATA_1")
        self.assertEqual(payload["nested"]["JWT"], "jwt-fixture")
        output = io.StringIO()
        threads = [threading.Thread(target=lambda: print_sample({"data_id": "DATA_1", "blob": "x" * 2000}, config, output)) for index in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(output.getvalue().splitlines()), 20)
        for line in output.getvalue().splitlines():
            self.assertEqual(json.loads(line)["data_id"], "DATA_1")
        config.print_sample_json = False
        output = io.StringIO()
        print_sample(payload, config, output)
        self.assertEqual(output.getvalue(), "")

    def test_real_device_cannot_use_virtual_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                DeviceConfig({"DEVICE_ID": "TLD_JETSON_001"}, directory, os.path.join(directory, "device.env"))

    def test_ntrip_unconfigured_skips_factory_preserves_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config = DeviceConfig({"NTRIP_ENABLED": "true", "NTRIP_PASSWORD": "private-fixture"}, directory, os.path.join(directory, "device.env"))
            supervisor = HardwareSupervisor(config, LatestValueCache(), QuietLogger(), lambda: True)
            settings = supervisor._ntrip_settings()
            self.assertFalse(settings["enabled"])
            self.assertEqual(config.ntrip_password, "private-fixture")
        # GPSManager constructor is tested with imported drivers replaced, not with a serial port.
        modules = {"serial": types.SimpleNamespace(SerialException=OSError),
                   "gps.gps_reader": types.SimpleNamespace(GPSReader=mock.Mock()),
                   "gps.ntrip_client": types.SimpleNamespace(NTRIPClient=mock.Mock())}
        with mock.patch.dict(sys.modules, modules), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            spec = importlib.util.spec_from_file_location("gps.gps_manager", os.path.join(os.path.dirname(__file__), "..", "gps", "gps_manager.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.GPSManager(gps_port="/dev/fake", ntrip_settings={"enabled": False})
            modules["gps.ntrip_client"].NTRIPClient.assert_not_called()
        self.assertIn("未启用网络 RTK，使用普通 GPS", output.getvalue())

    def test_old_sqlite_queue_migrates_without_losing_ids_sequence_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "old.sqlite3")
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE outbound(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,business_id TEXT NOT NULL,topic TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_attempt_at REAL NOT NULL DEFAULT 0,last_error TEXT,created_at TEXT NOT NULL,UNIQUE(kind,business_id))")
            payload = {"inspection_id": "INS_OLD", "data_id": "DATA_OLD", "sequence": 123}
            connection.execute("INSERT INTO outbound(kind,business_id,topic,payload_json,created_at) VALUES ('data','DATA_OLD','topic',?,'time')", (json.dumps(payload),))
            connection.commit()
            connection.close()
            store = PersistentStore(path)
            self.assertEqual(store.pending_data_for_inspection("INS_OLD"), 1)
            self.assertEqual(json.loads(store.due_messages()[0]["payload_json"]), payload)
            store.close()

    def test_image_queue_uses_actual_camera_capture_time(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "queue"))
            payload = {"data_id": "DATA_1", "inspection_id": "INS_1", "timestamp": "2026-10-01T01:00:01Z"}
            store.commit_sample({"inspection_id": "INS_1"}, "topic", payload,
                                {"image_id": "IMG_1", "path": "/unused", "captured_at": "2026-10-01T01:00:00Z"})
            store.mark_message_done_by_business("data", "DATA_1")
            self.assertEqual(store.due_images()[0]["captured_at"], "2026-10-01T01:00:00Z")
            store.close()

    def test_camera_failure_does_not_reidentify_old_frame_as_new_image(self):
        with tempfile.TemporaryDirectory() as directory:
            config = DeviceConfig({}, directory, os.path.join(directory, "env"))
            cache = LatestValueCache()
            cache.update("detection", [{"class": "old"}], sampled_at="old_time", valid=True)
            supervisor = HardwareSupervisor(config, cache, QuietLogger(), lambda: True)
            supervisor._latest_frame = types.SimpleNamespace(copy=lambda: object())
            supervisor._latest_frame_at = "old_time"
            supervisor.engine = mock.Mock()
            supervisor._running = True
            with mock.patch("edge.hardware.time.sleep", side_effect=lambda seconds: setattr(supervisor, "_running", False)):
                supervisor._infer_frames()
            supervisor.engine.infer.assert_not_called()
            self.assertFalse(cache.get("detection")["valid"])
            self.assertEqual(cache.get("detection")["sampled_at"], "old_time")


class GpsValidityTests(unittest.TestCase):
    def test_valid_gga_then_invalid_rmc_never_claims_fix_and_stale_sample_expires(self):
        modules = {"serial": types.SimpleNamespace(SerialException=OSError), "pynmea2": types.ModuleType("pynmea2")}
        with mock.patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("gps.gps_reader", os.path.join(os.path.dirname(__file__), "..", "gps", "gps_reader.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        reader = module.GPSReader.__new__(module.GPSReader)
        reader._lock = threading.Lock()
        reader._latest = {}
        reader._last_data_time = None
        reader._latest_sampled_at = None
        reader._on_gga(types.SimpleNamespace(num_sats="12", gps_qual="1", latitude=34, longitude=110, altitude=18.7))
        self.assertEqual(reader.get_position()["fix"], "GPS Fix")
        sampled_at = reader.get_position()["sampled_at"]
        self.assertEqual(reader.get_position()["sampled_at"], sampled_at)
        reader._on_rmc(types.SimpleNamespace(spd_over_grnd="", true_course="", latitude=34, longitude=110, status="V"))
        self.assertEqual(reader.get_position()["fix"], "No Fix")
        reader._last_data_time = time.time() - 6
        self.assertIsNone(reader.get_position())


class CudaOwnershipTests(unittest.TestCase):
    def load_fake_module(self):
        self.events = []
        record = lambda name: self.events.append((name, threading.get_ident()))
        context = types.SimpleNamespace(pop=lambda: record("pop"), detach=lambda: record("detach"))
        cuda = types.SimpleNamespace(init=lambda: record("init"), Device=lambda index: types.SimpleNamespace(make_context=lambda: (record("make_context") or context)),
                                     memcpy_htod=lambda *args: record("htod"), memcpy_dtoh=lambda *args: record("dtoh"))
        package = types.ModuleType("inference")
        package.__path__ = []
        modules = {"inference": package, "cv2": types.ModuleType("cv2"), "numpy": types.ModuleType("numpy"),
                   "tensorrt": types.ModuleType("tensorrt"), "pycuda": types.ModuleType("pycuda"), "pycuda.driver": cuda,
                   "inference.yolov11_postprocess": types.SimpleNamespace(decode_output=lambda *args: [], scale_detections=lambda *args: [])}
        with mock.patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("cuda_test_engine", os.path.join(os.path.dirname(__file__), "..", "inference", "inference_engine.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_context_is_popped_detached_on_failed_load(self):
        module = self.load_fake_module()
        engine = module.InferenceEngine()
        with mock.patch.object(engine, "_load_engine", side_effect=RuntimeError("bad engine")):
            with self.assertRaises(RuntimeError):
                engine.load()
        self.assertEqual([name for name, owner in self.events], ["init", "make_context", "pop", "detach"])
        self.assertIsNone(engine._cuda_context)

    def test_cross_thread_infer_release_rejected_without_touching_context(self):
        module = self.load_fake_module()
        engine = module.InferenceEngine()
        with mock.patch.object(engine, "_load_engine", return_value=True):
            engine.load()
        failures = []
        def other_thread():
            for action in (lambda: engine.infer(None), engine.release):
                try:
                    action()
                except RuntimeError:
                    failures.append(True)
        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()
        self.assertEqual(len(failures), 2)
        engine.release()
        self.assertEqual([name for name, owner in self.events][-2:], ["pop", "detach"])
        self.assertEqual(len(set(owner for name, owner in self.events)), 1)

    def test_supervisor_load_infer_release_all_on_yolo_thread(self):
        events = []
        with tempfile.TemporaryDirectory() as directory:
            config = DeviceConfig({}, directory, os.path.join(directory, "device.env"))
            supervisor = HardwareSupervisor(config, LatestValueCache(), QuietLogger(), lambda: True)
            supervisor._running = True
            supervisor._latest_frame = types.SimpleNamespace(copy=lambda: types.SimpleNamespace())
            supervisor._latest_frame_at = "actual_camera_capture"
            supervisor._set_health("camera", True)
            class Engine(object):
                def __init__(self, *args):
                    events.append(("create", threading.get_ident()))
                def load(self):
                    events.append(("load", threading.get_ident()))
                def infer(self, frame):
                    events.append(("infer", threading.get_ident()))
                    supervisor._running = False
                    return []
                def release(self):
                    events.append(("release", threading.get_ident()))
            with mock.patch.dict(sys.modules, {"inference": types.SimpleNamespace(InferenceEngine=Engine)}):
                worker = threading.Thread(target=supervisor._inference_loop)
                worker.start()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual([name for name, owner in events], ["create", "load", "infer", "release"])
            self.assertEqual(len(set(owner for name, owner in events)), 1)
            self.assertNotEqual(events[0][1], threading.get_ident())
            self.assertIsNone(supervisor.engine)


class MqttEvidenceTests(unittest.TestCase):
    def test_ui_is_paused_without_constructing_runtime(self):
        import main
        with mock.patch("edge.runtime.EdgeRuntime", side_effect=AssertionError("UI must not construct runtime")), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main.main(["--ui"]), 2)

    def test_actual_will_connect_and_graceful_offline_are_explicit(self):
        logger = QuietLogger()
        with tempfile.TemporaryDirectory() as directory:
            config = DeviceConfig({"MQTT_HOST": "192.168.1.8"}, directory, os.path.join(directory, "env"))
            client = mock.Mock()
            client.publish.return_value.rc = 0
            client.publish.return_value.is_published.return_value = True
            factory = mock.Mock(return_value=client)
            modules = {"paho": types.ModuleType("paho"), "paho.mqtt": types.ModuleType("paho.mqtt"),
                       "paho.mqtt.client": types.SimpleNamespace(Client=factory)}
            session = MqttSession(config, logger)
            session.on_connected = mock.Mock()
            with mock.patch.dict(sys.modules, modules):
                session.start()
                factory.assert_called_once_with(client_id="TLD_SIM_002", clean_session=False)
                will = json.loads(client.will_set.call_args[0][1])
                self.assertEqual(will["communication_status"], "OFFLINE")
                self.assertEqual(will["operating_status"], "STARTUP")
                session._on_connect(client, None, {}, 0)
                status = json.loads(client.publish.call_args[0][1])
                self.assertEqual(status["communication_status"], "ONLINE")
                self.assertEqual(status["inference_status"], "NOT_STARTED")
                session.on_connected.assert_called_once_with()
                session.stop()
                self.assertEqual(json.loads(client.publish.call_args[0][1])["communication_status"], "OFFLINE")

    def test_queue_retry_keeps_exact_data_id_and_puback_is_not_cloud_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PersistentStore(os.path.join(directory, "db"))
            payload = {"data_id": "DATA_ORIGINAL", "inspection_id": "INS_CLOUD", "sequence": 1}
            store.enqueue_message("data", "DATA_ORIGINAL", "topic", payload)
            logs = []
            logger = types.SimpleNamespace(info=logs.append, warning=logs.append, error=logs.append)
            session = types.SimpleNamespace(connected=True)
            worker = MqttQueueWorker(store, session, logger)
            attempts = []
            def publish(topic, message, **kwargs):
                attempts.append(copy.deepcopy(message))
                worker._running = False
                return len(attempts) > 1
            session.publish = publish
            worker._running = True
            worker._loop()
            self.assertEqual(store.pending_business_count(), 1)
            store.retry_all()
            worker._running = True
            worker._loop()
            self.assertEqual(attempts, [payload, payload])
            self.assertEqual(store.pending_business_count(), 0)
            self.assertTrue(any("MQTT_RETRY_FAILED" in line for line in logs))
            self.assertTrue(any("MQTT_RETRY" in line for line in logs))
            self.assertTrue(any("BROKER_PUBACK" in line and "不代表云端入库" in line for line in logs))
            store.close()


if __name__ == "__main__":
    unittest.main()
