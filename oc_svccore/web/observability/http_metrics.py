import re
import time
from collections.abc import Collection

from flask import Flask, Response, g, request
from prometheus_client import Counter, Histogram

from oc_svccore.metrics.registry import BUCKETS, get_or_create

_RULE_PARAM = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


def instrument_requests(app: Flask, skip_paths: Collection[str]) -> None:
    requests_total = get_or_create(Counter, "http_requests", "HTTP requests served", ("method", "route", "status"))
    duration = get_or_create(Histogram, "http_request_duration_seconds", "HTTP request latency", ("method", "route"),
                             buckets=BUCKETS)

    def start() -> None:
        g.oc_svccore_metrics_started = time.perf_counter()

    def observe(response: Response) -> Response:
        started = g.pop("oc_svccore_metrics_started", None)
        if started is not None and request.path not in skip_paths:
            route = _RULE_PARAM.sub(r"{\1}", request.url_rule.rule) if request.url_rule else "unmatched"
            method = request.method if request.method in _METHODS else "OTHER"
            requests_total.labels(method, route, str(response.status_code)).inc()
            duration.labels(method, route).observe(time.perf_counter() - started)
        return response

    app.before_request(start)
    app.after_request(observe)
