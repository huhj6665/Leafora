"""数据库 CRUD 测试.

验证 User 与 UserIdentity 的创建、读取、更新、删除以及级联删除行为。
"""
from sqlalchemy import select

from app.models.identity import IdentityType, UserIdentity
from app.models.user import User


async def test_user_identity_crud(session_factory):
    """用户与身份的完整 CRUD 流程."""
    async with session_factory() as db:
        # ---- Create：创建用户与身份 ----
        user = User(nickname="crud_user", status=1)
        db.add(user)
        await db.flush()  # 获取 user.id

        identity = UserIdentity(
            user_id=user.id,
            identity_type=IdentityType.USERNAME.value,
            identifier="crud_user",
            credential="hashed_password_placeholder",
        )
        db.add(identity)
        await db.commit()

        # ---- Read ----
        fetched = await db.scalar(select(User).where(User.id == user.id))
        assert fetched is not None
        assert fetched.nickname == "crud_user"

        fetched_identity = await db.scalar(
            select(UserIdentity).where(UserIdentity.user_id == user.id)
        )
        assert fetched_identity is not None
        assert fetched_identity.identifier == "crud_user"

        # ---- Update ----
        fetched.nickname = "crud_updated"
        await db.commit()

        refreshed = await db.scalar(select(User).where(User.id == user.id))
        assert refreshed.nickname == "crud_updated"

        # ---- Delete：删除用户，级联删除身份 ----
        await db.delete(refreshed)
        await db.commit()

        remaining_user = await db.scalar(select(User).where(User.id == user.id))
        remaining_identity = await db.scalar(
            select(UserIdentity).where(UserIdentity.user_id == user.id)
        )
        assert remaining_user is None
        assert remaining_identity is None
