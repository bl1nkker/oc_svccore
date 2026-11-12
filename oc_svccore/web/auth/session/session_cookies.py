import base64
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from flask import Request, Response

from oc_svccore.web.auth.session.session_config import SessionConfig

MAX_COOKIE_BYTES = 4000

log = logging.getLogger(__name__)


class SessionCookies:
    def __init__(self, config: SessionConfig):
        signing = base64.b64decode(config.hash_key)[:16]
        encryption = base64.b64decode(config.block_key)[:16]
        self._fernet = Fernet(base64.urlsafe_b64encode(signing + encryption))
        self._name = config.cookie_name
        self._secure = config.cookie_secure

    def read(self, request: Request, suffix: str = "", *, max_age: int | None = None) -> Any:
        raw = request.cookies.get(self._name + suffix)
        if not raw:
            return None
        try:
            return json.loads(self._fernet.decrypt(raw, ttl=max_age))
        except (InvalidToken, ValueError):
            return None

    def write(self, response: Response, suffix: str, value: Any, max_age: int) -> None:
        name = self._name + suffix
        encoded = self._fernet.encrypt(json.dumps(value).encode()).decode()
        # Browsers drop a cookie over 4 KB without a word, so it is skipped and logged here instead.
        if len(encoded) > MAX_COOKIE_BYTES:
            log.warning("session: cookie too large, not set", extra={"cookie": name, "size": len(encoded)})
            return
        response.set_cookie(
            name, encoded, max_age=max_age, path="/", httponly=True, secure=self._secure, samesite="Lax"
        )

    def clear(self, response: Response, suffix: str = "") -> None:
        response.delete_cookie(self._name + suffix, path="/", httponly=True, secure=self._secure, samesite="Lax")
