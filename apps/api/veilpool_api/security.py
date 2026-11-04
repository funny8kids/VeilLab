from __future__ import annotations

import hashlib
import hmac
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .errors import build_problem
from .ids import new_id

PUBLIC_EXACT_PATHS = frozenset(
    {
        "/api/v1/health",
        "/api/v1/compliance/policy",
    }
)
PUBLIC_PATH_PREFIXES = (
    "/api/v1/pools",
    "/api/v1/relayers",
)

_RATE_LIMIT_ROUTES = {
    ("POST", "/api/v1/deposits/intent"): "deposit_intent",
    ("POST", "/api/v1/withdrawals/quote"): "withdrawal_quote",
    ("POST", "/api/v1/withdrawals/submit"): "withdrawal_submit",
    ("POST", "/api/v1/local/deposits"): "local_deposit",
    ("POST", "/api/v1/local/withdrawals"): "local_withdrawal",
}


class _BodyTooLarge(Exception):
    pass


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def is_public_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if normalized in PUBLIC_EXACT_PATHS:
        return True
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in PUBLIC_PATH_PREFIXES
    )


def rate_limit_scope(path: str, method: str) -> str | None:
    normalized = _normalize_path(path)
    scoped = _RATE_LIMIT_ROUTES.get((method.upper(), normalized))
    if scoped is not None:
        return scoped
    if (
        normalized.startswith("/api/v1/pools/")
        and "/path/" in normalized
    ):
        return "pool_path"
    if normalized == "/api/v1/compliance" or normalized.startswith(
        "/api/v1/compliance/"
    ):
        return "compliance"
    if normalized == "/api/v1/admin" or normalized.startswith("/api/v1/admin/"):
        return "admin"
    return None


def rate_limits_from_settings(settings: Settings) -> dict[str, int]:
    return {
        "deposit_intent": settings.rate_limit_deposit_intent,
        "withdrawal_quote": settings.rate_limit_withdrawal_quote,
        "withdrawal_submit": settings.rate_limit_withdrawal_submit,
        "compliance": settings.rate_limit_compliance,
        "admin": settings.rate_limit_admin,
        "local_deposit": settings.rate_limit_local_deposit,
        "local_withdrawal": settings.rate_limit_local_withdrawal,
        "pool_path": settings.rate_limit_pool_path,
    }


def bearer_token(headers: Headers) -> str | None:
    value = headers.get("authorization")
    if not value:
        return None
    parts = value.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def _token_matches(supplied: str | None, expected: str) -> bool:
    if supplied is None:
        return False
    return hmac.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
    )


