from flask import g, has_request_context

from oc_svccore.authn.models import Principal
from oc_svccore.errors.types import UnauthorizedError


def set_principal(principal: Principal) -> None:
    g.oc_svccore_principal = principal


def current_principal() -> Principal:
    principal = principal_in_request()
    if principal is None:
        raise UnauthorizedError()
    return principal


def principal_in_request() -> Principal | None:
    return g.get("oc_svccore_principal") if has_request_context() else None
