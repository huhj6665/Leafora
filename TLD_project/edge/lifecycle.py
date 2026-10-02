# -*- coding: utf-8 -*-
"""动态配对和巡检 START/END 生命周期。"""

import os
import copy
import re
import threading
import time

from .preflight import run_preflight
from .commands import validate_command
from .protocol import new_id, utc_now
from .state import DeviceState, StateMachine


class LifecycleController(object):
    def __init__(self, config, store, mqtt, http_client, hardware, logger):
        self.config = config
        self.store = store
        self.mqtt = mqtt
        self.http = http_client
        self.hardware = hardware
        self.logger = logger
        self._ack_condition = threading.Condition()
        self._acks = {}
        self._pairing = None
        # 同一个锁覆盖采样与 END，等待正在生成的最后一条数据/图片。
        self.execution_lock = threading.RLock()
        self._command_running = False
        self._command_thread = None
        self._command_wakeup = threading.Event()
        self._last_final_replay = 0.0
        self._replay_requested = threading.Event()
        active = self.store.get_meta("active_inspection")
        bound = bool(self.store.get_meta("bound", False))
        if active:
            phase = active.get("phase")
            if phase in ("RUNNING", "RUNNING_OFFLINE"):
                initial = DeviceState.RUNNING_OFFLINE
            elif phase in ("SYNCING", "ENDING"):
                initial = DeviceState.SYNCING
            elif phase == "STARTING":
                initial = DeviceState.STARTING
            else:
                # 未知/旧未确认任务不能因向导后连接成功被当成空同步删除。
                initial = DeviceState.ERROR
        else:
            initial = DeviceState.IDLE if bound else DeviceState.UNBOUND
        self.state = StateMachine(initial)
        self.mqtt.add_downlink_callback(self.handle_downlink)

    @property
    def bound(self):
        return bool(self.store.get_meta("bound", False))

    @property
    def owner_nickname(self):
        return self.store.get_meta("owner_nickname", "") or ""

    @property
    def active(self):
        return self.store.get_meta("active_inspection")

    def preflight(self):
        return run_preflight(
            self.bound, self.mqtt.connected, self.hardware.health(),
            self.config.state_dir, self.config.min_free_disk_mb
        )

    def create_pairing(self):
        if self.bound:
            raise RuntimeError("设备已绑定")
        self.state.transition(DeviceState.PAIRING, "正在申请动态配对会话")
        try:
            session = self.http.create_pairing_session()
            path = self.http.generate_pairing_qr(session, self.config.qr_dir)
            self._pairing = dict(session)
            self._pairing["qr_path"] = path
            self.logger.info("动态配对二维码已生成")
            return dict(self._pairing)
        except Exception:
            self.state.transition(DeviceState.UNBOUND, "配对会话申请失败")
            raise

    def pairing_status(self):
        if not self._pairing:
            return None
        data = self.http.get_pairing_session(self._pairing["pairing_session_id"])
        status = str((data or {}).get("status", "PENDING")).upper()
        if status in ("CONFIRMED", "CONSUMED", "BOUND"):
            self._confirm_pairing(data or {})
        elif status in ("EXPIRED", "CANCELLED"):
            self.cancel_pairing(status)
        return data

    def cancel_pairing(self, reason="CANCELLED"):
        # 冻结协议未定义设备侧取消 API，仅在本机清除一次性会话展示。
        self._delete_pairing_qr()
        self._pairing = None
        if self.state.state == DeviceState.PAIRING:
            self.state.transition(DeviceState.UNBOUND, str(reason))

    def _confirm_pairing(self, payload):
        self.store.set_meta("bound", True)
        nickname = payload.get("owner_nickname") or payload.get("nickname") or ""
        self.store.set_meta("owner_nickname", nickname)
        self._delete_pairing_qr()
        self._pairing = None
        if self.active is None:
            self.state.transition(DeviceState.IDLE, "设备绑定成功", force=True)
        self.logger.info("设备绑定成功")

    def _delete_pairing_qr(self):
        if not self._pairing:
            return
        path = self._pairing.get("qr_path")
        try:
            if path and os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    def handle_downlink(self, payload):
        if not isinstance(payload, dict):
            return
        if payload.get("device_id") not in (None, self.config.device_id):
            return
        message_type = str(payload.get("type", ""))
        if message_type == "PAIRING_CONFIRMED":
            self._confirm_pairing(payload)
            return
        if message_type == "DEVICE_UNBOUND":
            self.store.set_meta("bound", False)
            self.store.delete_meta("owner_nickname")
            if self.active is None:
                self.state.transition(DeviceState.UNBOUND, "云端通知设备已解绑", force=True)
            return
        if message_type == "inspection_command":
            if isinstance(payload.get("command_id"), str) and re.match(r"^[A-Za-z0-9_.-]{1,64}$", payload["command_id"]):
                allowed = ("type", "schema_version", "command_id", "command", "inspection_id",
                           "device_id", "field_id", "field_version", "field_snapshot", "run_mode",
                           "timestamp", "expires_at")
                safe_payload = dict((key, copy.deepcopy(payload[key])) for key in allowed if key in payload)
                self.store.receive_command(safe_payload)
                result = self.store.command_result(payload["command_id"])
                if result:
                    self.replay_command(payload["command_id"])
                self._command_wakeup.set()
            return
        if message_type != "control_ack":
            return
        request_id = payload.get("request_id")
        if not request_id:
            return
        with self._ack_condition:
            self._acks[request_id] = dict(payload)
            self._ack_condition.notify_all()
        if str(payload.get("status", "")).upper() == "ACCEPTED":
            self.store.mark_message_done_by_business("control", request_id)

    def _wait_ack(self, request_id, timeout_s):
        deadline = time.time() + timeout_s
        with self._ack_condition:
            while request_id not in self._acks:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._ack_condition.wait(remaining)
            return self._acks.pop(request_id)

    def start_inspection(self, name="", location_note=""):
        if not getattr(self.config, "allow_legacy_control", False):
            raise RuntimeError("任务由小程序发起；设备等待云端 START_INSPECTION 命令")
        if self.state.state != DeviceState.IDLE:
            raise RuntimeError("当前状态不能启动任务: {}".format(self.state.state))
        checks = self.preflight()
        if not checks.ok:
            names = ", ".join(item["name"] for item in checks.errors)
            raise RuntimeError("启动前检查未通过: {}".format(names))
        inspection_id = new_id("INS")
        request_id = new_id("REQ")
        display_name = name.strip() or "{} {} 自动巡检".format(
            self.config.device_id, time.strftime("%Y-%m-%d %H:%M")
        )
        display_name = display_name[:128]
        payload = {
            "type": "inspection_control",
            "schema_version": "1.1",
            "request_id": request_id,
            "command": "START",
            "inspection_id": inspection_id,
            "device_id": self.config.device_id,
            "timestamp": utc_now(),
            "name": display_name,
        }
        active = {
            "inspection_id": inspection_id,
            "start_request_id": request_id,
            "name": display_name,
            # 协议尚未定义地点备注字段，先本地保存，避免私自扩展 MQTT JSON。
            "location_note": location_note.strip(),
            "started_at": payload["timestamp"],
            "phase": "STARTING",
            "sequence": 0,
            "samples": 0,
            "targets": 0,
            "images": 0,
            "errors": 0,
        }
        self.store.set_meta("active_inspection", active)
        self.store.enqueue_message("control", request_id, self.mqtt.topics.control, payload)
        self.state.transition(DeviceState.STARTING, "等待云端 START ACK")
        for attempt in range(max(1, self.config.start_retries)):
            self.mqtt.publish(self.mqtt.topics.control, payload)
            ack = self._wait_ack(request_id, self.config.start_ack_timeout_s)
            if ack is None:
                self.logger.warning("START ACK 等待超时，第 {} 次".format(attempt + 1))
                continue
            if str(ack.get("status", "")).upper() == "ACCEPTED":
                active["phase"] = "RUNNING"
                active["cloud_time"] = ack.get("cloud_time")
                self.store.set_meta("active_inspection", active)
                self.state.transition(DeviceState.RUNNING, "云端已接受 START")
                self.logger.info("巡检已开始: {}".format(inspection_id))
                return dict(active)
            self.store.mark_message_done_by_business("control", request_id)
            self.store.delete_meta("active_inspection")
            self.state.transition(DeviceState.IDLE, ack.get("message") or "云端拒绝 START")
            raise RuntimeError(ack.get("message") or "云端拒绝 START")
        self.store.mark_message_done_by_business("control", request_id)
        self.store.delete_meta("active_inspection")
        self.state.transition(DeviceState.ERROR, "START ACK 超时，云端结果不确定")
        raise RuntimeError("START ACK 超时；已停止本地启动，需在云端核对任务")

    def end_inspection(self):
        if not getattr(self.config, "allow_legacy_control", False):
            raise RuntimeError("请在小程序结束任务；设备等待云端 END_INSPECTION 命令")
        active = self.active
        if not active or self.state.state not in (DeviceState.RUNNING, DeviceState.RUNNING_OFFLINE):
            raise RuntimeError("当前没有可结束的巡检")
        self.state.transition(DeviceState.ENDING, "停止产生新采样")
        request_id = new_id("REQ")
        pending = self.store.pending_counts()["total"]
        payload = {
            "type": "inspection_control",
            "schema_version": "1.1",
            "request_id": request_id,
            "command": "END",
            "inspection_id": active["inspection_id"],
            "device_id": self.config.device_id,
            "timestamp": utc_now(),
            "summary": {
                "samples": active.get("samples", 0),
                "targets": active.get("targets", 0),
                "images": active.get("images", 0),
                "pending": pending,
                "errors": active.get("errors", 0),
            },
        }
        active["phase"] = "SYNCING"
        active["end_request_id"] = request_id
        active["ended_at"] = payload["timestamp"]
        self.store.set_meta("active_inspection", active)
        self.store.enqueue_message("control", request_id, self.mqtt.topics.control, payload)
        self.mqtt.publish(self.mqtt.topics.control, payload)
        self.state.transition(DeviceState.SYNCING, "END 已排队，等待补传完成")
        self.logger.info("巡检已停止采样，进入同步")
        return dict(active)

    def network_tick(self):
        with self.execution_lock:
            self._network_tick_locked()

    def _network_tick_locked(self):
        if self.mqtt.connected and time.time() - self._last_final_replay >= 60:
            self.request_final_replay()
            self._last_final_replay = time.time()
        current = self.state.state
        if current == DeviceState.RUNNING and not self.mqtt.connected:
            self.state.transition(DeviceState.RUNNING_OFFLINE, "网络中断，本地继续采样")
        elif current == DeviceState.RUNNING_OFFLINE and self.mqtt.connected:
            self.store.retry_all()
            self.state.transition(DeviceState.RUNNING, "网络恢复，开始补传")
        elif current == DeviceState.SYNCING:
            active = self.active
            if active and active.get("end_command_id"):
                self._finish_remote_sync(active)
                return
            if active and self.store.pending_for_inspection(active["inspection_id"]) == 0:
                self.store.delete_meta("active_inspection")
                self.state.transition(DeviceState.IDLE, "同步完成")
                self.logger.info("巡检数据同步完成")

    def start_command_worker(self):
        if self._command_running:
            return
        self._command_running = True
        self._command_thread = threading.Thread(target=self._command_loop, name="InspectionCommands", daemon=True)
        self._command_thread.start()

    def stop_command_worker(self):
        self._command_running = False
        self._command_wakeup.set()
        if self._command_thread:
            self._command_thread.join()
        self._command_thread = None

    def _command_loop(self):
        while self._command_running:
            self._command_wakeup.wait(0.5)
            self._command_wakeup.clear()
            if self._replay_requested.is_set():
                self._replay_requested.clear()
                for command_id in self.store.final_command_ids():
                    self.replay_command(command_id)
            for payload in self.store.pending_commands():
                if not self._command_running:
                    break
                try:
                    self.process_command(payload)
                except Exception as exc:
                    self.logger.error("任务命令处理失败，将重试: {}".format(type(exc).__name__))

    def request_final_replay(self):
        """MQTT 回调只唤醒工作线程，不扫描历史或执行硬件动作。"""
        self._replay_requested.set()
        self._command_wakeup.set()

    def replay_command(self, command_id):
        evidence = self.store.command_evidence(command_id)
        for ack in evidence:
            self.store.replay_ack(ack, self.mqtt.topics.ack)

    def _command_ack(self, payload, status, phase, reason=None, summary=None):
        ack = {
            "type": "command_ack", "schema_version": "2.0",
            "command_id": payload["command_id"], "inspection_id": payload.get("inspection_id"),
            "device_id": self.config.device_id, "command": payload.get("command"),
            "status": status, "phase": phase, "reason_code": reason, "timestamp": utc_now(),
        }
        if summary is not None:
            ack["summary"] = summary
        return ack

    def process_command(self, payload):
        """工作线程调用；业务状态与 ACK 在落盘后才对外可见。"""
        with self.execution_lock:
            previous = self.store.command_result(payload["command_id"])
            if previous:
                self.replay_command(payload["command_id"])
                return previous
            reason = validate_command(payload, self.config.device_id, time.time())
            active = self.active
            if not reason and not self.bound:
                reason = "DEVICE_UNBOUND"
            if not reason and payload["command"] == "START_INSPECTION":
                if not getattr(self.config, "device_secret", True):
                    reason = "DEVICE_CREDENTIALS_MISSING"
                elif active or self.state.state != DeviceState.IDLE:
                    reason = "DEVICE_BUSY"
                else:
                    checks = self.preflight()
                    if not checks.ok:
                        reason = {
                            "bound": "DEVICE_UNBOUND", "cloud": "CLOUD_OFFLINE", "camera": "CAMERA_NOT_READY",
                            "yolo": "INFERENCE_NOT_READY", "gps_fix": "GPS_NO_FIX", "disk": "STORAGE_LOW",
                        }.get(checks.errors[0]["name"], "HARDWARE_NOT_READY")
                    elif self.store.pending_business_count():
                        reason = "PENDING_SYNC"
            if not reason and payload["command"] == "END_INSPECTION":
                if not active or active["inspection_id"] != payload["inspection_id"]:
                    reason = "INSPECTION_MISMATCH"
                elif (active.get("field_id") != payload["field_id"] or
                      active.get("field_version") != payload["field_version"]):
                    reason = "FIELD_SNAPSHOT_MISMATCH"
                elif self.state.state not in (DeviceState.RUNNING, DeviceState.RUNNING_OFFLINE):
                    reason = "INVALID_STATE"
            if reason:
                ack = self._command_ack(payload, "REJECTED", self.state.state, reason)
                self.store.commit_command(payload, ack, self.mqtt.topics.ack)
                self.logger.warning("任务命令拒绝: {}".format(reason))
                return ack

            if payload["command"] == "START_INSPECTION":
                active = dict((key, copy.deepcopy(payload[key])) for key in
                              ("inspection_id", "field_id", "field_version", "field_snapshot", "run_mode"))
                active.update({"phase": "RUNNING", "start_command_id": payload["command_id"],
                               "started_at": utc_now(), "sequence": 0, "samples": 0,
                               "targets": 0, "images": 0, "errors": 0, "data_provenance": "DEVICE"})
                ack = self._command_ack(payload, "ACCEPTED", "RUNNING")
                self.store.commit_command(payload, ack, self.mqtt.topics.ack, active)
                self.state.transition(DeviceState.RUNNING, "云端任务已接受", force=True)
            else:
                active["phase"] = "SYNCING"
                active["end_command_id"] = payload["command_id"]
                active["ended_at"] = utc_now()
                active["end_command"] = dict(payload)
                summary = {
                    "sampling_stopped": True, "last_data_id": active.get("last_data_id"),
                    "last_sequence": active.get("sequence") if active.get("samples") else None,
                    "sample_count": active.get("samples", 0),
                    "pending_sync_count": self.store.pending_data_for_inspection(active["inspection_id"]),
                }
                active["stop_summary"] = summary
                ack = self._command_ack(payload, "ACCEPTED", "SYNCING", summary=summary)
                self.store.commit_command(payload, ack, self.mqtt.topics.ack, active)
                self.state.transition(DeviceState.SYNCING, "停止采样，等待业务队列与最终确认", force=True)
            self.logger.info("任务命令 {} 已持久化接受".format(payload["command"]))
            return ack

    def _finish_remote_sync(self, active):
        if self.store.pending_data_for_inspection(active["inspection_id"]):
            return
        command_id = active["end_command_id"]
        result = self.store.command_result(command_id)
        if not result or result["status"] != "COMPLETED":
            summary = dict(active["stop_summary"])
            summary["pending_sync_count"] = 0
            ack = self._command_ack(active["end_command"], "COMPLETED", "COMPLETED", summary=summary)
            self.store.commit_command(active["end_command"], ack, self.mqtt.topics.ack, active)
            return
        if self.store.message_done("ack", command_id + ":COMPLETED"):
            # 保留任务及 command_id，重启/重连仍能再次投递最终通知。
            self.store.archive_inspection(active)
            self.state.transition(DeviceState.IDLE if self.bound else DeviceState.UNBOUND,
                                  "本地补传完成，最终 ACK 已获 Broker PUBACK；云端完成态以小程序为准", force=True)
        elif self.mqtt.connected and time.time() - self._last_final_replay >= 5:
            self.replay_command(command_id)
            self._last_final_replay = time.time()
