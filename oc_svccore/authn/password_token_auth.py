import threading
import time

import requests

from oc_svccore.errors.types import UpstreamError, UpstreamUnavailableError


class PasswordTokenAuth(requests.auth.AuthBase):
    def __init__(
        self,
        issuer_url: str,
        client_id: str,
        client_secret: str | None,
        username: str,
        password: str,
        *,
        timeout: float = 10,
    ):
        self._url = f"{issuer_url}/protocol/openid-connect/token"
        self._form = {"grant_type": "password", "client_id": client_id, "username": username, "password": password}
        if client_secret:
            self._form["client_secret"] = client_secret
        self._timeout = timeout
        self._token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self.token()}"
        return r

    def token(self) -> str:
        with self._lock:
            if time.monotonic() >= self._expires_at:
                self._token, self._expires_at = self._fetch()
            return self._token

    def _fetch(self) -> tuple[str, float]:
        try:
            resp = requests.post(self._url, data=self._form, timeout=self._timeout)
            resp.raise_for_status()
            body = resp.json()
        except requests.HTTPError as e:
            if e.response.status_code < 500:
                raise UpstreamError("_err_msg_keycloak_rejected_credentials") from e
            raise UpstreamUnavailableError("_err_msg_keycloak_unavailable") from e
        except requests.RequestException as e:
            raise UpstreamUnavailableError("_err_msg_keycloak_unavailable") from e
        return body["access_token"], time.monotonic() + body["expires_in"] - 30
