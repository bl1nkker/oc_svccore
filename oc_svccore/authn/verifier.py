import logging
from typing import Any

import jwt

from oc_svccore.authn.models import Principal
from oc_svccore.errors.types import UnauthorizedError, UpstreamUnavailableError

JWKS_TIMEOUT_SEC = 5

log = logging.getLogger(__name__)


class Verifier:
    def __init__(
        self,
        issuer_url: str,
        *,
        jwks_client: jwt.PyJWKClient | None = None,
        key: Any = None,
        audience: str | None = None,
    ):
        if (jwks_client is None) == (key is None):
            raise ValueError("pass exactly one of jwks_client or key")
        self._issuer = issuer_url
        self._jwks = jwks_client
        self._key = key
        self._audience = audience

    def verify(self, token: str) -> dict[str, Any]:
        key = self._key if self._key is not None else self._jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=self._issuer,
            audience=self._audience,
            options={"verify_aud": self._audience is not None, "require": ["exp", "iss"]},
        )

    def principal(self, token: str) -> Principal:
        try:
            claims = self.verify(token)
        except jwt.PyJWKClientConnectionError as e:
            raise UpstreamUnavailableError("_err_msg_keycloak_unavailable") from e
        except jwt.PyJWTError as e:
            log.warning("authn: rejected token", extra={"reason": str(e)})
            raise UnauthorizedError("_err_msg_invalid_token") from e
        return Principal(username=claims.get("preferred_username") or claims.get("sub", ""), claims=claims)


def keycloak_verifier(issuer_url: str, *, audience: str | None = None) -> Verifier:
    jwks = jwt.PyJWKClient(f"{issuer_url}/protocol/openid-connect/certs", timeout=JWKS_TIMEOUT_SEC)
    return Verifier(issuer_url, jwks_client=jwks, audience=audience)
