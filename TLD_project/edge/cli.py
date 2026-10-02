# -*- coding: utf-8 -*-
"""Jetson 默认命令行入口；配置与配对模式不启动重型硬件。"""

import getpass
import ipaddress
import json
import time

from .network_config import build_backend_url, normalize_remote_host, validate_port
from .logging_utils import console_print as print


def startup_network_wizard(runtime):
    """任何连接/CUDA 初始化之前确认地址；恢复任务只能确认原地址。"""
    print("请填写运行云端服务的电脑局域网 IPv4，不是 Jetson 自身 IP、手机网关或 localhost。")
    print("HTTPS/TLS 配置保持原样；任务/补传期间只能确认原地址，不能更换。")
    while True:
        current = runtime.network_form()
        try:
            host = normalize_remote_host(_prompt_default("运行云端服务的电脑局域网 IPv4", current.get("host", "")))
            # 既有公网 HTTPS 域名继续兼容；LAN 首次配置要求 IPv4。
            if current.get("scheme") != "https":
                ipaddress.IPv4Address(host)
            http_port = validate_port(_prompt_default("HTTP 端口", current.get("http_port", 8000)), "HTTP 端口")
            mqtt_port = validate_port(_prompt_default("MQTT 端口（例如 18883）", current.get("mqtt_port", 1883)), "MQTT 端口")
            mqtt_host = host
            if current.get("scheme") == "https" and runtime.config.mqtt_host != current.get("host"):
                mqtt_host = normalize_remote_host(_prompt_default("MQTT 地址（保留已配置 TLS Broker）", runtime.config.mqtt_host))
            username = _prompt_default("MQTT 用户名（留空保留）", current.get("mqtt_username", ""))
            password = getpass.getpass("MQTT 密码（不回显，留空保留）: ")
            target = build_backend_url(host, http_port, current.get("scheme", "http"))
            changed = (target != runtime.config.backend_url or mqtt_host != runtime.config.mqtt_host or
                       mqtt_port != runtime.config.mqtt_port or username != runtime.config.mqtt_username or
                       bool(password and password != runtime.config.mqtt_password))
            if changed:
                runtime.save_network(host, http_port, mqtt_port, username, password, current.get("scheme", "http"), mqtt_host=mqtt_host)
            http = runtime.test_http_network(host, http_port, current.get("scheme", "http"))
            mqtt = runtime.test_mqtt_network(mqtt_host, mqtt_port, username, password)
            for label, result in (("HTTP /api/health", http), ("MQTT CONNACK", mqtt)):
                print("[{}] {}: {}".format(label, result["category"], result["message"]))
            if http["ok"] and mqtt["ok"]:
                return True
            print("连接拒绝通常是端口/服务/防火墙问题；超时可能是网络不可达；auth_failed 为认证失败。")
            # 已接受的离线任务不能因云端故障被启动向导暂停采集。
            choices = "R 修改/重试，0 退出"
            if runtime.lifecycle.active and not changed:
                choices += "，O 按原配置离线恢复已有任务（不接受新 START）"
            action = input(choices + ": ").strip().upper()
            if action == "0":
                return False
            if action == "O" and runtime.lifecycle.active and not changed:
                return True
        except (ValueError, RuntimeError) as exc:
            print("配置未通过: {}".format(exc))


