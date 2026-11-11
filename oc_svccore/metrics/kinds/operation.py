import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

from prometheus_client import Counter, Gauge, Histogram
from pydantic import ValidationError

from oc_svccore.errors.base_error import BaseError
from oc_svccore.errors.types import UpstreamError
from oc_svccore.metrics.registry import BUCKETS, get_or_create, service_prefix

F = TypeVar("F", bound=Callable[..., Any])

OUTCOMES = ("success", "failed", "rejected")

_operations: list["Operation"] = []


class Operation:
    def __init__(self, name: str):
        self.name = name
        self._total: Counter | None = None
        self._duration: Histogram | None = None
        self._last_success: Gauge | None = None
        _operations.append(self)
        if service_prefix():
            self.bind()

    def bind(self) -> None:
        self._total = get_or_create(Counter, self.name, f"Attempts of {self.name}", ("outcome",))
        for outcome in OUTCOMES:
            self._total.labels(outcome)
        self._duration = get_or_create(Histogram, f"{self.name}_duration_seconds", f"Duration of {self.name}",
                                       buckets=BUCKETS)
        self._last_success = get_or_create(Gauge, f"{self.name}_last_success_timestamp_seconds",
                                           f"Unix time of the last successful {self.name}")

    @contextmanager
    def track(self) -> Iterator[None]:
        if self._total is None:
            raise RuntimeError(f"metrics: operation {self.name} used before metrics.setup")
        started, outcome = time.perf_counter(), "failed"
        try:
            yield
            outcome = "success"
        except (BaseError, ValidationError) as e:
            outcome = "failed" if isinstance(e, UpstreamError) else "rejected"
            raise
        finally:
            self._total.labels(outcome).inc()
            self._duration.observe(time.perf_counter() - started)
            if outcome == "success":
                self._last_success.set_to_current_time()

    def __call__(self, fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with self.track():
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]


def operation(name: str) -> Operation:
    return Operation(name)


def bind_operations() -> None:
    for op in _operations:
        op.bind()
