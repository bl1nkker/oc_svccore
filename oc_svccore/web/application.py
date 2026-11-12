from flask import Flask
from oc_logging.ecs import log_requests
from oc_logging.tracing import instrument_flask

from oc_svccore import metrics
from oc_svccore.errors import BaseError
from oc_svccore.metrics import Check
from oc_svccore.web.auth.authentication import Authenticate, authentication_hook
from oc_svccore.web.auth.session.session_auth import SessionAuth
from oc_svccore.web.error_handler import register_error_handlers
from oc_svccore.web.observability.health import health_blueprint
from oc_svccore.web.observability.http_metrics import instrument_requests
from oc_svccore.web.observability.log_user_name import log_user_name
from oc_svccore.web.observability.metrics_endpoint import add_metrics_endpoint
from oc_svccore.web.observability.trace_id import add_trace_id_header
from oc_svccore.web.request_session import close_request_sessions

PROBE_PATHS = ("/health", "/health/liveness", "/health/readiness", "/metrics")


def create_app(
    import_name: str,
    *,
    service: str,
    authenticate: Authenticate,
    checks: dict[str, Check] | None = None,
    errors_mapping: dict[type[BaseError], int] | None = None,
) -> Flask:
    app = Flask(import_name)
    # error handler
    register_error_handlers(app, errors_mapping)
    # health + readiness
    app.register_blueprint(health_blueprint(checks or {}))
    # metrics
    metrics.setup(service, checks)
    add_metrics_endpoint(app)
    # observability
    instrument_requests(app, PROBE_PATHS)
    log_requests(app, skip_paths=PROBE_PATHS)
    instrument_flask(app, excluded_paths=PROBE_PATHS)
    # authentication
    app.before_request(authentication_hook(authenticate))
    if isinstance(authenticate, SessionAuth):
        app.register_blueprint(authenticate.blueprint)
    app.after_request(add_trace_id_header)
    app.teardown_appcontext(close_request_sessions)
    log_user_name()
    return app
