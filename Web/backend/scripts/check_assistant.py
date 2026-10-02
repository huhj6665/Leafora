"""Read-only deployment checks; --live-model opts into one tiny paid model request."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, inspect, select
from app.database.assistant import AsyncSessionLocal, engine
from app.models.assistant import AssistantDocument
from app.services import assistant_providers


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-model", action="store_true", help="调用一次模型，仅发送无私有数据的短连接测试问题")
    args = parser.parse_args()
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
        names = ["assistant_conversations", "assistant_messages", "assistant_runs", "assistant_events", "assistant_documents", "assistant_field_contexts"]
        print("assistant_schema:", "ready" if all(name in tables for name in names) else "migration_required")
        async with AsyncSessionLocal() as db:
            count = await db.scalar(select(func.count(AssistantDocument.id)).where(AssistantDocument.owner_user_id.is_(None), AssistantDocument.deleted_at.is_(None)))
        print("public_knowledge_count:", count)
        capability = assistant_providers.capabilities()
        print("capabilities:", {k: capability[k] for k in ("model", "model_configured", "weather_configured", "search_configured")})
        if args.live_model:
            if not capability["model_configured"]:
                raise RuntimeError("model_not_configured")
            completed = False
            async for packet in assistant_providers.model_stream([{"role": "user", "content": "这是不含任何私人数据的接口连接测试。请只回复：连接正常。"}], []):
                if packet["kind"] == "complete":
                    completed = bool(packet["message"].get("content"))
            if not completed:
                raise RuntimeError("model_empty_reply")
            print("live_model:", "passed")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
