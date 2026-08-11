"""Rate-limit middleware (docs/08 Â§6, docs/21 Task 4.1).

Per-route buckets; in-memory token bucket for dev/tests. Phase 9 swaps in a
Redis-backed token bucket (Lua) behind the same API.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from cybersim.infra.errors import ErrorCode, problem_detail

#: (route_prefix, limit, window_sec) â€” docs/08 Â§6 default tier.
_DEFAULT_LIMITS: tuple[tuple[str, int, int], ...] = (
    ("/v1/auth/", 100, 60),  # auth endpoints: 100/min anonymous
    ("/v1/simulations", 200, 3600),  # sim starts: 200/hr
    ("/v1/knowledge/", 600, 60),  # knowledge: 600/min
    ("/v1/", 3000, 60),  # default: 3000/min
)

_RATE_LIMIT_HEADERS = ("RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset")


class TokenBucket(Protocol):
    def allow(self, key: str, limit: int, window_sec: int) -> tuple[bool, int, float]: ...


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, bucket: TokenBucket | None = None) -> None:
        super().__init__(app)
        self._bucket = bucket or InMemoryTokenBucket()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        limit, window = self._limit_for(path)
        host = request.client.host if request.client else "anon"
        key = request.headers.get("X-Org-ID") or host

        allowed, remaining, reset_in = self._bucket.allow(key, limit, window)
        headers = {
            "RateLimit-Limit": str(limit),
            "RateLimit-Remaining": str(remaining),
            "RateLimit-Reset": str(int(reset_in)),
        }
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=problem_detail(
                    ErrorCode.RATE_LIMITED,
                    f"Rate limit exceeded for {path!r} ({limit} per {window}s).",
                    instance=path,
                ),
                headers={**headers, "Retry-After": str(int(reset_in))},
            )
        response = await call_next(request)
        for header in _RATE_LIMIT_HEADERS:
            response.headers[header] = headers[header]
        return response

    def _limit_for(self, path: str) -> tuple[int, int]:
        for prefix, limit, window in _DEFAULT_LIMITS:
            if path.startswith(prefix):
                return limit, window
        return 300, 60


class InMemoryTokenBucket:
    """Sliding-window counter per key (dev/test)."""

    def __init__(self) -> None:
        self._counts: dict[str, list[float]] = {}

    def allow(self, key: str, limit: int, window_sec: int) -> tuple[bool, int, float]:
        now = time.time()
        bucket = [t for t in self._counts.get(key, []) if now - t < window_sec]
        remaining = max(0, limit - len(bucket))
        if remaining > 0:
            bucket.append(now)
            self._counts[key] = bucket
        else:
            self._counts[key] = bucket
        reset_in = window_sec - (now - bucket[0]) if bucket else float(window_sec)
        return (remaining > 0, remaining, reset_in)
