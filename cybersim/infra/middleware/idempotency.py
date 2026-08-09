"""Idempotency middleware (docs/08 Â§7, docs/21 Task 4.1).

For non-GET mutating routes, requires an `Idempotency-Key` header; replays the
cached response for 24h keyed by (org, key). In-memory store for dev/tests;
Phase 9 wires Redis-backed store behind the same interface.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from cybersim.infra.errors import ErrorCode, problem_detail

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
#: Routes that require an Idempotency-Key (docs/08 Â§7).
_IDEMPOTENT_ROUTE_PREFIXES = (
    "/v1/simulations",
    "/v1/billing/checkout",
    "/v1/missions/",
)


class IdempotencyStore(Protocol):
    def get(self, dedup_id: str) -> dict[str, Any] | None: ...
    def put(self, dedup_id: str, status: int, body: bytes) -> None: ...


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, store: IdempotencyStore | None = None) -> None:
        super().__init__(app)
        self._store = store or InMemoryIdempotencyStore()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not _requires_idempotency(request):
            return await call_next(request)
        key = request.headers.get("Idempotency-Key")
        if not key:
            return JSONResponse(
                status_code=400,
                content=problem_detail(
                    ErrorCode.IDEMPOTENCY_KEY_REQUIRED,
                    "Idempotency-Key header is required for this request.",
                    instance=str(request.url.path),
                ),
            )
        org_id = request.headers.get("X-Org-ID", "anon")
        dedup_id = hashlib.sha256(f"{org_id}:{key}".encode()).hexdigest()

        cached = self._store.get(dedup_id)
        if cached is not None:
            return Response(
                content=cached["body"],
                status_code=cached["status"],
                media_type="application/json",
                headers={"X-Idempotent-Replay": "true"},
            )

        response = await call_next(request)
        if response.status_code < 500:
            body = await _read_body(response)
            self._store.put(dedup_id, response.status_code, bytes(body))
            # Rebuild the response so downstream sees the body we cached.
            return Response(
                content=bytes(body),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        return response


def _requires_idempotency(request: Request) -> bool:
    if request.method not in _MUTATING_METHODS:
        return False
    path = urlparse(str(request.url)).path
    return any(path.startswith(prefix) for prefix in _IDEMPOTENT_ROUTE_PREFIXES)


class InMemoryIdempotencyStore(IdempotencyStore):
    """Dict-backed store with 24h TTL."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def get(self, dedup_id: str) -> dict[str, Any] | None:
        entry = self._data.get(dedup_id)
        if entry is None:
            return None
        if entry["ts"] + 86_400 < time.time():
            self._data.pop(dedup_id, None)
            return None
        return entry

    def put(self, dedup_id: str, status: int, body: bytes) -> None:
        self._data[dedup_id] = {"status": status, "body": body, "ts": time.time()}


async def _read_body(response: Response) -> bytes:
    """Read the full body of `response`, handling streaming responses."""
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray, memoryview)):
        if isinstance(body, memoryview):
            body = body.tobytes()
        return bytes(body)
    # StreamingResponse exposes `body_iterator`.
    iterator = getattr(response, "body_iterator", None)
    if iterator is None:
        return b""
    chunks = [chunk async for chunk in iterator]
    return b"".join(chunks)
