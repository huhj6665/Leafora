# -*- coding: utf-8 -*-
"""局域网云端配置校验与独立连通性诊断。

诊断只执行 HTTP health 请求和 MQTT CONNECT/CONNACK，不发布业务消息，
也不会把用户名或密码放入返回值、异常文本或日志。
"""

import ipaddress
import errno
import re
import socket
import threading
import uuid
from urllib import error, parse, request

from .state import DeviceState


class NetworkConfigError(RuntimeError):
    pass


BLOCKED_NETWORK_STATES = set([
    DeviceState.PAIRING,
    DeviceState.STARTING,
    DeviceState.RUNNING,
    DeviceState.RUNNING_OFFLINE,
    DeviceState.ENDING,
    DeviceState.SYNCING,
])


def ensure_network_change_allowed(state):
    """任务或配对流程活跃时禁止切换云端网络。"""
    if state in BLOCKED_NETWORK_STATES:
        raise NetworkConfigError(
            "当前状态 {} 禁止切换云端网络；请回到空闲状态后重试".format(state)
        )
    return True


def normalize_remote_host(value):
    """校验远端 IPv4/主机名，拒绝本机环回与 URL 形式输入。"""
    host = str(value or "").strip()
    if not host:
        raise NetworkConfigError("开发电脑 IPv4/主机名不能为空")
    lowered = host.lower().rstrip(".")
    if lowered in ("localhost", "localhost.localdomain") or lowered.endswith(".localhost"):
        raise NetworkConfigError("远端地址不能使用 localhost")
    if any(character.isspace() for character in host):
        raise NetworkConfigError("远端地址不能包含空白字符")
    if "://" in host or any(character in host for character in ("/", "\\", "?", "#", "@", ":")):
        raise NetworkConfigError("请输入 IPv4 或主机名，不要输入 URL、端口或路径")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if address.version != 4:
            raise NetworkConfigError("当前手工配置仅支持 IPv4 或主机名")
        if address.is_loopback:
            raise NetworkConfigError("远端地址不能使用 127.0.0.0/8 环回地址")
        if address.is_unspecified:
            raise NetworkConfigError("远端地址不能使用 0.0.0.0")
        return str(address)

    # 只由数字和点组成时，应视为写错的 IPv4，而不是合法主机名。
    if re.match(r"^[0-9.]+$", host):
        raise NetworkConfigError("IPv4 地址格式无效")
    if len(lowered) > 253:
        raise NetworkConfigError("主机名过长")
    labels = lowered.split(".")
    label_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    if any(not label_pattern.match(label) for label in labels):
        raise NetworkConfigError("主机名格式无效")
    return lowered


def validate_port(value, label):
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise NetworkConfigError("{}必须是 1-65535 的整数".format(label))
    if port < 1 or port > 65535:
        raise NetworkConfigError("{}必须是 1-65535 的整数".format(label))
    return port


def build_backend_url(host, http_port, scheme="http"):
    normalized = normalize_remote_host(host)
    port = validate_port(http_port, "HTTP 端口")
    scheme = str(scheme or "http").lower()
    if scheme not in ("http", "https"):
        raise NetworkConfigError("BACKEND_URL 仅支持 http 或 https")
    default_port = 443 if scheme == "https" else 80
    suffix = "" if port == default_port else ":{}".format(port)
    return "{}://{}{}".format(scheme, normalized, suffix)


def network_form_values(config):
    """从完整 BACKEND_URL 提取 UI 所需字段，不返回任何密码。"""
    host = config.mqtt_host or ""
    http_port = 8000
    scheme = "http"
    if config.backend_url:
        parsed = parse.urlparse(config.backend_url)
        if parsed.hostname:
            host = parsed.hostname
        scheme = parsed.scheme or scheme
        try:
            parsed_port = parsed.port
        except ValueError:
            parsed_port = None
        if parsed_port:
            http_port = parsed_port
        elif scheme == "https":
            http_port = 443
        elif scheme == "http":
            http_port = 80
    return {
        "host": host,
        "http_port": http_port,
        "mqtt_port": config.mqtt_port,
        "mqtt_username": config.mqtt_username,
        "backend_url": config.backend_url,
        "scheme": scheme,
        "password_saved": bool(config.mqtt_password),
    }


def _diagnostic(ok, category, message, **extra):
    result = {"ok": bool(ok), "category": category, "message": message}
    result.update(extra)
    return result


