"""Small REST client for the Lumen API. The MCP server never touches the database directly."""

import re
from typing import Any, Protocol

import httpx2
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel


class LumenError(ToolError):
    """The Lumen API is unreachable or returned an error.

    A `ToolError` is an anticipated failure, so the MCP SDK passes its message to the model
    (any other exception becomes a generic "Error executing tool").
    """


class Passage(BaseModel):
    document_id: str
    filename: str
    page: int | None
    section: str | None
    text: str
    score: float | None = None


class DocumentInfo(BaseModel):
    id: str
    filename: str
    type: str
    status: str
    pages: int | None
    passages: int
    language: str | None


class LumenApi(Protocol):
    async def search(
        self, query: str, *, limit: int, document_ids: list[str] | None
    ) -> list[Passage]: ...

    async def list_documents(self) -> list[DocumentInfo]: ...

    async def chunks(
        self, document_id: str, *, page: int | None, heading: str | None
    ) -> list[Passage]: ...


_FILLER = frozenset("de do da dos das the of and e a o pdf md txt markdown".split())


def name_words(name: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[^\W_]+", name.lower()) if w not in _FILLER)


def resolve_document(reference: str, documents: list[DocumentInfo]) -> DocumentInfo:
    """Find a document by id, exact filename, or the words of its name."""
    reference = reference.strip()
    for document in documents:
        if reference in (document.id, document.filename) or (
            reference.lower() == document.filename.lower()
        ):
            return document
    wanted = name_words(reference)
    matches = [d for d in documents if wanted and wanted <= name_words(d.filename)]
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(d.filename for d in documents) or "none"
    raise LumenError(f"No single document matches '{reference}'. Available: {names}.")


def _section(heading_path: list[str]) -> str | None:
    return " > ".join(heading_path) or None


class HttpLumenApi:
    def __init__(
        self, base_url: str, *, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx2.AsyncClient(
            base_url=self._base_url, timeout=60.0, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx2.HTTPError as exc:
            raise LumenError(
                f"Cannot reach the Lumen API at {self._base_url}. Is it running?"
            ) from exc
        if response.is_error:
            try:
                message = response.json()["error"]["message"]
            except ValueError, KeyError, TypeError:
                message = response.text or response.reason_phrase
            raise LumenError(f"Lumen API error {response.status_code}: {message}")
        return response.json()

    async def search(
        self, query: str, *, limit: int, document_ids: list[str] | None
    ) -> list[Passage]:
        body: dict[str, Any] = {"query": query, "limit": limit}
        if document_ids:
            body["document_ids"] = document_ids
        data = await self._request("POST", "/search", json=body)
        return [
            Passage(
                document_id=hit["document_id"],
                filename=hit["filename"],
                page=hit["page"],
                section=_section(hit["heading_path"]),
                text=hit["text"],
                score=hit["similarity"],
            )
            for hit in data["hits"]
        ]

    async def list_documents(self) -> list[DocumentInfo]:
        data = await self._request("GET", "/documents")
        return [
            DocumentInfo(
                id=d["id"],
                filename=d["filename"],
                type=d["doc_type"],
                status=d["status"],
                pages=d["page_count"],
                passages=d["chunk_count"],
                language=d["language"],
            )
            for d in data
        ]

    async def chunks(
        self, document_id: str, *, page: int | None, heading: str | None
    ) -> list[Passage]:
        params: dict[str, Any] = {"limit": 20}
        if page is not None:
            params["page"] = page
        if heading:
            params["heading"] = heading
        data = await self._request("GET", f"/documents/{document_id}/chunks", params=params)
        documents = {d.id: d.filename for d in await self.list_documents()}
        return [
            Passage(
                document_id=document_id,
                filename=documents.get(document_id, document_id),
                page=c["page"],
                section=_section(c["heading_path"]),
                text=c["text"],
            )
            for c in data
        ]
