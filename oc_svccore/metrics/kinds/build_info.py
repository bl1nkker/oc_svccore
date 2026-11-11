from prometheus_client import Gauge

from oc_svccore.metrics.build_config import get_build_config
from oc_svccore.metrics.registry import get_or_create


def register_build_info() -> None:
    build = get_build_config()
    gauge = get_or_create(Gauge, "build_info", "Version of the running build", ("version", "git_sha"))
    gauge.labels(build.version, build.git_sha).set(1)
