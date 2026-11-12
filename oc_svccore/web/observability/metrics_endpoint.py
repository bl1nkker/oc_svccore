from flask import Flask, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from oc_svccore.web.auth.public import public


def add_metrics_endpoint(app: Flask) -> None:
    app.add_url_rule("/metrics", "oc_svccore_metrics", _metrics_view)


@public
def _metrics_view() -> Response:
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)