def diagnose_http_health(base_url, timeout_s=5.0, opener=None):
    """GET ``/api/health``；不附带设备认证或业务数据。"""
    base_url = str(base_url or "").strip().rstrip("/")
    try:
        parsed = parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise NetworkConfigError("BACKEND_URL 格式无效")
        normalize_remote_host(parsed.hostname)
        if parsed.port is not None:
            validate_port(parsed.port, "HTTP 端口")
    except (NetworkConfigError, ValueError):
        return _diagnostic(False, "invalid_address", "HTTP 地址无效")

    target = base_url + "/api/health"
    req = request.Request(target, headers={"Accept": "application/json"})
    open_request = opener or request.urlopen
    try:
        response = open_request(req, timeout=float(timeout_s))
        try:
            status = int(response.getcode())
            response.read(4096)
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            return _diagnostic(False, "auth_failed", "HTTP 健康检查被认证/权限拒绝", status_code=int(exc.code))
        return _diagnostic(
            False, "http_error", "HTTP 服务可达，但健康检查返回 {}".format(exc.code),
            status_code=int(exc.code),
        )
    except socket.timeout:
        return _diagnostic(False, "timeout", "HTTP 健康检查超时")
    except error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout):
            return _diagnostic(False, "timeout", "HTTP 健康检查超时")
        if isinstance(reason, ConnectionRefusedError):
            return _diagnostic(False, "refused", "HTTP 连接被拒绝")
        if isinstance(reason, socket.gaierror):
            return _diagnostic(False, "invalid_address", "HTTP 主机名无法解析")
        if isinstance(reason, OSError) and reason.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            return _diagnostic(False, "network_unreachable", "HTTP 网络/主机不可达")
        return _diagnostic(False, "connection_failed", "HTTP 连接失败")
    except ConnectionRefusedError:
        return _diagnostic(False, "refused", "HTTP 连接被拒绝")
    except socket.gaierror:
        return _diagnostic(False, "invalid_address", "HTTP 主机名无法解析")
    except OSError as exc:
        if exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            return _diagnostic(False, "network_unreachable", "HTTP 网络/主机不可达")
        return _diagnostic(False, "connection_failed", "HTTP 连接失败")
    if 200 <= status < 300:
        return _diagnostic(True, "reachable", "HTTP 健康检查通过", status_code=status)
    return _diagnostic(
        False, "http_error", "HTTP 服务可达，但健康检查返回 {}".format(status),
        status_code=status,
    )


def _probe_tcp(host, port, timeout_s):
    connection = socket.create_connection((host, port), timeout=float(timeout_s))
    connection.close()


def diagnose_mqtt(host, port, username, password, use_tls=False,
                  timeout_s=5.0, client_factory=None, tcp_probe=None):
    """执行真实 TCP 与 MQTT CONNACK 诊断，不订阅、不发布。"""
    try:
        host = normalize_remote_host(host)
        port = validate_port(port, "MQTT 端口")
    except NetworkConfigError:
        return _diagnostic(False, "invalid_address", "MQTT 地址无效")

    try:
        (tcp_probe or _probe_tcp)(host, port, timeout_s)
    except socket.timeout:
        return _diagnostic(False, "timeout", "MQTT TCP 连接超时")
    except ConnectionRefusedError:
        return _diagnostic(False, "refused", "MQTT TCP 连接被拒绝")
    except socket.gaierror:
        return _diagnostic(False, "invalid_address", "MQTT 主机名无法解析")
    except OSError as exc:
        if exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            return _diagnostic(False, "network_unreachable", "MQTT 网络/主机不可达")
        return _diagnostic(False, "connection_failed", "MQTT TCP 连接失败")

    if client_factory is None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return _diagnostic(False, "dependency_missing", "缺少 paho-mqtt 依赖")

        def client_factory(client_id):
            return mqtt.Client(client_id=client_id, clean_session=True)

    connected = threading.Event()
    outcome = {}
    client = None

    def on_connect(client_object, userdata, flags, rc):
        code = int(rc)
        if code == 0:
            outcome.update(_diagnostic(True, "connected", "MQTT 认证连接成功", connack=code))
        elif code in (4, 5):
            outcome.update(_diagnostic(False, "auth_failed", "MQTT 用户名或密码认证失败", connack=code))
        else:
            outcome.update(_diagnostic(False, "connack_rejected", "MQTT CONNACK 拒绝连接", connack=code))
        connected.set()

    def on_connect_fail(client_object, userdata):
        outcome.update(_diagnostic(False, "connection_failed", "MQTT 建立会话失败"))
        connected.set()

    try:
        client_id = "TLD-diagnostic-{}".format(uuid.uuid4().hex[:12])
        client = client_factory(client_id)
        if username:
            client.username_pw_set(str(username), str(password) if password else None)
        if use_tls:
            client.tls_set()
        client.on_connect = on_connect
        if hasattr(client, "on_connect_fail"):
            client.on_connect_fail = on_connect_fail
        client.connect_async(host, port, keepalive=15)
        client.loop_start()
        if not connected.wait(float(timeout_s)):
            return _diagnostic(False, "timeout", "等待 MQTT CONNACK 超时")
        return dict(outcome)
    except socket.timeout:
        return _diagnostic(False, "timeout", "MQTT 连接超时")
    except ConnectionRefusedError:
        return _diagnostic(False, "refused", "MQTT 连接被拒绝")
    except socket.gaierror:
        return _diagnostic(False, "invalid_address", "MQTT 主机名无法解析")
    except OSError:
        return _diagnostic(False, "connection_failed", "MQTT 连接失败")
    except Exception:
        return _diagnostic(False, "client_error", "MQTT 客户端诊断失败")
    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
            try:
                client.loop_stop()
            except Exception:
                pass
