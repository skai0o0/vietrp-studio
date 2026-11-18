"""Standard error body: {"error": {"code": "<snake_case>", "message": "<English>"}}.

The backend never sends Vietnamese text; the frontend maps `code` to a UI string.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}


class AppError(Exception):
    """A deliberate, user-facing failure with a stable machine code."""

    def __init__(self, code: str, message: str, status: int = 400, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.headers = headers


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _error_response(code: str, message: str, status: int, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message), status_code=status, headers=headers)


async def _handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _error_response(exc.code, exc.message, exc.status, exc.headers)


async def _handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only locations and messages: never echo `input`, which may hold a passphrase or an API key.
    parts = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
    return _error_response("validation_error", "Request validation failed: " + "; ".join(parts), 422)


async def _handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    return _error_response(code, str(exc.detail), exc.status_code, dict(exc.headers) if exc.headers else None)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return _error_response("internal_error", "Internal server error", 500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
