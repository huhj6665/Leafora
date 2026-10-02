"""开发用：登记规范虚拟设备 TLD_JETSON_001（支持轮换设备凭据）.

仅当 ENABLE_DEV_TOOLS=true 时允许运行。

流程：
    1. 确保 devices 表存在配置的规范虚拟设备（不存在则创建并生成 device_secret）。
    2. --rotate-secret：重新生成 device_secret（凭据轮换，用于曾泄露的凭据）。

用户绑定只允许正式手机号账号通过动态配对会话完成；本脚本不创建用户名账号。

注意：
    - 不使用真实 Jetson 凭据，不使用用户 JWT 作为设备永久凭据。
    - device_secret 由 secrets 随机生成，仅写入 Web/local 下被忽略的文件，
      可选同步到模拟器本地 .env；控制台不输出原文。

运行：
    python scripts/seed_dev_device.py
    python scripts/seed_dev_device.py --rotate-secret
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from pathlib import Path

from sqlalchemy import select

# Standalone credential provisioning must not echo SQL bound parameters/hashes.
os.environ["DEBUG"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.device import Device
from app.core.security import hash_device_secret

WEB_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECRET_OUTPUT = WEB_ROOT / "local" / "device_credentials" / "TLD_JETSON_001.env"
MOCK_ENV_PATH = WEB_ROOT / "scripts" / "mock_jetson" / ".env"


def _export_secret(secret: str, output: Path, replace: bool = False) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not replace:
        raise FileExistsError(f"本地凭据文件已存在，拒绝覆盖：{output}")
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        f"DEVICE_ID={settings.DEV_SIM_DEVICE_ID}\nDEVICE_SECRET={secret}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, output)


def _sync_mock_env(secret: str) -> None:
    lines = MOCK_ENV_PATH.read_text(encoding="utf-8").splitlines() if MOCK_ENV_PATH.exists() else []
    rendered: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith("MOCK_DEVICE_SECRET="):
            rendered.append(f"MOCK_DEVICE_SECRET={secret}")
            replaced = True
        else:
            rendered.append(line)
    if not replaced:
        rendered.append(f"MOCK_DEVICE_SECRET={secret}")
    temporary = MOCK_ENV_PATH.with_suffix(".env.tmp")
    temporary.write_text("\n".join(rendered) + "\n", encoding="utf-8")
    os.replace(temporary, MOCK_ENV_PATH)


async def rotate_secret(
    device_id: str, output: Path, sync_mock_env: bool = False
) -> None:
    """轮换设备凭据（重新生成 device_secret）."""
    if not settings.ENABLE_DEV_TOOLS:
        print("ENABLE_DEV_TOOLS=false，已拒绝运行（生产环境保护）。")
        return

    async with AsyncSessionLocal() as session:
        device = await session.scalar(
            select(Device).where(Device.device_id == device_id)
        )
        if device is None:
            print(f"[失败] 设备 {device_id} 不存在，请先运行 seed 脚本创建。")
            return

        new_secret = secrets.token_hex(32)
        device.device_secret = hash_device_secret(new_secret)
        await session.commit()
        _export_secret(new_secret, output, replace=True)
        if sync_mock_env:
            _sync_mock_env(new_secret)
        print(f"[轮换] 设备 {device_id} 的 device_secret 已更新；凭据写入 {output}。")
        print("       凭据内容未输出；旧凭据即刻作废。")


async def main(output: Path, sync_mock_env: bool = False) -> None:
    if not settings.ENABLE_DEV_TOOLS:
        print("ENABLE_DEV_TOOLS=false，已拒绝运行（生产环境保护）。")
        return

    device_id = settings.DEV_SIM_DEVICE_ID
    device_name = settings.DEV_SIM_DEVICE_NAME

    async with AsyncSessionLocal() as session:
        device = await session.scalar(
            select(Device).where(Device.device_id == device_id)
        )
        if device is None:
            secret = secrets.token_hex(32)
            device = Device(
                device_id=device_id,
                device_name=device_name,
                device_secret=hash_device_secret(secret),
                status=1,
            )
            session.add(device)
            await session.commit()
            _export_secret(secret, output)
            if sync_mock_env:
                _sync_mock_env(secret)
            print(f"[创建] 设备 {device_id}；一次性凭据已写入 {output}。")
            print("      服务端仅保存摘要；凭据内容未输出。")
        else:
            print(f"[存在] 设备 {device_id}（name={device.device_name}）")

        print("用户绑定未自动执行；请由正式手机号账号通过动态配对二维码确认。")

    print("完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="登记模拟设备 / 轮换设备凭据")
    parser.add_argument(
        "--rotate-secret",
        action="store_true",
        help="轮换规范虚拟设备的 device_secret",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SECRET_OUTPUT,
        help="一次性凭据输出文件（必须位于 Web/local 内）",
    )
    parser.add_argument(
        "--sync-mock-env",
        action="store_true",
        help="同时安全写入 scripts/mock_jetson/.env 的 MOCK_DEVICE_SECRET",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    local_root = (WEB_ROOT / "local").resolve()
    if local_root not in output.parents:
        parser.error("凭据输出必须位于 Web/local 目录内")

    if args.rotate_secret:
        asyncio.run(rotate_secret(settings.DEV_SIM_DEVICE_ID, output, args.sync_mock_env))
    else:
        asyncio.run(main(output, args.sync_mock_env))
