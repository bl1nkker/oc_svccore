import re
from typing import Any

import prometheus_client

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

_metrics: dict[str, Any] = {}
_service = ""

prometheus_client.disable_created_metrics()


def set_service(service: str) -> None:
    global _service
    _service = re.sub(r"\W", "_", service)


def service_prefix() -> str:
    return _service


def get_or_create(cls: type, name: str, doc: str, labels: tuple[str, ...] = (), **kwargs: Any) -> Any:
    full = f"{_service}_{name}"
    if full not in _metrics:
        _metrics[full] = cls(full, doc, labels, **kwargs)
    return _metrics[full]


def find(name: str) -> Any | None:
    return _metrics.get(f"{_service}_{name}")
