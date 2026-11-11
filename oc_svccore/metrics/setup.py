from oc_svccore.metrics.checks import Check
from oc_svccore.metrics.kinds.build_info import register_build_info
from oc_svccore.metrics.kinds.dependencies import register_dependencies
from oc_svccore.metrics.kinds.operation import bind_operations
from oc_svccore.metrics.registry import set_service


def setup(service: str, checks: dict[str, Check] | None = None) -> None:
    set_service(service)
    register_build_info()
    register_dependencies(checks or {})
    bind_operations()
