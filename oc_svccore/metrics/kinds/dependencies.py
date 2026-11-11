import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import REGISTRY, Histogram
from prometheus_client.core import GaugeMetricFamily

from oc_svccore.metrics.checks import Check, run_checks
from oc_svccore.metrics.registry import BUCKETS, find, get_or_create, service_prefix

_DURATION = "dependency_request_duration_seconds"

_checks: dict[str, Check] = {}
_up_registered = False


def register_dependencies(checks: dict[str, Check]) -> None:
    global _checks, _up_registered
    _checks = checks
    get_or_create(Histogram, _DURATION, "Duration of outgoing calls", ("dependency", "outcome"), buckets=BUCKETS)
    if not _up_registered:
        REGISTRY.register(_DependencyUp())
        _up_registered = True


def observe_dependency(dependency: str, outcome: str, seconds: float) -> None:
    histogram = find(_DURATION)
    if histogram is not None:
        histogram.labels(dependency, outcome).observe(seconds)


@contextmanager
def dependency(name: str) -> Iterator[None]:
    started, outcome = time.perf_counter(), "error"
    try:
        yield
        outcome = "success"
    finally:
        observe_dependency(name, outcome, time.perf_counter() - started)


class _DependencyUp:
    def describe(self) -> list:
        return []

    def collect(self) -> Iterator[GaugeMetricFamily]:
        family = GaugeMetricFamily(f"{service_prefix()}_dependency_up", "Current state of each dependency",
                                   labels=["dependency"])
        for name, up in run_checks(_checks).items():
            family.add_metric([name], 1.0 if up else 0.0)
        yield family
