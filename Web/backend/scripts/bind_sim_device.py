"""本地兼容联调脚本：登录 + 绑定规范虚拟设备 TLD_JETSON_001.

通过现有 FastAPI 接口完成认证与设备绑定，用于打通「用户 → 设备绑定 → 巡检数据归属」链路。
不重写登录系统，不伪造 JWT，不直连数据库查询/写入凭据。

登录方式：
    - username：用户名 + 密码（POST /api/auth/login）
    - phone   ：手机号验证码（POST /api/auth/send-phone-code → 手动输入验证码 → POST /api/auth/login-phone）

安全约束：
    - 密码 / 短信验证码 / Access Token 均通过 getpass 或交互输入，绝不写死源码。
    - 不打印完整 Token、密码、验证码、Cookie。
    - 绑定结果通过受认证的设备查询接口二次校验。

运行（在 backend 目录）：
    python scripts/bind_sim_device.py
    python scripts/bind_sim_device.py --method phone --device-id TLD_JETSON_001
    python scripts/bind_sim_device.py --method phone
"""
from __future__ import annotations

import argparse
import getpass
import sys

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api"
DEFAULT_DEVICE_ID = "TLD_JETSON_001"


class ApiError(Exception):
    """接口调用失败（带 HTTP 状态与业务码）."""

    def __init__(self, status: int, code: object, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


def _mask_phone(phone: str) -> str:
    p = phone.strip()
    if len(p) >= 7:
        return f"{p[:3]}****{p[-4:]}"
    return "***"


def _call(client: httpx.Client, method: str, url: str, *, json=None, token: str | None = None):
    """发起请求并解包统一响应 {code, message, data}."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = client.request(method, url, json=json, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise ApiError(0, 0, f"网络错误：{exc}") from exc

    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(resp.status_code, resp.status_code, "响应非 JSON") from exc

    code = body.get("code")
    message = body.get("message") or body.get("detail") or "未知错误"
    if resp.status_code >= 400 or (isinstance(code, int) and code != 0):
        raise ApiError(resp.status_code, code, message)
    return body.get("data")


def login_username(client: httpx.Client, base: str) -> tuple[str, int]:
    """用户名 + 密码登录."""
    username = input("用户名：").strip()
    if not username:
        raise ApiError(0, 0, "用户名不能为空")
    password = getpass.getpass("密码：")
    data = _call(
        client, "POST", f"{base}/auth/login",
        json={"username": username, "password": password},
    )
    return data["access_token"], data["user_id"]


def login_phone(client: httpx.Client, base: str) -> tuple[str, int]:
    """手机号验证码登录（发送验证码 → 手动输入 → 登录）."""
    phone = input("手机号：").strip()
    if not phone:
        raise ApiError(0, 0, "手机号不能为空")

    # 1. 发送验证码
    _call(client, "POST", f"{base}/auth/send-phone-code", json={"phone": phone})
    print(f"验证码已发送至 {_mask_phone(phone)}，请输入收到的 6 位验证码。")

    # 2. 输入验证码（隐藏）
    code = getpass.getpass("短信验证码：").strip()
    if not code:
        raise ApiError(0, 0, "验证码不能为空")

    # 3. 登录
    data = _call(
        client, "POST", f"{base}/auth/login-phone",
        json={"phone": phone, "code": code},
    )
    return data["access_token"], data["user_id"]


def bind_device(client: httpx.Client, base: str, token: str, device_id: str) -> dict:
    """调用设备绑定接口."""
    return _call(
        client, "POST", f"{base}/device/bind",
        json={"device_id": device_id}, token=token,
    )


def verify_bound(client: httpx.Client, base: str, token: str, device_id: str) -> bool:
    """通过受认证的设备列表接口校验绑定已提交并可访问."""
    devices = _call(client, "GET", f"{base}/device/list", token=token)
    return any(d.get("device_id") == device_id for d in (devices or []))


def main() -> None:
    parser = argparse.ArgumentParser(description="脚本式登录 + 绑定模拟设备")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--method", choices=["username", "phone"], default=None,
                        help="登录方式，缺省交互选择")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    device_id = args.device_id

    method = args.method
    if method is None:
        print("请选择登录方式：")
        print("  1) 用户名密码登录")
        print("  2) 手机号验证码登录")
        choice = input("输入 1 或 2：").strip()
        method = "phone" if choice == "2" else "username"

    with httpx.Client() as client:
        # 1. 用户登录
        try:
            if method == "phone":
                token, user_id = login_phone(client, base)
                method_label = "手机号验证码"
            else:
                token, user_id = login_username(client, base)
                method_label = "用户名密码"
        except ApiError as exc:
            print(f"用户登录：失败（{exc.message}）")
            sys.exit(1)

        print(f"用户登录：成功（user_id={user_id}，方式={method_label}）")
        print(f"设备：{device_id}")

        # 2. 绑定设备
        try:
            result = bind_device(client, base, token, device_id)
        except ApiError as exc:
            if exc.status == 409:
                print(f"设备绑定：失败（{exc.message}，已绑定到其他用户，拒绝覆盖归属）")
            else:
                print(f"设备绑定：失败（{exc.message}）")
            sys.exit(1)

        already = bool(result.get("already_bound"))
        print(f"设备绑定：{'已绑定（此前已绑定到当前用户）' if already else '成功'}")

        # 3. 验证绑定结果（受认证查询，反映 PostgreSQL 已提交数据）
        if verify_bound(client, base, token, device_id):
            print("数据库绑定校验：通过")
            print("当前用户设备查询：通过")
        else:
            print("数据库绑定校验：失败（列表中未找到该设备）")
            sys.exit(1)

    print("——")
    print("说明：跨用户隔离由后端在绑定/查询时强制（其他用户无法通过修改 device_id 访问不属于自己的设备），")
    print("该行为已由自动化测试 test_device_bind.py 覆盖；本脚本仅验证当前用户视角。")


if __name__ == "__main__":
    main()