def _print_snapshot(runtime):
    snapshot = runtime.snapshot()
    output = {
        "device_id": snapshot["device_id"],
        "state": snapshot["state"],
        "reason": snapshot["state_reason"],
        "bound": snapshot["bound"],
        "owner_nickname": snapshot["owner_nickname"],
        "mqtt_connected": snapshot["mqtt_connected"],
        "network": snapshot["network"],
        "queues": snapshot["queues"],
        "health": snapshot["health"],
        "active": dict((key, snapshot["active"].get(key)) for key in
                       ("inspection_id", "field_id", "field_version", "phase", "sequence", "samples", "images"))
                  if snapshot["active"] else None,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _pair(runtime):
    session = runtime.create_pairing()
    _print_terminal_qr(runtime, session)
    print("二维码路径: {}".format(session["qr_path"]))
    print("如终端二维码不便扫描，可执行: xdg-open '{}'".format(session["qr_path"]))
    print("有效期: {}".format(session["expires_at"]))
    print("等待小程序确认，Ctrl+C 可返回菜单。")
    try:
        while True:
            result = runtime.pairing_status() or {}
            status = result.get("status", "PENDING")
            print("配对状态: {}".format(status))
            if str(status).upper() in ("CONFIRMED", "CONSUMED", "BOUND", "EXPIRED", "CANCELLED"):
                return
            time.sleep(2.0)
    except KeyboardInterrupt:
        runtime.cancel_pairing()
        print("已停止本机轮询。")


def _print_terminal_qr(runtime, session):
    """尽力把配对二维码渲染到终端；失败时仍保留 PNG。"""
    try:
        import qrcode
        payload = runtime.http.pairing_payload(runtime.config.device_id, session)
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        qr = qrcode.QRCode(border=1)
        qr.add_data(rendered)
        qr.make(fit=True)
        print("\n请使用已登录的小程序扫描下方设备配对码：\n")
        qr.print_ascii(tty=True, invert=True)
        print("")
    except Exception:
        print("终端二维码渲染不可用，请打开已生成的 PNG 文件。")


def _preflight(runtime):
    result = runtime.preflight()
    for item in result.checks:
        marker = "PASS" if item["passed"] else ("FAIL" if item["required"] else "WARN")
        print("[{}] {}: {}".format(marker, item["name"], item["detail"]))


def _prompt_default(label, default):
    rendered = "{} [{}]: ".format(label, default) if default not in (None, "") else "{}: ".format(label)
    value = input(rendered).strip()
    return value if value else str(default or "")


def _configure_network(runtime):
    current = runtime.network_form()
    host = _prompt_default("开发电脑 IPv4/主机名", current.get("host", ""))
    http_port = _prompt_default("HTTP 端口", current.get("http_port", 8000))
    mqtt_port = _prompt_default("MQTT 端口", current.get("mqtt_port", 1883))
    username = _prompt_default("MQTT 用户名", current.get("mqtt_username", ""))
    password = getpass.getpass("MQTT 密码（不回显，留空保留已保存值）: ")
    result = runtime.save_network(
        host, http_port, mqtt_port, username, password, current.get("scheme", "http")
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("注意：保存成功不代表连接成功，请分别执行 HTTP 与 MQTT 测试。")


def _configure_device_secret(runtime):
    status = runtime.credential_status()
    print("设备 ID: {}".format(status["device_id"]))
    print("永久密钥状态: {}".format("已配置" if status["device_secret_present"] else "未配置"))
    secret = getpass.getpass("粘贴云端为该设备生成的永久密钥（输入不回显）: ").strip()
    if not secret:
        print("未输入，保持原配置不变。")
        return
    result = runtime.save_device_secret(secret)
    print("设备永久密钥已保存；{}".format(result.get("message", "网络客户端已更新")))


def _test_http_network(runtime):
    current = runtime.network_form()
    host = _prompt_default("开发电脑 IPv4/主机名", current.get("host", ""))
    port = _prompt_default("HTTP 端口", current.get("http_port", 8000))
    result = runtime.test_http_network(host, port, current.get("scheme", "http"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _test_mqtt_network(runtime):
    current = runtime.network_form()
    host = _prompt_default("开发电脑 IPv4/主机名", current.get("host", ""))
    port = _prompt_default("MQTT 端口", current.get("mqtt_port", 1883))
    username = _prompt_default("MQTT 用户名", current.get("mqtt_username", ""))
    password = getpass.getpass("MQTT 密码（不回显，留空使用已保存值）: ")
    result = runtime.test_mqtt_network(host, port, username, password)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _configure_ntrip(runtime):
    server = input("NTRIP 服务器: ").strip()
    port = input("端口 [2101]: ").strip() or "2101"
    mountpoint = input("Mountpoint: ").strip()
    username = input("用户名: ").strip()
    password = getpass.getpass("密码（不回显）: ")
    runtime.save_ntrip(server, port, mountpoint, username, password, True)
    print("NTRIP 配置已保存；通信配置模式下将在完整硬件运行时启动后生效。")


def _test_ntrip(runtime):
    server = input("NTRIP 服务器: ").strip()
    port = input("端口 [2101]: ").strip() or "2101"
    mountpoint = input("Mountpoint: ").strip()
    username = input("用户名: ").strip()
    password = getpass.getpass("密码（不回显）: ")
    runtime.test_ntrip(server, port, mountpoint, username, password)
    print("NTRIP 握手成功。")


def run_cli(runtime, start_hardware=False):
    actions = {
        "1": lambda: _print_snapshot(runtime),
        "2": lambda: _pair(runtime),
        "3": lambda: _configure_device_secret(runtime),
        "4": lambda: _configure_network(runtime),
        "5": lambda: _test_http_network(runtime),
        "6": lambda: _test_mqtt_network(runtime),
    }
    if start_hardware:
        actions.update({
            "10": lambda: _preflight(runtime),
        })
    try:
        if not startup_network_wizard(runtime):
            return
        runtime.start(start_hardware=bool(start_hardware))
        mode = "完整硬件" if start_hardware else "通信配置"
        print("\nTLD Jetson 命令行（{}模式）".format(mode))
        print("任务由小程序发起，Jetson 等待云端命令；本地菜单不创建巡检。")
        if not start_hardware:
            print("当前不会启动 Camera、YOLO、GPS 或传感器。")
            if getattr(runtime, "lifecycle", None) and runtime.lifecycle.active:
                print("已有任务与缓存已保留；通信模式不恢复采样。需采样请退出后运行 python3 main.py --hardware。")
        while True:
            print("\n1 状态  2 生成动态配对二维码  3 配置设备永久密钥")
            print("4 配置云端网络  5 测试HTTP  6 测试MQTT")
            if start_hardware:
                print("10 启动前检查（普通 GPS Fix 即可；本轮不配置网络 RTK）")
            print("0 退出")
            choice = input("选择: ").strip()
            if choice == "0":
                break
            action = actions.get(choice)
            if action is None:
                print("无效选择")
                continue
            try:
                result = action()
                if isinstance(result, dict):
                    print(json.dumps(result, ensure_ascii=False, indent=2))
            except Exception as exc:
                print("操作失败: {}".format(exc))
    except (KeyboardInterrupt, EOFError):
        print("\n正在退出…")
    finally:
        runtime.stop()
