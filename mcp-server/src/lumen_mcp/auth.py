"""Bearer-token check for the Streamable HTTP transport.

A single shared token is enough for a local, single-user setup. The SDK's OAuth support
(`AuthSettings`) needs an authorization server, which a local install does not have.
"""

import secrets
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send


class BearerTokenMiddleware:
    def __init__(self, app: ASGIApp, token: str) -> None:
        if len(token) < 16:
            raise ValueError("LUMEN_MCP_TOKEN must be at least 16 characters long.")
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # lifespan events pass through
            await self._app(scope, receive, send)
            return
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        scheme, _, credentials = headers.get(b"authorization", b"").partition(b" ")
        if scheme.lower() == b"bearer" and secrets.compare_digest(credentials, self._token):
            await self._app(scope, receive, send)
            return
        await _unauthorized(send)


async def _unauthorized(send: Send) -> None:
    body = b'{"error": "missing or invalid bearer token"}'
    start: dict[str, Any] = {
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", b'Bearer realm="lumen"'),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    await send(start)
    await send({"type": "http.response.body", "body": body})
