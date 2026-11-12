from flask import Request

from oc_svccore.authn import Principal, Verifier, get_auth_config, keycloak_verifier
from oc_svccore.errors import UnauthorizedError
from oc_svccore.web.auth.authentication import Authenticate


def bearer(verifier: Verifier) -> Authenticate:
    def authenticate(request: Request) -> Principal:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise UnauthorizedError("_err_msg_missing_token")
        return verifier.principal(token)

    return authenticate


def bearer_auth() -> Authenticate:
    return bearer(keycloak_verifier(get_auth_config().issuer_url))
