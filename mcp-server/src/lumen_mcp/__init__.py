"""Lumen MCP server.

    lumen-mcp stdio                       # for Claude Code / Claude Desktop / VS Code (local)
    lumen-mcp http --port 8765            # Streamable HTTP at /mcp, needs LUMEN_MCP_TOKEN

Environment: LUMEN_API_URL (default http://localhost:8000), LUMEN_MCP_TOKEN (HTTP only).
"""

import argparse
import os
import sys

import uvicorn

from lumen_mcp.auth import BearerTokenMiddleware
from lumen_mcp.client import HttpLumenApi
from lumen_mcp.server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="lumen-mcp", description="Lumen MCP server")
    sub = parser.add_subparsers(dest="transport", required=True)
    sub.add_parser("stdio", help="talk MCP over stdin/stdout (local clients)")
    http = sub.add_parser("http", help="serve Streamable HTTP at /mcp (bearer token required)")
    http.add_argument("--host", default="127.0.0.1")
    http.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    api = HttpLumenApi(os.environ.get("LUMEN_API_URL", "http://localhost:8000"))
    server = build_server(api)

    if args.transport == "stdio":
        server.run("stdio")
        return

    token = os.environ.get("LUMEN_MCP_TOKEN", "")
    if not token:
        sys.exit("Set LUMEN_MCP_TOKEN to a long random string to use the HTTP transport.")
    app = BearerTokenMiddleware(server.streamable_http_app(host=args.host), token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
