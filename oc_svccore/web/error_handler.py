import logging
from http import HTTPStatus
from typing import Any

from flask import Flask
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from oc_svccore.errors import (
    BaseError,
    ConflictError,
    InvalidDataError,
    NotFoundError,
    PermissionDeniedError,
    UnauthorizedError,
    UpstreamError,
    UpstreamUnavailableError,
)
from oc_svccore.web.observability.trace_id import current_trace_id

log = logging.getLogger(__name__)

DEFAULT_STATUSES: dict[type[BaseError], int] = {
    BaseError: 400,
    InvalidDataError: 400,
    UnauthorizedError: 401,
    PermissionDeniedError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    UpstreamError: 502,
    UpstreamUnavailableError: 503,
}


def register_error_handlers(app: Flask, errors_mapping: dict[type[BaseError], int] | None = None) -> None:
    statuses = {**DEFAULT_STATUSES, **(errors_mapping or {})}
    app.register_error_handler(BaseError, _base_error_handler(statuses))
    app.register_error_handler(ValidationError, _validation_error_handler)
    app.register_error_handler(HTTPException, _http_exception_handler)
    app.register_error_handler(Exception, _unhandled_error_handler)


def error_body(message: str, code: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"message": message, "code": code, "data": data or {}}
    if trace_id := current_trace_id():
        body["traceId"] = trace_id
    return body


def _status_for(exc: BaseError, statuses: dict[type[BaseError], int]) -> int:
    for cls in type(exc).__mro__:
        if cls in statuses:
            return statuses[cls]
    return 400


def _base_error_handler(statuses: dict[type[BaseError], int]):
    def handle(exc: BaseError):
        status = _status_for(exc, statuses)
        if status >= 500:
            log.error(exc.message, exc_info=exc)
        return error_body(exc.message, exc.code, exc.data), status

    return handle


def _validation_error_handler(exc: ValidationError):
    errors = [{"field": _field(e["loc"]), "message": f"_err_msg_{e['type']}"} for e in exc.errors()]
    return error_body("_err_msg_validation", "validation", {"errors": errors}), 400


def _field(loc: tuple[int | str, ...]) -> str:
    return "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in loc).lstrip(".")


def _http_exception_handler(exc: HTTPException):
    if exc.code >= 500:
        log.error(exc.description or exc.name, exc_info=exc)
    code = HTTPStatus(exc.code).name.lower()
    return error_body(f"_err_msg_{code}", code), exc.code


def _unhandled_error_handler(exc: Exception):
    log.error("unhandled error", exc_info=exc)
    return error_body("_err_msg_internal", "internal"), 500
