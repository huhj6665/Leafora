"""生成 TLD 设备配对测试二维码（普通 QR Code）.

用途：
    在 Windows 电脑上生成一张普通二维码，模拟 Jetson 屏幕显示设备配对二维码，
    供手机小程序内的 wx.scanCode() 扫码测试。

重要说明：
    - 这是普通二维码，但内容来自后端动态配对会话；
      它不支持微信「扫一扫」直接打开 TLD 小程序（那需要官方小程序码）。
    - 二维码内容不包含用户手机号、JWT、设备长期密钥、数据库密码或 AppSecret。
    - pairing_token 短时、一次性，服务端只保存摘要。

依赖（安装到 backend 虚拟环境，不装到 model_service/.venv）：
    backend\\.venv\\Scripts\\python.exe -m pip install "qrcode[pil]"

运行（在 Web 项目根目录）：
    backend\\.venv\\Scripts\\python.exe scripts\\mock_jetson\\generate_pairing_qr.py
    backend\\.venv\\Scripts\\python.exe scripts\\mock_jetson\\generate_pairing_qr.py --device-id TLD_JETSON_001
    backend\\.venv\\Scripts\\python.exe scripts\\mock_jetson\\generate_pairing_qr.py --open
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.mock_jetson.config import load_config

# 使控制台中文输出在不同终端编码下尽量正常显示
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 默认输出到 scripts/mock_jetson/outputs/pairing_test.png
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "outputs" / "pairing_test.png"

PROTOCOL_TYPE = "tld_device_pairing"
PROTOCOL_VERSION = "2.0"


def build_pairing_payload(device_id: str, session_id: str, token: str, expires_at: str, version: str) -> str:
    """构造 V2.0 一次性配对二维码 JSON 内容."""
    payload = {
        "type": PROTOCOL_TYPE,
        "version": version,
        "device_id": device_id,
        "pairing_session_id": session_id,
        "pairing_token": token,
        "expires_at": expires_at,
    }
    # 保持字段顺序稳定、无多余空格，便于与小程序解析协议一致
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def generate_qr(content: str, output_path: Path) -> None:
    """生成标准 QR Code 并保存为 PNG."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(
        version=None,  # 自动选择最小可用版本
        error_correction=ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path))
    print(f"[输出] 二维码图片已生成：{output_path}")


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(
        description="生成 TLD 设备配对测试二维码（普通 QR Code）"
    )
    parser.add_argument("--device-id", default=config.device_id, help="设备编号")
    parser.add_argument("--version", default=PROTOCOL_VERSION, help="协议版本（默认 2.0）")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出 PNG 路径")
    parser.add_argument("--open", action="store_true", help="生成后用系统默认程序打开图片")
    args = parser.parse_args()

    if not config.device_secret:
        raise SystemExit("MOCK_DEVICE_SECRET 未配置，无法申请动态配对会话")
    response = httpx.post(
        f"{config.backend_base_url.rstrip('/')}/device/pairing-sessions",
        headers={"X-Device-ID": args.device_id, "X-Device-Secret": config.device_secret},
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()["data"]
    content = build_pairing_payload(
        args.device_id, data["pairing_session_id"], data["pairing_token"],
        data["expires_at"], args.version,
    )
    output_path = Path(args.output)

    print(f"[会话] {data['pairing_session_id']}，有效期至 {data['expires_at']}")
    print("注意：本二维码为「普通设备测试二维码」，仅供小程序内 wx.scanCode() 扫码测试；")
    print("      它不支持微信「扫一扫」直接打开 TLD 小程序。")

    generate_qr(content, output_path)

    if args.open:
        import os

        if hasattr(os, "startfile"):  # Windows：用系统默认程序打开
            os.startfile(str(output_path))
        else:
            print("[提示] 当前环境不支持自动打开，请手动打开该 PNG。")


if __name__ == "__main__":
    main()
