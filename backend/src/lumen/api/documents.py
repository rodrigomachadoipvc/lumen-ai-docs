"""Upload, list, inspect and delete documents."""

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from lumen.api.deps import ContainerDep, SessionDep
from lumen.api.errors import AppError, not_found
from lumen.db.models import Document, DocumentStatus, DocumentType
from lumen.ingestion.parsing import UnsupportedFileError
from lumen.ingestion.uploads import DuplicateDocumentError, register_upload

router = APIRouter(prefix="/documents", tags=["documents"])

_READ_CHUNK = 1024 * 1024
_MEDIA_TYPES = {
    DocumentType.PDF: "application/pdf",
    # Markdown is served as plain text so a browser never renders it as HTML.
    DocumentType.MARKDOWN: "text/plain; charset=utf-8",
    DocumentType.TEXT: "text/plain; charset=utf-8",
}


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    doc_type: DocumentType
    size_bytes: int
    status: DocumentStatus
    error: str | None
    language: str | None
    page_count: int | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    data = bytearray()
    while chunk := await file.read(_READ_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise AppError(
                413, "file_too_large", f"Files must be at most {limit // (1024 * 1024)} MB."
            )
    return bytes(data)


async def _get_document(session: SessionDep, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise not_found("Document")
    return document


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile, session: SessionDep, container: ContainerDep
) -> DocumentOut:
    """Store the file and queue it for processing. Poll `GET /documents/{id}` for its status."""
    data = await _read_limited(file, container.settings.max_upload_bytes)
    if not data:
        raise AppError(422, "empty_file", "The file is empty.")
    try:
        document = await register_upload(session, container.storage, file.filename, data)
    except UnsupportedFileError as exc:
        raise AppError(415, "unsupported_file", str(exc)) from exc
    except DuplicateDocumentError as exc:
        details = {"document_id": str(exc.existing_id)} if exc.existing_id else None
        raise AppError(409, "duplicate_document", str(exc), details) from exc
    container.worker.enqueue(document.id)
    return DocumentOut.model_validate(document)


@router.get("")
async def list_documents(session: SessionDep) -> list[DocumentOut]:
    documents = await session.scalars(select(Document).order_by(Document.created_at.desc()))
    return [DocumentOut.model_validate(d) for d in documents]


@router.get("/{document_id}")
async def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentOut:
    return DocumentOut.model_validate(await _get_document(session, document_id))


@router.get("/{document_id}/file", response_class=FileResponse)
async def download_document_file(
    document_id: uuid.UUID, session: SessionDep, container: ContainerDep
) -> FileResponse:
    """The original file, shown inline (PDFs open in the browser's viewer)."""
    document = await _get_document(session, document_id)
    path = container.storage.path_for(document.id)
    if not path.exists():
        raise not_found("File")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[document.doc_type],
        filename=document.filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: uuid.UUID, session: SessionDep, container: ContainerDep
) -> DocumentOut:
    """Queue the document again, for example after Ollama was unavailable."""
    document = await _get_document(session, document_id)
    if document.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
        raise AppError(409, "already_processing", "The document is already being processed.")
    document.status = DocumentStatus.PENDING
    document.error = None
    await session.commit()
    await session.refresh(document)
    container.worker.enqueue(document.id)
    return DocumentOut.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, session: SessionDep, container: ContainerDep
) -> Response:
    document = await _get_document(session, document_id)
    await session.delete(document)
    await session.commit()
    await asyncio.to_thread(container.storage.delete, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
