import base64
import binascii
import re
from datetime import timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, BeforeValidator, field_validator, model_validator

from oc_svccore.config import getter

_GO_DURATION = re.compile(r"(\d+)(h|m|s)")
_UNITS = {"h": "hours", "m": "minutes", "s": "seconds"}


# The Go bff takes durations as "8h" or "5m" (time.ParseDuration), so one deployment config fits both.
def _go_duration(value: Any) -> Any:
    if isinstance(value, str) and value and not _GO_DURATION.sub("", value):
        return sum((timedelta(**{_UNITS[unit]: int(n)}) for n, unit in _GO_DURATION.findall(value)), timedelta())
    return value


Duration = Annotated[timedelta, BeforeValidator(_go_duration)]


class SessionConfig(BaseModel):
    redirect_url: str
    hash_key: str
    block_key: str
    return_origins: list[str] = []
    post_login_redirect_path: str = "/"
    post_logout_redirect_url: str = ""
    cookie_name: str = "session"
    cookie_secure: bool = True
    ttl: Duration = timedelta(hours=8)
    refresh_interval: Duration = timedelta(minutes=5)

    @field_validator("hash_key", "block_key")
    @classmethod
    def _sixteen_bytes_of_base64(cls, value: str) -> str:
        try:
            key = base64.b64decode(value, validate=True)
        except binascii.Error:
            raise ValueError("must be base64") from None
        if len(key) < 16:
            raise ValueError("must be at least 16 bytes")
        return value

    @model_validator(mode="after")
    def _post_logout_defaults_to_the_app(self) -> "SessionConfig":
        if not self.post_logout_redirect_url:
            url = urlsplit(self.redirect_url)
            self.post_logout_redirect_url = f"{url.scheme}://{url.netloc}{self.post_login_redirect_path}"
        return self


get_session_config = getter(SessionConfig, lambda get: dict(
    redirect_url=get("OIDC_REDIRECT_URL"),
    post_logout_redirect_url=get("OIDC_POST_LOGOUT_REDIRECT_URL"),
    return_origins=[origin.strip() for origin in (get("OIDC_RETURN_ORIGINS") or "").split(",") if origin.strip()],
    post_login_redirect_path=get("POST_LOGIN_REDIRECT_PATH"),
    hash_key=get("SESSION__HASH_KEY"),
    block_key=get("SESSION__BLOCK_KEY"),
    cookie_name=get("SESSION_COOKIE_NAME"),
    cookie_secure=get("SESSION_COOKIE_SECURE"),
    ttl=get("SESSION_TTL"),
    refresh_interval=get("SESSION_REFRESH_INTERVAL"),
))
