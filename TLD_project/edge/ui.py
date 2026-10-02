# -*- coding: utf-8 -*-
"""可缩放 Tkinter 桌面 UI；所有阻塞操作均派发到后台线程。"""

import calendar
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk


class EdgeUI(object):
    def __init__(self, runtime):
        self.runtime = runtime
        self.root = tk.Tk()
        self.root.title("TLD Jetson 边缘端")
        self.root.geometry("1100x720")
        self.root.minsize(820, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", self._leave_fullscreen)
        self._fullscreen = False
        self._closing = False
        self._pair_polling = False
        self._last_pair_poll = 0.0
        self._qr_image = None
        self._log_queue = queue.Queue()
        self.runtime.logger.callback_handler.add_callback(self._queue_log)
        self._build()

    def _build(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="TLD Jetson", font=("TkDefaultFont", 16, "bold")).pack(side="left")
        ttk.Button(top, text="全屏 F11", command=self._toggle_fullscreen).pack(side="right")
        self.summary_var = tk.StringVar(value="正在启动运行时…")
        ttk.Label(top, textvariable=self.summary_var).pack(side="right", padx=12)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.dashboard = ttk.Frame(self.notebook, padding=12)
        self.cloud_network = ttk.Frame(self.notebook, padding=12)
        self.pairing = ttk.Frame(self.notebook, padding=12)
        self.task = ttk.Frame(self.notebook, padding=12)
        self.ntrip = ttk.Frame(self.notebook, padding=12)
        self.logs = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.dashboard, text="设备状态")
        self.notebook.add(self.cloud_network, text="云端网络")
        self.notebook.add(self.pairing, text="动态配对")
        self.notebook.add(self.task, text="巡检任务")
        self.notebook.add(self.ntrip, text="NTRIP")
        self.notebook.add(self.logs, text="日志")
        self._build_dashboard()
        self._build_cloud_network()
        self._build_pairing()
        self._build_task()
        self._build_ntrip()
        self._build_logs()

    def _build_dashboard(self):
        self.status_vars = {}
        labels = [
            ("device", "设备 ID"), ("binding", "绑定"), ("owner", "用户昵称"),
            ("network", "网络/云端"), ("gps", "GPS / RTK"),
            ("camera", "Camera"), ("yolo", "YOLO"),
            ("sensors", "环境传感器"), ("disk", "磁盘"), ("sync", "同步队列"),
        ]
        for index, (key, label) in enumerate(labels):
            row, column = divmod(index, 2)
            card = ttk.LabelFrame(self.dashboard, text=label, padding=10)
            card.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")
            value = tk.StringVar(value="—")
            self.status_vars[key] = value
            ttk.Label(card, textvariable=value, font=("TkDefaultFont", 11)).pack(anchor="w")
        self.dashboard.columnconfigure(0, weight=1)
        self.dashboard.columnconfigure(1, weight=1)
        for row in range(5):
            self.dashboard.rowconfigure(row, weight=1)

    def _build_cloud_network(self):
        current = self.runtime.network_form()
        self.network_scheme = current.get("scheme", "http")
        self.network_entries = {}
        fields = [
            ("host", "开发电脑 IPv4 / 主机名", False),
            ("http_port", "HTTP 端口", False),
            ("mqtt_port", "MQTT 端口", False),
            ("mqtt_username", "MQTT 用户名", False),
            ("mqtt_password", "MQTT 密码", True),
        ]
        defaults = {
            "host": current.get("host", ""),
            "http_port": str(current.get("http_port", 8000)),
            "mqtt_port": str(current.get("mqtt_port", 1883)),
            "mqtt_username": current.get("mqtt_username", ""),
            # 密码永不从配置读回 UI。
            "mqtt_password": "",
        }
        for row, (key, label, secret) in enumerate(fields):
            ttk.Label(self.cloud_network, text=label).grid(
                row=row, column=0, sticky="w", padx=4, pady=5
            )
            entry = ttk.Entry(self.cloud_network, show="*" if secret else "")
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
            entry.insert(0, defaults[key])
            self.network_entries[key] = entry
        self.cloud_network.columnconfigure(1, weight=1)
        password_note = "已保存密码；留空保持不变" if current.get("password_saved") else "尚未保存密码"
        self.network_password_note = tk.StringVar(value=password_note)
        ttk.Label(self.cloud_network, textvariable=self.network_password_note).grid(
            row=4, column=2, sticky="w", padx=4
        )

        buttons = ttk.Frame(self.cloud_network)
        buttons.grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
        ttk.Button(buttons, text="保存网络配置", command=self._save_network).pack(side="left", padx=4)
        ttk.Button(buttons, text="测试 HTTP", command=self._test_http_network).pack(side="left", padx=4)
        ttk.Button(buttons, text="测试 MQTT", command=self._test_mqtt_network).pack(side="left", padx=4)

        self.network_backend_var = tk.StringVar(
            value="后端 URL: {}".format(current.get("backend_url") or "未配置")
        )
        self.network_save_var = tk.StringVar(value="保存状态: 本轮尚未保存")
        self.network_http_var = tk.StringVar(value="HTTP: 尚未测试")
        self.network_mqtt_var = tk.StringVar(value="MQTT: 尚未测试")
        self.network_live_var = tk.StringVar(value="实时 MQTT: 未连接")
        for offset, variable in enumerate((
                self.network_backend_var, self.network_save_var,
                self.network_http_var, self.network_mqtt_var, self.network_live_var)):
            ttk.Label(self.cloud_network, textvariable=variable).grid(
                row=6 + offset, column=0, columnspan=3, sticky="w", padx=4, pady=3
            )
        ttk.Label(
            self.cloud_network,
            text="保存成功不代表连接成功；请分别执行 HTTP 与 MQTT 测试。任务运行、同步或配对期间禁止切换。",
            wraplength=900,
        ).grid(row=11, column=0, columnspan=3, sticky="w", padx=4, pady=12)

    def _build_pairing(self):
        self.pair_state_var = tk.StringVar(value="未申请配对会话")
        ttk.Label(self.pairing, textvariable=self.pair_state_var, font=("TkDefaultFont", 12)).pack(pady=6)
        self.qr_label = ttk.Label(self.pairing, anchor="center")
        self.qr_label.pack(fill="both", expand=True, pady=8)
        buttons = ttk.Frame(self.pairing)
        buttons.pack()
        ttk.Button(buttons, text="生成/刷新二维码", command=self._create_pairing).pack(side="left", padx=5)
        ttk.Button(buttons, text="取消显示", command=self._cancel_pairing).pack(side="left", padx=5)
        ttk.Label(
            self.pairing,
            text="已绑定设备只显示云端用户昵称；解绑请在 Web 或微信小程序执行。",
        ).pack(pady=10)

    def _build_task(self):
        form = ttk.Frame(self.task)
        form.pack(fill="x")
        ttk.Label(form, text="任务名称（可留空）").grid(row=0, column=0, sticky="w", pady=4)
        self.task_name = ttk.Entry(form)
        self.task_name.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(form, text="地点备注（当前仅本地保存）").grid(row=1, column=0, sticky="w", pady=4)
        self.location_note = ttk.Entry(form)
        self.location_note.grid(row=1, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)
        buttons = ttk.Frame(self.task)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="启动前检查", command=self._show_preflight).pack(side="left", padx=4)
        ttk.Button(buttons, text="确认并开始", command=self._start_task).pack(side="left", padx=4)
        ttk.Button(buttons, text="本地结束任务", command=self._end_task).pack(side="left", padx=4)
        self.task_state_var = tk.StringVar(value="任务未运行")
        ttk.Label(self.task, textvariable=self.task_state_var, font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=8)
        self.running_text = tk.Text(self.task, height=18, state="disabled", wrap="word")
        self.running_text.pack(fill="both", expand=True)

    def _build_ntrip(self):
        self.ntrip_entries = {}
        fields = [
            ("server", "服务器", False), ("port", "端口", False),
            ("mountpoint", "Mountpoint", False), ("username", "用户名", False),
            ("password", "密码", True),
        ]
        for row, (key, label, secret) in enumerate(fields):
            ttk.Label(self.ntrip, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=5)
            entry = ttk.Entry(self.ntrip, show="*" if secret else "")
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
            self.ntrip_entries[key] = entry
        self.ntrip.columnconfigure(1, weight=1)
        self.ntrip_entries["server"].insert(0, self.runtime.config.ntrip_server)
        self.ntrip_entries["port"].insert(0, str(self.runtime.config.ntrip_port))
        self.ntrip_entries["mountpoint"].insert(0, self.runtime.config.ntrip_mountpoint)
        self.ntrip_entries["username"].insert(0, self.runtime.config.ntrip_username)
        buttons = ttk.Frame(self.ntrip)
        buttons.grid(row=len(fields), column=0, columnspan=2, pady=12)
        ttk.Button(buttons, text="保存并重启 NTRIP", command=self._save_ntrip).pack(side="left", padx=4)
        ttk.Button(buttons, text="连接测试", command=self._test_ntrip).pack(side="left", padx=4)
        ttk.Button(buttons, text="清除凭据", command=self._clear_ntrip).pack(side="left", padx=4)
        self.ntrip_result = tk.StringVar(value="NTRIP 与 GPS Fix/RTK 状态分别显示。")
        ttk.Label(self.ntrip, textvariable=self.ntrip_result).grid(row=len(fields) + 1, column=0, columnspan=2)

    def _build_logs(self):
        self.log_text = tk.Text(self.logs, state="disabled", wrap="word")
        scroll = ttk.Scrollbar(self.logs, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _queue_log(self, rendered, level):
        self._log_queue.put(rendered)

    def _background(self, function, success=None, failure_title="操作失败", complete=None):
        def runner():
            try:
                result = function()
                if success is not None and not self._closing:
                    self.root.after(0, lambda: success(result))
            except Exception as exc:
                if not self._closing:
                    message = str(exc)
                    self.root.after(0, lambda: messagebox.showerror(failure_title, message))
            finally:
                if complete is not None and not self._closing:
                    self.root.after(0, complete)
        threading.Thread(target=runner, name="UiAction", daemon=True).start()

    def _create_pairing(self):
        self.pair_state_var.set("正在申请配对会话…")
        self._background(self.runtime.create_pairing, self._show_qr, "配对失败")

    def _show_qr(self, session):
        path = session.get("qr_path")
        self._qr_image = tk.PhotoImage(file=path)
        width = self._qr_image.width()
        if width > 420:
            factor = max(1, int(width / 420))
            self._qr_image = self._qr_image.subsample(factor, factor)
        self.qr_label.configure(image=self._qr_image)
        self.pair_state_var.set("有效期至 {}；等待小程序确认".format(session.get("expires_at", "—")))

    def _cancel_pairing(self):
        self.runtime.cancel_pairing()
        self._qr_image = None
        self.qr_label.configure(image="")
        self.pair_state_var.set("本机已取消显示；服务端会话按有效期自动失效")

    def _show_preflight(self):
        result = self.runtime.preflight()
        lines = []
        for item in result.checks:
            marker = "通过" if item["passed"] else ("失败" if item["required"] else "警告")
            lines.append("{}: {} ({})".format(item["name"], marker, item["detail"]))
        messagebox.showinfo("启动前检查", "\n".join(lines))

    def _start_task(self):
        check = self.runtime.preflight()
        if not check.ok:
            self._show_preflight()
            return
        warning_text = "\n".join(item["name"] + ": " + item["detail"] for item in check.warnings)
        prompt = "确认在 Jetson 本地开始巡检？"
        if warning_text:
            prompt += "\n\n非阻塞警告：\n" + warning_text
        if not messagebox.askyesno("开始巡检", prompt):
            return
        name = self.task_name.get()
        note = self.location_note.get()
        self.task_state_var.set("STARTING：等待云端 ACK…")
        self._background(lambda: self.runtime.start_inspection(name, note), None, "启动失败")

    def _end_task(self):
        if messagebox.askyesno("结束巡检", "确认立即停止产生新采样并进入同步？"):
            self._background(self.runtime.end_inspection, None, "结束失败")

    def _ntrip_values(self):
        return dict((key, entry.get()) for key, entry in self.ntrip_entries.items())

    def _network_values(self):
        return dict((key, entry.get()) for key, entry in self.network_entries.items())

    def _save_network(self):
        values = self._network_values()
        self.network_save_var.set("保存状态: 正在校验并保存…")
        self._background(
            lambda: self.runtime.save_network(
                values["host"], values["http_port"], values["mqtt_port"],
                values["mqtt_username"], values["mqtt_password"], self.network_scheme
            ), self._network_saved, "云端网络保存失败"
        )

    def _network_saved(self, result):
        self.network_entries["mqtt_password"].delete(0, "end")
        self.network_password_note.set(
            "已保存密码；留空保持不变" if result.get("password_saved") else "尚未保存密码"
        )
        self.network_backend_var.set("后端 URL: {}".format(result.get("backend_url", "未配置")))
        self.network_save_var.set("保存状态: {}".format(result.get("message", "已保存")))

    def _test_http_network(self):
        values = self._network_values()
        self.network_http_var.set("HTTP: 正在请求 /api/health…")
        self._background(
            lambda: self.runtime.test_http_network(
                values["host"], values["http_port"], self.network_scheme
            ), lambda result: self.network_http_var.set(
                "HTTP [{}]: {}".format(result.get("category"), result.get("message"))
            ), "HTTP 测试失败"
        )

    def _test_mqtt_network(self):
        values = self._network_values()
        self.network_mqtt_var.set("MQTT: 正在等待真实 CONNACK…")
        self._background(
            lambda: self.runtime.test_mqtt_network(
                values["host"], values["mqtt_port"],
                values["mqtt_username"], values["mqtt_password"]
            ), lambda result: self.network_mqtt_var.set(
                "MQTT [{}]: {}".format(result.get("category"), result.get("message"))
            ), "MQTT 测试失败"
        )

    def _save_ntrip(self):
        values = self._ntrip_values()
        self._background(
            lambda: self.runtime.save_ntrip(
                values["server"], values["port"], values["mountpoint"],
                values["username"], values["password"], True
            ), lambda result: self.ntrip_result.set("配置已保存，NTRIP Client 已重启"),
            "NTRIP 保存失败"
        )

    def _test_ntrip(self):
        values = self._ntrip_values()
        self.ntrip_result.set("正在测试 NTRIP 握手…")
        self._background(
            lambda: self.runtime.test_ntrip(
                values["server"], values["port"], values["mountpoint"],
                values["username"], values["password"]
            ), lambda result: self.ntrip_result.set("NTRIP 握手成功"), "NTRIP 测试失败"
        )

    def _clear_ntrip(self):
        if messagebox.askyesno("清除 NTRIP", "确认清除本机 NTRIP 凭据？"):
            self._background(self.runtime.clear_ntrip, lambda result: self._cleared_ntrip(), "清除失败")

    def _cleared_ntrip(self):
        for entry in self.ntrip_entries.values():
            entry.delete(0, "end")
        self.ntrip_result.set("NTRIP 凭据已清除")

    def _toggle_fullscreen(self, event=None):
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)

    def _leave_fullscreen(self, event=None):
        self._fullscreen = False
        self.root.attributes("-fullscreen", False)

    @staticmethod
    def _entry_value(cache, name):
        entry = cache.get(name)
        return entry.get("value") if entry and entry.get("valid") else {}

    def _refresh(self):
        if self._closing:
            return
        snapshot = self.runtime.snapshot()
        health = snapshot["health"]
        queues = snapshot["queues"]
        cache = snapshot["cache"]
        location = self._entry_value(cache, "location")
        environment = self._entry_value(cache, "environment")
        detection = self._entry_value(cache, "detection")
        status = self._entry_value(cache, "device_status")
        self.summary_var.set("{} · {}".format(snapshot["state"], snapshot["state_reason"]))
        self.status_vars["device"].set(snapshot["device_id"])
        self.status_vars["binding"].set("已绑定" if snapshot["bound"] else "未绑定")
        self.status_vars["owner"].set(snapshot["owner_nickname"] or "—")
        network = snapshot.get("network") or {}
        http_state = (network.get("http") or {}).get("category", "not_tested")
        self.status_vars["network"].set("HTTP {} / MQTT {}".format(
            http_state, "已连接" if snapshot["mqtt_connected"] else "未连接"
        ))
        self.network_backend_var.set("后端 URL: {}".format(network.get("backend_url") or "未配置"))
        self.network_live_var.set(
            "实时 MQTT: {}".format("已连接" if snapshot["mqtt_connected"] else "未连接")
        )
        self.status_vars["gps"].set("{} · NTRIP {}".format(
            location.get("fix", "无 Fix"), "已连接" if health.get("ntrip_connected") else "未连接"
        ))
        self.status_vars["camera"].set("正常" if health.get("camera") else "严重异常")
        self.status_vars["yolo"].set("正常" if health.get("yolo") else "严重异常")
        sensors = health.get("sensors") or {}
        self.status_vars["sensors"].set("光照 {} / SCD41 {}".format(
            "正常" if sensors.get("light") else "异常", "正常" if sensors.get("air") else "异常"
        ))
        self.status_vars["disk"].set("使用率 {}%".format(status.get("storage_usage", "—")))
        self.status_vars["sync"].set("消息 {} / 图片 {}".format(queues["messages"], queues["images"]))
        active = snapshot.get("active") or {}
        elapsed = 0
        if active.get("started_at"):
            elapsed = max(0, int(time.time() - self._parse_time(active["started_at"])))
        self.task_state_var.set("{} · 时长 {} 秒".format(snapshot["state"], elapsed))
        details = (
            "位置: {lat}, {lon}  Fix: {fix}\n"
            "环境: 温度 {temp}°C  湿度 {humidity}%  CO2 {co2}  光照 {light}\n"
            "最新检测: {detections}\n"
            "累计采样: {samples}  目标数: {targets}  图片: {images}\n"
            "待同步: {pending}  异常数: {errors}\n"
        ).format(
            lat=location.get("latitude"), lon=location.get("longitude"), fix=location.get("fix"),
            temp=environment.get("temperature"), humidity=environment.get("humidity"),
            co2=environment.get("co2"), light=environment.get("lux"),
            detections=len(detection or []), samples=active.get("samples", 0),
            targets=active.get("targets", 0), images=active.get("images", 0),
            pending=queues["total"], errors=active.get("errors", 0),
        )
        self.running_text.configure(state="normal")
        self.running_text.delete("1.0", "end")
        self.running_text.insert("end", details)
        self.running_text.configure(state="disabled")
        while True:
            try:
                line = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        if snapshot["state"] == "PAIRING" and time.time() - self._last_pair_poll >= 2.0 and not self._pair_polling:
            self._pair_polling = True
            self._last_pair_poll = time.time()
            def done(result):
                if result and str(result.get("status", "")).upper() in ("CONFIRMED", "BOUND", "CONSUMED"):
                    self._qr_image = None
                    self.qr_label.configure(image="")
                    self.pair_state_var.set("配对成功")
            self._background(
                self.runtime.pairing_status, done, "配对状态查询失败",
                complete=lambda: setattr(self, "_pair_polling", False)
            )
        self.root.after(500, self._refresh)

    @staticmethod
    def _parse_time(value):
        try:
            import datetime
            parsed = datetime.datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")
            return calendar.timegm(parsed.timetuple())
        except Exception:
            return time.time()

    def _close(self):
        self._closing = True
        self.root.destroy()

    def run(self):
        threading.Thread(target=self.runtime.start, name="RuntimeStartup", daemon=True).start()
        self.root.after(300, self._refresh)
        try:
            self.root.mainloop()
        finally:
            self.runtime.stop()
