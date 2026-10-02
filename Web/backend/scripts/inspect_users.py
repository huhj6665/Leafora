"""只读脚本：查看用户与登录身份（不含敏感凭据）.

用途：开发调试时快速查看 tld_db 中的用户数据。
用法（在 backend/ 目录下）：

    python scripts/inspect_users.py

安全约束：
    - 不输出 credential（密码哈希）
    - 手机号脱敏显示
    - 不输出 AccessKey / JWT / 验证码
"""
import asyncio
import sys
from pathlib import Path

# 确保可导入 app 包（脚本可能从任意目录运行）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.identity import UserIdentity  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.phone import mask_phone  # noqa: E402


def _display_identifier(identity: UserIdentity) -> str:
    """手机号脱敏，其余类型原样显示."""
    if identity.identity_type == "phone":
        return mask_phone(identity.identifier)
    return identity.identifier


async def main() -> None:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).order_by(User.id))).scalars().all()
        if not users:
            print("（无用户数据）")
        for u in users:
            created = u.created_at.isoformat(sep=" ", timespec="seconds") if u.created_at else "-"
            print(f"[user #{u.id}] status={u.status}  created={created}  nickname={u.nickname}")
            identities = (
                await db.execute(
                    select(UserIdentity).where(UserIdentity.user_id == u.id)
                )
            ).scalars().all()
            for ident in identities:
                print(f"    - identity: type={ident.identity_type:<10} identifier={_display_identifier(ident)}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
