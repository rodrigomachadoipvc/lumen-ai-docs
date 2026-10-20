# 0007. MCP server as a separate package that talks to the REST API

- Status: accepted
- Date: 2026-10-20

## Context

Lumen should be usable as a knowledge source from AI tools the user already has: Claude Code,
Claude Desktop and VS Code. The Model Context Protocol is how these tools discover and call
external tools. The official Python SDK (`mcp`) is now at 2.x, where `FastMCP` became `MCPServer`
and transport options moved to `run()`.

## Decision

- A separate package, `mcp-server/` (`lumen-mcp`), built on `mcp.server.mcpserver.MCPServer`, with
  three read-only tools: `search_documents`, `get_document_section` and `list_documents`.
- It calls the Lumen **REST API** (`POST /search`, `GET /documents`,
  `GET /documents/{id}/chunks`) instead of the database, so it shares validation, filters and
  logs with the web app, and can run anywhere the API is reachable.
- **stdio** transport for local clients, and **Streamable HTTP** (`/mcp`) for URL-based clients.
  HTTP needs a static bearer token (`LUMEN_MCP_TOKEN`, at least 16 characters), checked by a small
  ASGI middleware with `secrets.compare_digest`.
- Expected failures (unknown document, API down) raise `LumenError`, a subclass of the SDK's
  `ToolError`, so their message reaches the model. Any other exception becomes a generic error, so
  internal details stay on the server.
- Tests use the SDK's in-process `Client(server)` with a fake API, `httpx2.MockTransport` for the
  REST client, and `ASGITransport` for the token middleware.

## Alternatives considered

- **Tools inside the FastAPI app**: one process fewer, but it couples MCP to the web backend and
  makes the server harder to run on its own.
- **OAuth via the SDK's `AuthSettings`**: the right choice for multi-user remote servers, but it
  needs an authorization server. A local single-user install does not have one.
- **Exposing write tools (upload, delete)**: not needed for a knowledge source, and risky to give
  to an autonomous agent.

## Consequences

- The API must be running for the MCP server to work. The tools report this clearly ("Is it
  running?").
- Answers produced through MCP are written by the client's model (Claude, Copilot…), which cites
  the filenames and pages the tools return.
