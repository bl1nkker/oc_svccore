from typing import Any

import requests

from oc_svccore import authn, metrics
from oc_svccore.errors import InvalidDataError, UpstreamError, UpstreamUnavailableError
from notes_bff.bff_config import get_notes_bff_config

TIMEOUT_SEC = 10
CHECK_TIMEOUT_SEC = 2


class NotesClient:
    def __init__(self, url: str, auth: requests.auth.AuthBase):
        self._url = url.rstrip("/")
        self._auth = auth

    def list_notes(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            with metrics.dependency("notes"):
                resp = requests.get(f"{self._url}/api/v1/notes", params=params, auth=self._auth, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            raise UpstreamUnavailableError("_err_msg_notes_unavailable") from e
        if resp.status_code == 400:
            body = resp.json()
            raise InvalidDataError(body.get("message"), code=body.get("code"), data=body.get("data"))
        if not resp.ok:
            raise UpstreamError("_err_msg_notes_rejected", data={"status": resp.status_code})
        return resp.json()

    def ping(self) -> None:
        requests.get(f"{self._url}/health/liveness", timeout=CHECK_TIMEOUT_SEC).raise_for_status()


def notes_client() -> NotesClient:
    config, oidc = get_notes_bff_config(), authn.get_oidc_client_config()
    auth = authn.PasswordTokenAuth(authn.get_auth_config().issuer_url, oidc.client_id, oidc.client_secret,
                                   config.username, config.password)
    return NotesClient(config.notes_url, auth)
