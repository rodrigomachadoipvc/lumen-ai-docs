from typing import Any

from httpx2 import AsyncClient
from sqlalchemy import func, select

from lumen.container import Container
from lumen.db.models import Chunk
from lumen.providers.errors import ProviderError
from tests.fakes import FakeEmbeddings
from tests.pdf_factory import make_pdf

MARKDOWN = (
    "# Guia\n\nO Lumen responde a perguntas sobre os seus documentos.\n\n"
    "## Citações\n\nCada resposta cita as passagens e as páginas usadas.\n"
).encode()


async def _upload(client: AsyncClient, name: str, data: bytes) -> Any:
    return await client.post("/documents", files={"file": (name, data)})


async def test_upload_markdown_is_processed_into_chunks(
    client: AsyncClient, container: Container
) -> None:
    response = await _upload(client, "guia.md", MARKDOWN)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["doc_type"] == "markdown"

    await container.worker.join()
    document = (await client.get(f"/documents/{body['id']}")).json()
    assert document["status"] == "ready"
    assert document["language"] == "portuguese"
    assert document["chunk_count"] == 2

    async with container.sessions() as session:
        chunks = (await session.scalars(select(Chunk).order_by(Chunk.ordinal))).all()
    assert [c.heading_path for c in chunks] == [["Guia"], ["Guia", "Citações"]]
    assert all(len(c.embedding) == 1024 for c in chunks)


async def test_upload_pdf_keeps_pages_and_serves_original(
    client: AsyncClient, container: Container
) -> None:
    pdf = make_pdf([["First page."], ["Second page."]])

    document = (await _upload(client, "report.pdf", pdf)).json()
    await container.worker.join()

    ready = (await client.get(f"/documents/{document['id']}")).json()
    assert ready["status"] == "ready"
    assert ready["page_count"] == 2
    async with container.sessions() as session:
        pages = (await session.scalars(select(Chunk.page).order_by(Chunk.ordinal))).all()
    assert pages == [1, 2]

    file = await client.get(f"/documents/{document['id']}/file")
    assert file.status_code == 200
    assert file.headers["content-type"] == "application/pdf"
    assert file.content == pdf


async def test_full_text_vector_is_built_with_document_language(
    client: AsyncClient, container: Container
) -> None:
    await _upload(client, "guia.md", MARKDOWN)
    await container.worker.join()

    async with container.sessions() as session:
        # The Portuguese stemmer maps "página" and "páginas" to the same lexeme.
        matches = await session.scalar(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.tsv.op("@@")(func.plainto_tsquery("portuguese", "página")))
        )
    assert matches == 1


async def test_list_and_delete(client: AsyncClient, container: Container) -> None:
    first = (await _upload(client, "a.txt", b"Alpha text.")).json()
    second = (await _upload(client, "b.txt", b"Beta text.")).json()
    await container.worker.join()

    listed = (await client.get("/documents")).json()
    assert [d["id"] for d in listed] == [second["id"], first["id"]]  # newest first

    assert (await client.delete(f"/documents/{first['id']}")).status_code == 204
    assert (await client.get(f"/documents/{first['id']}")).status_code == 404
    assert not container.storage.path_for(first["id"]).exists()
    async with container.sessions() as session:
        remaining = await session.scalar(select(func.count()).select_from(Chunk))
    assert remaining == 1


async def test_duplicate_upload_is_rejected(client: AsyncClient) -> None:
    first = (await _upload(client, "a.txt", b"Same content.")).json()

    response = await _upload(client, "copy.txt", b"Same content.")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "duplicate_document",
        "message": "This file has already been uploaded.",
        "details": {"document_id": first["id"]},
    }


async def test_rejects_unsupported_empty_and_oversized_files(
    client: AsyncClient, container: Container
) -> None:
    unsupported = await _upload(client, "image.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "unsupported_file"

    empty = await _upload(client, "empty.txt", b"")
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "empty_file"

    container.settings.max_upload_mb = 1
    too_big = await _upload(client, "big.txt", b"a" * (1024 * 1024 + 1))
    assert too_big.status_code == 413


async def test_filename_cannot_escape_storage(client: AsyncClient, container: Container) -> None:
    response = await _upload(client, "../../etc/passwd.txt", b"Harmless.")

    assert response.json()["filename"] == "passwd.txt"
    assert container.storage.path_for(response.json()["id"]).parent == container.storage.root


async def test_provider_failure_marks_document_failed_and_can_be_reprocessed(
    client: AsyncClient, container: Container, embedder: FakeEmbeddings
) -> None:
    original = embedder.embed_documents

    async def broken(texts: Any) -> list[list[float]]:
        raise ProviderError("Could not reach Ollama.")

    embedder.embed_documents = broken  # type: ignore[method-assign]
    document = (await _upload(client, "a.txt", b"Some text.")).json()
    await container.worker.join()

    failed = (await client.get(f"/documents/{document['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error"] == "Could not reach Ollama."

    embedder.embed_documents = original  # type: ignore[method-assign]
    assert (await client.post(f"/documents/{document['id']}/reprocess")).status_code == 202
    await container.worker.join()
    assert (await client.get(f"/documents/{document['id']}")).json()["status"] == "ready"


async def test_unknown_document_returns_json_404(client: AsyncClient) -> None:
    response = await client.get("/documents/01900000-0000-7000-8000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_invalid_id_returns_validation_error(client: AsyncClient) -> None:
    response = await client.get("/documents/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
