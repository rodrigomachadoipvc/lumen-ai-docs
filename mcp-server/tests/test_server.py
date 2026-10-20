import json
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp_types import CallToolResult, TextContent
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from lumen_mcp.auth import BearerTokenMiddleware
from lumen_mcp.client import (
    DocumentInfo,
    HttpLumenApi,
    LumenError,
    Passage,
    resolve_document,
)
from lumen_mcp.server import build_server

DOCS = [
    DocumentInfo(
        id="doc-pdf",
        filename="regulamento-teletrabalho.pdf",
        type="pdf",
        status="ready",
        pages=5,
        passages=17,
        language="portuguese",
    ),
    DocumentInfo(
        id="doc-md",
        filename="employee-handbook.md",
        type="markdown",
        status="ready",
        pages=None,
        passages=14,
        language="english",
    ),
]
PASSAGE = Passage(
    document_id="doc-pdf",
    filename="regulamento-teletrabalho.pdf",
    page=3,
    section="Capítulo II > Artigo 7.º",
    text="O número máximo de dias de teletrabalho é de 3 dias por semana.",
    score=0.84,
)


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def search(
        self, query: str, *, limit: int, document_ids: list[str] | None
    ) -> list[Passage]:
        self.calls.append(("search", {"query": query, "limit": limit, "ids": document_ids}))
        return [PASSAGE]

    async def list_documents(self) -> list[DocumentInfo]:
        return DOCS

    async def chunks(
        self, document_id: str, *, page: int | None, heading: str | None
    ) -> list[Passage]:
        self.calls.append(("chunks", {"id": document_id, "page": page, "heading": heading}))
        return [PASSAGE]


def _text(result: CallToolResult) -> str:
    return " ".join(block.text for block in result.content if isinstance(block, TextContent))


async def test_tools_are_listed_with_schemas() -> None:
    async with Client(build_server(FakeApi())) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {"search_documents", "list_documents", "get_document_section"}
    assert tools["search_documents"].input_schema["required"] == ["query"]


async def test_search_resolves_document_names() -> None:
    api = FakeApi()
    async with Client(build_server(api)) as client:
        result = await client.call_tool(
            "search_documents", {"query": "teletrabalho", "documents": ["Regulamento Teletrabalho"]}
        )

    assert not result.is_error
    assert api.calls == [("search", {"query": "teletrabalho", "limit": 5, "ids": ["doc-pdf"]})]
    passages = result.structured_content["result"]
    assert passages[0]["page"] == 3 and "3 dias" in passages[0]["text"]


async def test_section_and_errors_reach_the_model() -> None:
    api = FakeApi()
    async with Client(build_server(api)) as client:
        ok = await client.call_tool(
            "get_document_section", {"document": "employee handbook", "heading": "Vacation"}
        )
        missing = await client.call_tool("get_document_section", {"document": "nope", "page": 1})
        no_target = await client.call_tool("get_document_section", {"document": "doc-md"})

    assert not ok.is_error
    assert api.calls[-1] == ("chunks", {"id": "doc-md", "page": None, "heading": "Vacation"})
    assert missing.is_error and "No single document matches 'nope'" in _text(missing)
    assert no_target.is_error and "Give a page or a heading" in _text(no_target)


def test_resolve_document() -> None:
    assert resolve_document("doc-md", DOCS).filename == "employee-handbook.md"
    assert resolve_document("EMPLOYEE-HANDBOOK.MD", DOCS).id == "doc-md"
    with pytest.raises(LumenError):
        resolve_document("handbook regulamento", DOCS)


async def test_http_client_maps_api_responses() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/search":
            assert json.loads(request.content) == {"query": "x", "limit": 2}
            hit = {
                "document_id": "doc-pdf",
                "filename": "reg.pdf",
                "page": 3,
                "heading_path": ["A", "B"],
                "text": "t",
                "similarity": 0.5,
            }
            return httpx2.Response(200, json={"hits": [hit]})
        return httpx2.Response(404, json={"error": {"message": "Document not found."}})

    api = HttpLumenApi("http://lumen", transport=httpx2.MockTransport(handler))
    passages = await api.search("x", limit=2, document_ids=None)
    with pytest.raises(LumenError, match="404: Document not found"):
        await api.chunks("missing", page=1, heading=None)
    await api.aclose()

    assert passages[0].section == "A > B"


async def test_unreachable_api_has_a_clear_error() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    api = HttpLumenApi("http://localhost:1", transport=httpx2.MockTransport(refuse))
    with pytest.raises(LumenError, match="Is it running"):
        await api.list_documents()
    await api.aclose()


async def test_bearer_token_is_required() -> None:
    async def ok(_: Any) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = BearerTokenMiddleware(Starlette(routes=[Route("/mcp", ok)]), "s3cret-token-0123456789")
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as http:
        missing = await http.get("/mcp")
        wrong = await http.get("/mcp", headers={"Authorization": "Bearer nope"})
        right = await http.get("/mcp", headers={"Authorization": "Bearer s3cret-token-0123456789"})

    assert missing.status_code == wrong.status_code == 401
    assert missing.headers["www-authenticate"].startswith("Bearer")
    assert right.status_code == 200


def test_short_tokens_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least 16"):
        BearerTokenMiddleware(Starlette(), "short")
