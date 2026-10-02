from pathlib import Path

from sqlalchemy import select

from app.core.security import verify_device_secret
from app.models.device import Device, DeviceBinding
from scripts.register_real_device import REAL_DEVICE_ID, register_real_device
from tests.helpers import make_user


async def test_register_real_device_exports_once_and_preserves_existing(
    session_factory, tmp_path: Path
):
    credential_file = tmp_path / "TLD_SIM_002.env"
    async with session_factory() as session:
        created = await register_real_device(session, credential_file)
        device = await session.scalar(
            select(Device).where(Device.device_id == REAL_DEVICE_ID)
        )
        assert created.status == "CREATED"
        assert created.credential_path == credential_file
        assert device is not None
        credential_text = credential_file.read_text(encoding="utf-8")
        plaintext = credential_text.split("DEVICE_SECRET=", 1)[1].strip()
        assert plaintext
        assert plaintext not in device.device_secret
        assert verify_device_secret(plaintext, device.device_secret)

        original_hash = device.device_secret
        user = await make_user(session, nickname="real-device-owner")
        session.add(DeviceBinding(user_id=user.id, device_id=device.id, status=1))
        await session.commit()

        credential_file.unlink()
        existing = await register_real_device(session, credential_file)
        await session.refresh(device)
        assert existing.status == "EXISTS"
        assert existing.active_binding_count == 1
        assert device.device_secret == original_hash
        assert not credential_file.exists()
