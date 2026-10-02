"""Idempotently import reviewed public knowledge; never publish user uploads.

Run from Web/backend: .venv/Scripts/python.exe scripts/import_assistant_knowledge.py
Optional --manifest accepts the same explicit reviewed-summary JSON format.
"""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.database.assistant import AsyncSessionLocal, engine
from app.models.assistant import AssistantDocument
from app.services.assistant_files import chunk_text


def validate_manifest(path: Path) -> list[dict]:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("知识清单最大2MB")
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("知识清单必须是最多100项的数组")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k].strip()
                                               for k in ("id", "title", "publisher", "reviewed_at", "text")):
            raise ValueError("每项需填写id、title、publisher、reviewed_at、text")
        if not row["id"].startswith("KNOW_") or len(row["id"]) > 40 or row["id"] in seen:
            raise ValueError("知识编号必须唯一，KNOW_开头且最多40字符")
        if len(row["text"]) > 50000 or len(row["title"]) > 255:
            raise ValueError("单项文字最多50000字符，标题最多255字符")
        if row.get("url") and urlparse(row["url"]).scheme not in {"http", "https"}:
            raise ValueError("来源URL必须使用HTTP或HTTPS")
        seen.add(row["id"])
    return rows


async def import_manifest(db, rows: list[dict]) -> tuple[int, int]:
    updated = unchanged = 0
    for item in rows:
        metadata = {k: v for k, v in item.items() if k not in {"text", "id"}}
        digest = hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        row = await db.scalar(select(AssistantDocument).where(AssistantDocument.id == item["id"]))
        if row and row.owner_user_id is not None:
            raise ValueError("导入编号与私有资料冲突；禁止发布用户附件")
        if row and row.content_hash == digest and row.deleted_at is None:
            unchanged += 1
            continue
        if row is None:
            row = AssistantDocument(id=item["id"], owner_user_id=None)
            db.add(row)
        row.title, row.kind, row.mime_type = item["title"], "DOCUMENT", "text/plain"
        row.storage_key, row.byte_size, row.content_hash = "", len(item["text"].encode()), digest
        row.chunks, row.metadata_, row.deleted_at = chunk_text(item["text"]), metadata, None
        updated += 1
    await db.commit()
    return updated, unchanged


async def main():
    parser = argparse.ArgumentParser(description="导入经人工审阅、可公开共享的知识摘要，不要放入私有信息")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "knowledge" / "assistant_starter.json")
    args = parser.parse_args()
    try:
        rows = validate_manifest(args.manifest)
        async with AsyncSessionLocal() as db:
            changed, unchanged = await import_manifest(db, rows)
        print(f"公共知识导入完成：新增或更新 {changed} 条，未变化 {unchanged} 条")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
