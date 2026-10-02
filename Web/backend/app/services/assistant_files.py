"""Private attachment storage and bounded text extraction."""
from __future__ import annotations

import asyncio
import hashlib
import io
import math
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessError, NotFoundError
from app.models.assistant import AssistantDocument

MAX_TEXT = 400000


def root() -> Path:
    path = Path(settings.ASSISTANT_STORAGE_ROOT)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path.resolve()


def path_for(key: str) -> Path:
    path = (root() / key).resolve()
    if root() not in path.parents:
        raise BusinessError("非法附件路径")
    return path


def chunk_text(text: str, page: int = 1) -> list[dict]:
    text = text.replace("\x00", "").strip()
    return [{"page": page, "text": text[i:i + 900]} for i in range(0, len(text), 760)]


def extract(filename: str, data: bytes) -> tuple[str, str, list[dict]]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        if len(data) > 10 * 1024 * 1024:
            raise BusinessError("图片最大10MB")
        from PIL import Image
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in {"JPEG", "PNG", "WEBP"} or img.width * img.height > 25000000:
                    raise ValueError()
                fmt = img.format
                img.verify()
        except Exception as exc:
            raise BusinessError("图片损坏或尺寸过大，请上传有效JPEG、PNG或WebP") from exc
        return "IMAGE", {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt], []
    chunks: list[dict] = []
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise BusinessError("暂不支持加密PDF")
        if len(reader.pages) > 200:
            raise BusinessError("文档最多200页，请分拆上传")
        size = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            size += len(text)
            if size > MAX_TEXT:
                raise BusinessError("文档文字量过大，请分拆上传")
            chunks.extend(chunk_text(text, number))
        mime = "application/pdf"
    elif suffix == ".docx":
        from docx import Document
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 80 * 1024 * 1024:
                raise BusinessError("文档解压后过大")
        document = Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        parts.extend(" | ".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows)
        text = "\n".join(parts)
        if len(text) > MAX_TEXT:
            raise BusinessError("文档文字量过大，请分拆上传")
        chunks = chunk_text(text)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif suffix in {".txt", ".md"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = data.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise BusinessError("文本需使用UTF-8或GB18030编码") from exc
        if len(text) > MAX_TEXT:
            raise BusinessError("文档文字量过大，请分拆上传")
        chunks = chunk_text(text)
        mime = "text/plain" if suffix == ".txt" else "text/markdown"
    else:
        raise BusinessError("支持JPEG/PNG/WebP、文字型PDF、DOCX、TXT和Markdown")
    if not chunks:
        raise BusinessError("没有提取到文字；扫描版文档请先进行OCR")
    return "DOCUMENT", mime, chunks


def document_dict(row: AssistantDocument) -> dict:
    return {"id": row.id, "title": row.title, "kind": row.kind, "mime_type": row.mime_type,
            "byte_size": row.byte_size, "chunk_count": len(row.chunks or []),
            "metadata": row.metadata_, "created_at": row.created_at.isoformat() if row.created_at else None}


async def owned_document(db: AsyncSession, user_id: int, document_id: str) -> AssistantDocument:
    row = await db.scalar(select(AssistantDocument).where(
        AssistantDocument.id == document_id, AssistantDocument.owner_user_id == user_id,
        AssistantDocument.deleted_at.is_(None)))
    if not row:
        raise NotFoundError("附件不存在或无权访问")
    return row


async def save_attachment(db: AsyncSession, user_id: int, filename: str, data: bytes) -> dict:
    if not data or len(data) > 20 * 1024 * 1024:
        raise BusinessError("附件不能为空且最大20MB")
    name = Path(filename.replace("\\", "/")).name[:255]
    try:
        # Parsing is performed outside the event loop by the calling upload route.
        kind, mime, chunks = await asyncio.to_thread(extract, name, data)
    except BusinessError:
        raise
    except Exception as exc:
        raise BusinessError("文件解析失败，请确认文件有效且未加密") from exc
    digest = hashlib.sha256(data).hexdigest()
    old = await db.scalar(select(AssistantDocument).where(
        AssistantDocument.owner_user_id == user_id, AssistantDocument.content_hash == digest,
        AssistantDocument.deleted_at.is_(None)))
    if old:
        return document_dict(old)
    identifier = "ATT_" + uuid4().hex
    key = identifier + Path(name).suffix.lower()
    path = path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    row = AssistantDocument(id=identifier, owner_user_id=user_id, title=name, kind=kind,
                            mime_type=mime, storage_key=key, byte_size=len(data), content_hash=digest,
                            chunks=chunks, metadata_={"source": "用户上传", "locator": "页码" if mime == "application/pdf" else "片段"})
    db.add(row)
    try:
        await db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return document_dict(row)


def tokens(text: str) -> list[str]:
    import jieba
    return [x.lower() for x in jieba.cut(text) if re.search(r"[\w\u4e00-\u9fff]", x) and len(x.strip()) > 1]


async def search(db: AsyncSession, user_id: int, query: str, attachment_ids: list[str] | None = None) -> list[dict]:
    stmt = select(AssistantDocument).where(
        AssistantDocument.kind == "DOCUMENT", AssistantDocument.deleted_at.is_(None),
        or_(AssistantDocument.owner_user_id == user_id, AssistantDocument.owner_user_id.is_(None)))
    if attachment_ids:
        stmt = stmt.where(or_(AssistantDocument.id.in_(attachment_ids), AssistantDocument.owner_user_id.is_(None)))
    rows = (await db.execute(stmt.order_by(AssistantDocument.updated_at.desc()).limit(100))).scalars().all()
    candidates = [(row, index, chunk) for row in rows for index, chunk in enumerate(row.chunks or [])][:10000]
    if not candidates:
        return []
    return await asyncio.to_thread(rank_candidates, candidates, query)


def rank_candidates(candidates: list, query: str) -> list[dict]:
    # Chinese segmentation / BM25 can be CPU-intensive; keep the event loop responsive.
    from rank_bm25 import BM25Okapi
    corpus = [tokens(row.title + " " + chunk["text"]) for row, _, chunk in candidates]
    scores = BM25Okapi(corpus).get_scores(tokens(query))
    # BM25 can be negative with very small corpora; require real lexical overlap.
    terms = set(tokens(query))
    ranked = sorted(range(len(candidates)), key=lambda i: (len(terms.intersection(corpus[i])), scores[i]), reverse=True)
    output = []
    for i in ranked:
        if not terms.intersection(corpus[i]):
            continue
        row, index, chunk = candidates[i]
        output.append({"document_id": row.id, "title": row.title, "text": chunk["text"],
                       "page": chunk.get("page", 1) if row.mime_type == "application/pdf" else index + 1,
                       "locator": "页" if row.mime_type == "application/pdf" else "片段", "paragraph": index + 1,
                       "url": row.metadata_.get("url"), "publisher": row.metadata_.get("publisher", "用户资料"),
                       "private": row.owner_user_id is not None})
        if len(output) == 6:
            break
    return output
