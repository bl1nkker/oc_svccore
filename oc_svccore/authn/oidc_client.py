import base64
import hashlib
from typing import Any
from urllib.parse import urlencode

import jwt
import requests

from oc_svccore.authn.models import OidcTokens
from oc_svccore.authn.refresh_rejected_error import RefreshRejectedError
from oc_svccore.authn.verifier import Verifier, keycloak_verifier
from oc_svccore.errors import UpstreamError, UpstreamUnavailableError

SCOPES = "openid profile email"


def code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class OidcClient:
    def __init__(
        self,
        issuer_url: str,
        client_id: str,
        client_secret: str | None,
        redirect_url: str,
        *,
        verifier: Verifier | None = None,
        timeout: float = 5,
    ):
        self._endpoint = f"{issuer_url}/protocol/openid-connect"
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_url = redirect_url
        self._verifier = verifier or keycloak_verifier(issuer_url, audience=client_id)
        self._timeout = timeout

    def auth_code_url(self, state: str, code_verifier: str) -> str:
        query = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_url,
            "scope": SCOPES,
            "state": state,
            "code_challenge": code_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
        return f"{self._endpoint}/auth?{urlencode(query)}"

    def exchange(self, code: str, code_verifier: str) -> OidcTokens:
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": self._redirect_url,
                "code_verifier": code_verifier}
        return self._tokens(form)

    def refresh(self, refresh_token: str) -> OidcTokens:
        return self._tokens({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def end_session_url(self, id_token_hint: str, post_logout_redirect_url: str) -> str:
        query = {"client_id": self._client_id}
        if id_token_hint:
            query["id_token_hint"] = id_token_hint
        if post_logout_redirect_url:
            query["post_logout_redirect_uri"] = post_logout_redirect_url
        return f"{self._endpoint}/logout?{urlencode(query)}"

    def _tokens(self, form: dict[str, str]) -> OidcTokens:
        form = {**form, "client_id": self._client_id}
        if self._client_secret:
            form["client_secret"] = self._client_secret
        try:
            resp = requests.post(f"{self._endpoint}/token", data=form, timeout=self._timeout)
        except requests.RequestException as e:
            raise UpstreamUnavailableError("_err_msg_keycloak_unavailable") from e
        if resp.status_code >= 500:
            raise UpstreamUnavailableError("_err_msg_keycloak_unavailable")
        body = _json(resp)
        if form["grant_type"] == "refresh_token" and body.get("error") == "invalid_grant":
            raise RefreshRejectedError()
        if not resp.ok or "id_token" not in body:
            raise UpstreamError("_err_msg_keycloak_rejected_request")
        claims = self._verify(body["id_token"])
        return OidcTokens(
            subject=claims["sub"],
            username=claims.get("preferred_username", ""),
            name=claims.get("name", ""),
            email=claims.get("email", ""),
            id_token=body["id_token"],
            refresh_token=body.get("refresh_token", ""),
        )

    def _verify(self, id_token: str) -> dict[str, Any]:
        try:
            return self._verifier.verify(id_token)
        except jwt.PyJWKClientConnectionError as e:
            raise UpstreamUnavailableError("_err_msg_keycloak_unavailable") from e
        except jwt.PyJWTError as e:
            raise UpstreamError("_err_msg_keycloak_bad_id_token") from e


def _json(resp: requests.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
