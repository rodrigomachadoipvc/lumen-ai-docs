# Use Lumen from other AI tools (MCP)

The `mcp-server/` package exposes Lumen as a [Model Context Protocol](https://modelcontextprotocol.io)
server. Claude Code, Claude Desktop, VS Code and other MCP clients can then search your
documents and cite them, using the models those tools already have.

```
Claude Code / Claude Desktop / VS Code ──MCP──► lumen-mcp ──REST──► Lumen API ──► PostgreSQL
```

## Tools

| Tool | What it does |
| --- | --- |
| `search_documents(query, limit=5, documents?)` | Hybrid search. Returns passages with filename, page, section and similarity. |
| `get_document_section(document, page? \| heading?)` | Reads one page or one section of a document, in order. |
| `list_documents()` | Lists the documents with their type, status, pages and language. |

You can refer to documents by id, by filename, or by the words in the name ("regulamento
teletrabalho").

## Requirements

The Lumen API must be running (see the main README). Install the server once:

```bash
cd mcp-server
uv sync
```

`LUMEN_API_URL` sets where the API is (default `http://localhost:8000`).

## Claude Code

```bash
claude mcp add --transport stdio lumen -- uv run --directory /absolute/path/to/lumen-ai-docs/mcp-server lumen-mcp stdio
```

Add `--scope user` to make it available in every project. Then ask, for example: *"Use lumen to
find how many telework days per week are allowed, and cite the page."*

## Claude Desktop

Edit `claude_desktop_config.json`. It is in `%APPDATA%\Claude\` on Windows and
`~/Library/Application Support/Claude/` on macOS (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "lumen": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:\\path\\to\\lumen-ai-docs\\mcp-server",
        "lumen-mcp",
        "stdio"
      ]
    }
  }
}
```

Then restart Claude Desktop completely.

## VS Code

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "lumen": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/lumen-ai-docs/mcp-server", "lumen-mcp", "stdio"]
    }
  }
}
```

## Over HTTP (optional)

For a client that connects to a URL rather than starting a process, run the Streamable HTTP
transport. It requires a bearer token of at least 16 characters:

```bash
cd mcp-server
LUMEN_MCP_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))") uv run lumen-mcp http --port 8765
```

The endpoint is `http://127.0.0.1:8765/mcp`, and it only listens on localhost by default. In Claude
Code:

```bash
claude mcp add --transport http lumen http://127.0.0.1:8765/mcp --header "Authorization: Bearer <token>"
```

In VS Code, use an input variable so the token is not written to the file:

```json
{
  "inputs": [{ "type": "promptString", "id": "lumen-token", "description": "Lumen MCP token", "password": true }],
  "servers": {
    "lumen": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer ${input:lumen-token}" }
    }
  }
}
```

## Security notes

- The server has read-only tools. It cannot upload, change or delete documents.
- Passage text comes from your files. The server's instructions tell clients to treat it as data,
  not as instructions.
- The HTTP transport compares tokens in constant time and returns `401` without one. Keep it on
  `127.0.0.1` unless you put it behind TLS.
