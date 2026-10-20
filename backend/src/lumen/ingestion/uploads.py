"""Register a new upload: validate it, store the file and create its `pending` row."""

import asyncio
import hashlib
import uuid
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumen.db.models import Document, DocumentStatus
from lumen.ingestion.parsing import detect_type
from lumen.storage import FileStorage


class DuplicateDocumentError(Exception):
    def __init__(self, existing_id: uuid.UUID | None) -> None:
        super().__init__("This file has already been uploaded.")
        self.existing_id = existing_id


def safe_filename(name: str | None) -> str:
    """Keep only the last path component, so names like '../../x' cannot mean anything."""
    cleaned = PurePath((name or "").replace("\\", "/")).name.strip()
    return (cleaned or "document")[:255]


async def register_upload(
    session: AsyncSession, storage: FileStorage, filename: str | None, data: bytes
) -> Document:
    """Raises `UnsupportedFileError` or `DuplicateDocumentError`. The caller queues processing."""
    name = safe_filename(filename)
    doc_type = detect_type(data, name)
    sha256 = hashlib.sha256(data).hexdigest()

    existing = await session.scalar(select(Document.id).where(Document.sha256 == sha256))
    if existing is not None:
        raise DuplicateDocumentError(existing)

    document = Document(
        id=uuid.uuid7(),
        filename=name,
        doc_type=doc_type,
        size_bytes=len(data),
        sha256=sha256,
        status=DocumentStatus.PENDING,
        chunk_count=0,
    )
    await asyncio.to_thread(storage.save, document.id, data)
    session.add(document)
    try:
        await session.commit()
    except IntegrityError as exc:  # the same file uploaded twice at the same moment
        await session.rollback()
        await asyncio.to_thread(storage.delete, document.id)
        raise DuplicateDocumentError(None) from exc
    await session.refresh(document)
    return document
