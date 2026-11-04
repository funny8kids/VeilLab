from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("veilpool_api")

_TITLES = {
    "NOT_FOUND": "Not found",
    "METHOD_NOT_ALLOWED": "Method not allowed",
    "POOL_NOT_FOUND": "Pool not found",
    "POOL_PAUSED": "Pool paused",
    "POOL_RETIRED": "Pool retired",
    "AMOUNT_MISMATCH": "Amount mismatch",
    "COMMITMENT_MISMATCH": "Commitment mismatch",
    "INVALID_AMOUNT": "Invalid amount",
    "ROOT_STALE": "Stale Merkle root",
    "NULLIFIER_SPENT": "Nullifier already spent",
    "QUOTE_EXPIRED": "Quote expired",
    "QUOTE_NOT_FOUND": "Quote not found",
    "QUOTE_USED": "Quote already used",
    "QUOTE_CONSUMED": "Quote already consumed",
    "UNKNOWN_ROOT": "Unknown Merkle root",
    "INVALID_PROOF": "Invalid proof encoding",
    "INVALID_PUBLIC_SIGNALS": "Invalid public signals",
    "INVALID_COMMITMENT": "Invalid commitment",
    "NON_CANONICAL_COMMITMENT": "Non-canonical commitment",
    "COMMITMENT_NOT_FOUND": "Commitment not found",
    "COMPLIANCE_BLOCKED": "Compliance blocked",
    "COMPLIANCE_REVIEW": "Compliance review required",
    "COMPLIANCE_EXPIRED": "Compliance decision expired",
    "POLICY_NOT_FOUND": "Compliance policy not found",
    "FEE_EXCEEDS_DENOMINATION": "Fees exceed denomination",
    "RELAYER_OFFLINE": "Relayer offline",
    "RELAYER_NOT_FOUND": "Relayer not found",
    "RELAYER_UNSUPPORTED": "Relayer does not support this pool",
    "PROOF_INVALID": "Proof invalid",
    "IDEMPOTENCY_MISMATCH": "Idempotency key reuse with a different request",
    "IDEMPOTENCY_KEY_REQUIRED": "Idempotency key required",
    "DEPOSIT_NOT_FOUND": "Deposit not found",
    "WITHDRAWAL_NOT_FOUND": "Withdrawal not found",
    "INTENT_NOT_FOUND": "Deposit intent not found",
    "INTENT_EXPIRED": "Deposit intent expired",
    "INTENT_CONSUMED": "Deposit intent already consumed",
    "DUPLICATE_TX": "Duplicate mock transaction",
    "ADMIN_UNAUTHORIZED": "Admin authorization required",
    "AUTH_REQUIRED": "Authentication required",
    "RATE_LIMITED": "Too many requests",
    "REQUEST_TOO_LARGE": "Request body too large",
    "INVALID_CONTENT_LENGTH": "Invalid Content-Length",
    "REVIEW_NOT_FOUND": "Compliance review not found",
    "REVIEW_ALREADY_DECIDED": "Compliance review already decided",
    "MOCK_ONLY": "Endpoint available in mock mode only",
    "LOCAL_ONLY": "Endpoint available in local Anvil mode only",
    "LOCAL_DEPOSIT_DISABLED": "Local auto-deposit disabled",
    "LOCAL_WITHDRAWAL_DISABLED": "Local auto-withdrawal disabled",
    "INDEXER_UNAVAILABLE": "Indexer unavailable",
    "INDEXER_TIMEOUT": "Indexer timeout",
    "INDEXER_BAD_RESPONSE": "Invalid indexer response",
    "INDEXER_MISMATCH": "Indexer/local chain mismatch",
    "INDEXER_CONFIRMATION_TIMEOUT": "Indexer confirmation timeout",
    "WITHDRAWAL_REVERTED": "Local withdrawal transaction reverted",
    "LOCAL_RPC_UNAVAILABLE": "Local Anvil RPC unavailable",
    "LOCAL_RPC_TIMEOUT": "Local Anvil RPC timeout",
    "LOCAL_RPC_BAD_RESPONSE": "Invalid local Anvil RPC response",
    "LOCAL_RPC_ERROR": "Local Anvil RPC rejected the transaction",
    "LOCAL_RPC_BAD_REQUEST": "Invalid local Anvil RPC request",
    "VALIDATION_ERROR": "Request validation failed",
    "INTERNAL_ERROR": "Internal error",
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra or {}
        self.headers = headers or {}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def build_problem(
    *,
    request_id: str | None,
    status_code: int,
    code: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an RFC 9457-style problem response.

    Kept public so ASGI middleware can emit the same error shape as routes
    without going through FastAPI's exception handlers.
    """

    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _TITLES.get(code, code.replace("_", " ").title()),
        "status": status_code,
        "code": code,
        "detail": detail,
        "request_id": request_id,
    }
    if extra:
        body.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )


def _problem(
    request: Request,
    status_code: int,
    code: str,
    detail: str,
    *,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return build_problem(
        request_id=_request_id(request),
        status_code=status_code,
        code=code,
        detail=detail,
        extra=extra,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _problem(
            request,
            exc.status_code,
            exc.code,
            exc.detail,
            extra=exc.extra,
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = {
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }.get(exc.status_code, "HTTP_ERROR")
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _problem(request, exc.status_code, code, detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Never echo submitted values: addresses and client secrets must not
        # appear in errors, logs or traces.
        errors = [
            {
                "loc": [str(part) for part in item.get("loc", ())],
                "msg": item.get("msg", "invalid value"),
                "type": item.get("type", "value_error"),
            }
            for item in exc.errors()[:20]
        ]
        return _problem(
            request,
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            extra={"errors": errors},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled API error request_id=%s", _request_id(request)
        )
        return _problem(
            request,
            500,
            "INTERNAL_ERROR",
            "An unexpected error occurred. Use the request id for support.",
        )
