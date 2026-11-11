import os

from oc_logging.ecs import setup_ecs_logging
from oc_logging.tracing import setup_tracing

from oc_svccore.logging.log_config import get_log_config

_tracing_ready = False


def setup(service: str) -> None:
    global _tracing_ready
    os.environ.setdefault("OTEL_SERVICE_NAME", service)
    setup_ecs_logging(service_name=service, level=get_log_config().level)
    if not _tracing_ready:
        setup_tracing()
        _tracing_ready = True