def request_identity(scope: Scope, headers: Headers) -> str:
    """Bucket key: a hash of the bearer token, otherwise the client IP.

    The raw token is never retained, logged or exposed. Forwarded-for headers
    are deliberately not trusted because this MVP can be run without a trusted
    reverse proxy.
    """

    token = bearer_token(headers)
    if token:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
        return f"token:{digest}"
    client = scope.get("client")
    host = client[0] if client else "unknown"
    return f"ip:{host}"


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Small in-memory token bucket store.

    Each ``(scope, identity)`` pair gets an independent bucket. Buckets refill
    continuously at ``limit / window_seconds`` tokens per second.
    """

    def __init__(
        self,
        limits: dict[str, int],
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = {name: int(value) for name, value in limits.items()}
        self._window_seconds = max(1.0, float(window_seconds))
        self._clock = clock
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._lock = threading.Lock()
        self._checks = 0

    def check(self, scope: str, identity: str) -> RateLimitResult:
        limit = self._limits.get(scope, 0)
        if limit <= 0:
            return RateLimitResult(True, limit=0, remaining=0, retry_after=0)

        now = self._clock()
        refill_per_second = limit / self._window_seconds
        key = (scope, identity)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(float(limit), now)
            else:
                elapsed = max(0.0, now - bucket.updated_at)
                bucket.tokens = min(
                    float(limit), bucket.tokens + elapsed * refill_per_second
                )
                bucket.updated_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                allowed = True
                retry_after = 0
            else:
                allowed = False
                retry_after = max(
                    1, math.ceil((1.0 - bucket.tokens) / refill_per_second)
                )

            self._buckets[key] = bucket
            self._checks += 1
            if self._checks % 512 == 0:
                cutoff = now - self._window_seconds * 2
                stale = [
                    existing
                    for existing, value in self._buckets.items()
                    if value.updated_at < cutoff
                ]
                for existing in stale:
                    self._buckets.pop(existing, None)

            return RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=max(0, int(bucket.tokens)),
                retry_after=retry_after,
            )


def _content_length(headers: Headers) -> int | None:
    values = headers.getlist("content-length")
    if not values:
        return None
    if len(set(values)) != 1:
        raise ValueError("conflicting Content-Length headers")
    raw = values[0].strip()
    if not raw.isdigit():
        raise ValueError("Content-Length must be a non-negative integer")
    return int(raw)


def _request_id_from(headers: Headers) -> str:
    supplied = headers.get("x-request-id", "")
    if (
        supplied
        and len(supplied) <= 128
        and all(ch.isalnum() or ch in "-_" for ch in supplied)
    ):
        return supplied
    return new_id("req")


class SecurityMiddleware:
    """Auth, rate limiting, body limits and security headers.

    Public paths stay readable when ``require_auth`` is enabled, matching the
    demo contract: health, pools, relayers and the compliance policy summary.
    Admin routes still require ``X-Admin-Token`` in addition to the bearer
    token when auth is enabled.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.limiter = limiter or TokenBucketRateLimiter(
            rate_limits_from_settings(settings),
            window_seconds=settings.rate_limit_window_seconds,
        )

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = _request_id_from(headers)
        scope.setdefault("state", {})["request_id"] = request_id
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        public = is_public_path(path)

        if method != "OPTIONS":
            try:
                content_length = _content_length(headers)
            except ValueError:
                await self._problem(
                    scope,
                    receive,
                    send,
                    request_id=request_id,
                    public=public,
                    status_code=400,
                    code="INVALID_CONTENT_LENGTH",
                    detail="The Content-Length header is invalid.",
                    headers={"Connection": "close"},
                )
                return
            if (
                content_length is not None
                and content_length > self.settings.max_body_bytes
            ):
                await self._problem(
                    scope,
                    receive,
                    send,
                    request_id=request_id,
                    public=public,
                    status_code=413,
                    code="REQUEST_TOO_LARGE",
                    detail=(
                        "The request body exceeds the configured maximum of "
                        f"{self.settings.max_body_bytes} bytes."
                    ),
                    headers={"Connection": "close"},
                )
                return

            if self.settings.require_auth and not public:
                token = bearer_token(headers)
                if not _token_matches(token, self.settings.api_token):
                    await self._problem(
                        scope,
                        receive,
                        send,
                        request_id=request_id,
                        public=public,
                        status_code=401,
                        code="AUTH_REQUIRED",
                        detail=(
                            "A valid Authorization: Bearer token is required "
                            "for this endpoint."
                        ),
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                    return

            rate_result: RateLimitResult | None = None
            rate_scope: str | None = None
            if self.settings.rate_limit_enabled:
                scoped = rate_limit_scope(path, method)
                if scoped is not None:
                    rate_scope = scoped
                    rate_result = self.limiter.check(
                        scoped, request_identity(scope, headers)
                    )
                    if not rate_result.allowed:
                        await self._problem(
                            scope,
                            receive,
                            send,
                            request_id=request_id,
                            public=public,
                            status_code=429,
                            code="RATE_LIMITED",
                            detail="Too many requests. Retry after the indicated delay.",
                            headers={
                                "Retry-After": str(rate_result.retry_after),
                                "X-RateLimit-Limit": str(rate_result.limit),
                                "X-RateLimit-Remaining": "0",
                                "X-RateLimit-Scope": scoped,
                            },
                        )
                        return
        else:
            rate_result = None
            rate_scope = None

        # POST/PUT/PATCH bodies are buffered up to the cap before routing. This
        # enforces the limit for both Content-Length and HTTP/1.1 chunked
        # uploads, and lets the request be replayed to FastAPI unchanged.
        replay_body: bytes | None = None
        if method in {"POST", "PUT", "PATCH"}:
            chunks: list[bytes] = []
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > self.settings.max_body_bytes:
                    await self._problem(
                        scope,
                        receive,
                        send,
                        request_id=request_id,
                        public=public,
                        status_code=413,
                        code="REQUEST_TOO_LARGE",
                        detail=(
                            "The request body exceeds the configured maximum "
                            f"of {self.settings.max_body_bytes} bytes."
                        ),
                        headers={"Connection": "close"},
                    )
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            replay_body = b"".join(chunks)

        received = 0
        replay_delivered = False
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
                response_headers["X-VeilPool-Mode"] = self.settings.mode
                response_headers["X-VeilPool-Mock"] = (
                    "true" if self.settings.mode == "mock" else "false"
                )
                response_headers["X-Content-Type-Options"] = "nosniff"
                response_headers["Referrer-Policy"] = "no-referrer"
                if not public:
                    response_headers["Cache-Control"] = "no-store"
                if rate_result is not None:
                    response_headers["X-RateLimit-Limit"] = str(
                        rate_result.limit
                    )
                    response_headers["X-RateLimit-Remaining"] = str(
                        rate_result.remaining
                    )
                    if rate_scope is not None:
                        response_headers["X-RateLimit-Scope"] = rate_scope
            await send(message)

        async def receive_with_limit() -> Message:
            nonlocal received, replay_delivered
            if replay_body is not None:
                if replay_delivered:
                    return {"type": "http.disconnect"}
                replay_delivered = True
                received = len(replay_body)
                return {
                    "type": "http.request",
                    "body": replay_body,
                    "more_body": False,
                }
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.settings.max_body_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, receive_with_limit, send_with_headers)
        except _BodyTooLarge:
            if response_started:
                return
            await self._problem(
                scope,
                receive,
                send,
                request_id=request_id,
                public=public,
                status_code=413,
                code="REQUEST_TOO_LARGE",
                detail=(
                    "The request body exceeds the configured maximum of "
                    f"{self.settings.max_body_bytes} bytes."
                ),
                headers={"Connection": "close"},
            )

    def _security_headers(
        self,
        *,
        request_id: str,
        public: bool,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers = {
            "X-Request-ID": request_id,
            "X-VeilPool-Mode": self.settings.mode,
            "X-VeilPool-Mock": "true" if self.settings.mode == "mock" else "false",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        }
        if not public:
            headers["Cache-Control"] = "no-store"
        if extra:
            headers.update(extra)
        return headers

    async def _problem(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        request_id: str,
        public: bool,
        status_code: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = build_problem(
            request_id=request_id,
            status_code=status_code,
            code=code,
            detail=detail,
            headers=self._security_headers(
                request_id=request_id, public=public, extra=headers
            ),
        )
        await response(scope, receive, send)
