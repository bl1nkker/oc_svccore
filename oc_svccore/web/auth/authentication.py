from collections.abc import Callable

from flask import Request, current_app, request

from oc_svccore.authn import Principal
from oc_svccore.web.auth.current_principal import set_principal
from oc_svccore.web.auth.public import is_public

Authenticate = Callable[[Request], Principal]


def authentication_hook(authenticate: Authenticate) -> Callable[[], None]:
    def hook() -> None:
        view = current_app.view_functions.get(request.endpoint) if request.endpoint else None
        if view is not None and not is_public(view):
            set_principal(authenticate(request))

    return hook
