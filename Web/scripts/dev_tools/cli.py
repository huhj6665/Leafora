"""HTTP 链路测试工具.

用法：
    python cli.py list --username dev --password xxx
    python cli.py upload --data-id <id> --image path/to/a.jpg --username dev --password xxx
    python cli.py status --data-id <id> ...
    python cli.py json   --data-id <id> ...

也可通过环境变量 TLD_API_USERNAME / TLD_API_PASSWORD 提供凭据（避免命令行泄露）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def _login(client: httpx.Client, base_url: str, username: str, password: str) -> str:
    resp = client.post(f"{base_url}/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise SystemExit(f"登录失败: {body.get('message')}")
    return body["data"]["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_token(args) -> str:
    username = args.username or os.environ.get("TLD_API_USERNAME")
    password = args.password or os.environ.get("TLD_API_PASSWORD")
    if not username or not password:
        raise SystemExit("请提供 --username/--password 或设置 TLD_API_USERNAME/TLD_API_PASSWORD")
    return username, password


def cmd_list(client, base_url, token, args) -> None:
    resp = client.get(f"{base_url}/inspection/list", params={"page_size": 50}, headers=_headers(token))
    resp.raise_for_status()
    data = resp.json()["data"]
    print(f"total={data['total']}")
    for it in data["items"]:
        print(f"  device={it['device_id']} data_id={it['data_id']} captured={it['captured_at']}")


def cmd_upload(client, base_url, token, args) -> None:
    with open(args.image, "rb") as f:
        content = f.read()
    resp = client.post(
        f"{base_url}/inspection/upload-image",
        data={"device_id": args.device_id, "data_id": args.data_id},
        files={"image": (os.path.basename(args.image), content, "image/jpeg")},
        headers=_headers(token),
    )
    resp.raise_for_status()
    print(json.dumps(resp.json()["data"], ensure_ascii=False, indent=2))


def cmd_status(client, base_url, token, args) -> None:
    resp = client.get(f"{base_url}/inspection/{args.data_id}", headers=_headers(token))
    resp.raise_for_status()
    data = resp.json()["data"]
    cd = data.get("cloud_detection")
    if not cd:
        print("尚未上传图片 / 无 cloud_detection")
        return
    print(f"status={cd['status']} model={cd.get('model_name')} version={cd.get('model_version')}")
    print(f"has_target={cd.get('has_target')} results={cd.get('results')}")


def cmd_json(client, base_url, token, args) -> None:
    resp = client.get(f"{base_url}/inspection/{args.data_id}", headers=_headers(token))
    resp.raise_for_status()
    print(json.dumps(resp.json()["data"], ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="TLD 数据链路 HTTP 测试工具")
    parser.add_argument("--base-url", default=os.environ.get("TLD_API_BASE_URL", "http://127.0.0.1:8000/api"))
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="查询巡检数据列表")
    p_list.set_defaults(func=cmd_list)

    p_up = sub.add_parser("upload", help="上传图片")
    p_up.add_argument("--data-id", required=True)
    p_up.add_argument("--device-id", default="TLD_JETSON_001")
    p_up.add_argument("--image", required=True)
    p_up.set_defaults(func=cmd_upload)

    p_st = sub.add_parser("status", help="查询模型状态")
    p_st.add_argument("--data-id", required=True)
    p_st.set_defaults(func=cmd_status)

    p_json = sub.add_parser("json", help="查询完整 JSON")
    p_json.add_argument("--data-id", required=True)
    p_json.set_defaults(func=cmd_json)

    args = parser.parse_args()
    username, password = _get_token(args)

    with httpx.Client(timeout=30.0) as client:
        token = _login(client, args.base_url, username, password)
        args.func(client, args.base_url, token, args)


if __name__ == "__main__":
    main()
