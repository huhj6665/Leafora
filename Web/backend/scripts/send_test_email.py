"""独立 SMTP 发信测试脚本.

用途：填写好 backend/.env 中的 SMTP_* 配置后，向指定测试邮箱发送一封测试邮件，
验证 SMTP 连接、认证与发送链路是否正常。

用法（在 backend/ 目录下，需先激活虚拟环境）：

    python scripts/send_test_email.py recipient@example.com

或省略参数，脚本会提示输入收件邮箱。不会向真实用户批量发送邮件。

安全约束：
    - 不打印 SMTP 授权码。
    - 仅向命令行指定的单个收件邮箱发送。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services import account_security_service  # noqa: E402


async def main() -> None:
    if not settings.smtp_configured:
        print("错误：SMTP 未配置。请在 backend/.env 中填写：")
        print("  SMTP_USERNAME=你的163邮箱地址")
        print("  SMTP_PASSWORD=你的163客户端授权码")
        print("  SMTP_FROM_EMAIL=你的163邮箱地址")
        sys.exit(1)

    to_email = sys.argv[1] if len(sys.argv) > 1 else input("请输入测试收件邮箱：").strip()
    if not to_email:
        print("错误：未提供收件邮箱。")
        sys.exit(1)

    print(f"正在向 {to_email} 发送测试邮件（SMTP: {settings.SMTP_HOST}:{settings.SMTP_PORT}）...")
    try:
        result = await account_security_service.send_test_email(to_email)
    except Exception as exc:  # noqa: BLE001 - 打印可诊断错误，不打印授权码
        print(f"发送失败：{type(exc).__name__}: {exc}")
        sys.exit(1)

    print(f"发送成功：{result}")


if __name__ == "__main__":
    asyncio.run(main())
