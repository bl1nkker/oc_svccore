from flask import Response
from opentelemetry import trace


def current_trace_id() -> str | None:
    span = trace.get_current_span().get_span_context()
    return format(span.trace_id, "032x") if span.is_valid else None


def add_trace_id_header(response: Response) -> Response:
    if trace_id := current_trace_id():
        response.headers["X-Request-Id"] = trace_id
    return response
