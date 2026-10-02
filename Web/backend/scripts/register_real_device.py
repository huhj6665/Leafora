"""Idempotently register the real Jetson without exposing its credential.

The permanent identifier is frozen as ``TLD_SIM_002``.  Existing rows, bindings,
history and credentials are never changed.  For a new row, the plaintext secret is
written once to a Git-ignored local file while PostgreSQL stores only its hash.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# The application enables SQL echo in development.  Registration output must never
# include credential hashes or bound parameters, so disable echo before importing
# the shared settings/engine in this standalone process.
os.environ["DEBUG"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_device_secret
from app.database.session import AsyncSessionLocal
from app.models.device import Device, DeviceBinding

REAL_DEVICE_ID = "TLD_SIM_002"
REAL_DEVICE_NAME = "TLD Jetson Nano"
WEB_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = WEB_ROOT / "local" / "device_credentials" / f"{REAL_DEVICE_ID}.env"


@dataclass(frozen=True)
class RegistrationResult:
    status: str
    device_id: str
    active_binding_count: int
    credential_path: Path | None = None


def _prepare_secret_file(path: Path, secret: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(
            f"本地凭据文件已存在，拒绝覆盖：{path}。请先人工核对数据库与设备状态。"
        )
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise FileExistsError(
            f"发现未完成的临时凭据文件：{temporary}。请人工核对后再运行。"
        )
    temporary.write_text(
        f"DEVICE_ID={REAL_DEVICE_ID}\nDEVICE_SECRET={secret}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    return temporary


async def register_real_device(
    session: AsyncSession,
    output_path: Path = DEFAULT_OUTPUT,
) -> RegistrationResult:
    device = await session.scalar(
        select(Device).where(Device.device_id == REAL_DEVICE_ID)
    )
    if device is not None:
        active_bindings = int(
            await session.scalar(
                select(func.count())
                .select_from(DeviceBinding)
                .where(DeviceBinding.device_id == device.id, DeviceBinding.status == 1)
            )
            or 0
        )
        return RegistrationResult("EXISTS", REAL_DEVICE_ID, active_bindings)

    secret = secrets.token_urlsafe(48)
    temporary = _prepare_secret_file(output_path, secret)
    device = Device(
        device_id=REAL_DEVICE_ID,
        device_name=REAL_DEVICE_NAME,
        device_secret=hash_device_secret(secret),
        status=1,
    )
    session.add(device)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        temporary.unlink(missing_ok=True)
        existing = await session.scalar(
            select(Device).where(Device.device_id == REAL_DEVICE_ID)
        )
        if existing is None:
            raise
        return RegistrationResult("EXISTS", REAL_DEVICE_ID, 0)

    os.replace(temporary, output_path)
    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass
    return RegistrationResult("CREATED", REAL_DEVICE_ID, 0, output_path)


async def _run(output_path: Path) -> RegistrationResult:
    async with AsyncSessionLocal() as session:
        return await register_real_device(session, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="幂等登记真实设备 TLD_SIM_002；不会覆盖既有设备、绑定或历史数据"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="一次性凭据输出文件（必须位于 Web/local 内）",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    local_root = (WEB_ROOT / "local").resolve()
    if local_root not in output.parents:
        parser.error("凭据输出必须位于 Web/local 目录内")

    result = asyncio.run(_run(output))
    if result.status == "CREATED":
        print(f"[CREATED] {result.device_id} 已登记；一次性凭据已写入：{result.credential_path}")
        print("凭据内容未输出。请由项目总监转写到 Jetson runtime/device.env 后安全保管。")
    else:
        print(
            f"[EXISTS] {result.device_id} 已存在；保留原凭据、历史数据和绑定，"
            f"active_binding_count={result.active_binding_count}。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
