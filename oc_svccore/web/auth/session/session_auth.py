import hmac
import html
import logging
import secrets
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlsplit

from flask import Blueprint, Request, Response, g, redirect, request

from oc_svccore.authn import (
    OidcClient,
    OidcTokens,
    Principal,
    RefreshRejectedError,
    get_auth_config,
    get_oidc_client_config,
)
from oc_svccore.errors import UnauthorizedError, UpstreamError
from oc_svccore.web.auth.current_principal import current_principal
from oc_svccore.web.auth.public import public
from oc_svccore.web.auth.session.session_config import SessionConfig, get_session_config
from oc_svccore.web.auth.session.session_cookies import SessionCookies

TXN_MAX_AGE_SEC = 30 * 60

_PENDING_COOKIES = "oc_svccore_session_cookies"

log = logging.getLogger(__name__)


class SessionAuth:
    def __init__(self, client: OidcClient, config: SessionConfig, *, clock: Callable[[], float] = time.time):
        self._client = client
        self._config = config
        self._cookies = SessionCookies(config)
        self._clock = clock
        self._ttl = int(config.ttl.total_seconds())
        self._login_url = self._public_login_url(config.redirect_url)
        self.blueprint = self._blueprint()

    def __call__(self, req: Request) -> Principal:
        session = self._session(req)
        if session is None:
            raise UnauthorizedError("_err_msg_no_session")
        claims = {"sub": session["sub"], "name": session["name"], "email": session["email"]}
        return Principal(username=session["username"], claims=claims)

    def _session(self, req: Request) -> dict[str, Any] | None:
        session = self._cookies.read(req)
        now = self._clock()
        if session is None or now >= session["expires_at"]:
            return None
        if now - session["refreshed_at"] < self._config.refresh_interval.total_seconds():
            return session
        refresh_token = self._cookies.read(req, "_rt")
        if not refresh_token:
            self._clear_session()
            return None
        try:
            tokens = self._client.refresh(refresh_token)
        except RefreshRejectedError:
            log.info("session: ended in Keycloak")
            self._clear_session()
            return None
        except UpstreamError as e:
            reason = str(e.__cause__ or e.message)
            log.warning("session: refresh failed, keeping the current session", extra={"reason": reason})
            return session
        return self._start(tokens)

    def _start(self, tokens: OidcTokens) -> dict[str, Any]:
        now = self._clock()
        session = {"sub": tokens.subject, "username": tokens.username, "name": tokens.name, "email": tokens.email,
                   "expires_at": now + self._ttl, "refreshed_at": now}
        self._later(lambda r: self._cookies.write(r, "_rt", tokens.refresh_token, self._ttl))
        self._later(lambda r: self._cookies.write(r, "", session, self._ttl))
        if tokens.id_token:
            self._later(lambda r: self._cookies.write(r, "_idt", tokens.id_token, self._ttl))
        return session

    def _clear_session(self) -> None:
        for suffix in ("", "_rt", "_idt"):
            self._later(lambda r, s=suffix: self._cookies.clear(r, s))

    # The session is read before the view runs, when there is no response yet, so cookie changes wait in g.
    @staticmethod
    def _later(change: Callable[[Response], None]) -> None:
        g.setdefault(_PENDING_COOKIES, []).append(change)

    @staticmethod
    def _apply_cookies(response: Response) -> Response:
        for change in g.pop(_PENDING_COOKIES, []):
            change(response)
        return response

    def _blueprint(self) -> Blueprint:
        bp = Blueprint("oc_svccore_session", __name__, url_prefix="/auth")
        bp.after_app_request(self._apply_cookies)

        @bp.get("/login")
        @public
        def login():
            state, code_verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            return_to, origin = self._return_params()
            txn = {"state": state, "code_verifier": code_verifier, "return_to": return_to, "origin": origin}
            self._later(lambda r: self._cookies.write(r, "_txn", txn, TXN_MAX_AGE_SEC))
            return redirect(self._client.auth_code_url(state, code_verifier))

        @bp.get("/callback")
        @public
        def callback():
            txn = self._cookies.read(request, "_txn", max_age=TXN_MAX_AGE_SEC)
            if txn is None:
                return self._error_page(400, "Your sign-in request expired or was not recognised.")
            self._later(lambda r: self._cookies.clear(r, "_txn"))
            state = request.args.get("state", "")
            if not state or not hmac.compare_digest(state.encode(), txn["state"].encode()):
                return self._error_page(400, "Sign-in could not be verified.")
            code = request.args.get("code", "")
            if not code:
                return self._error_page(400, "Sign-in did not return an authorization code.")
            try:
                tokens = self._client.exchange(code, txn["code_verifier"])
            except UpstreamError as e:
                log.warning("session: code exchange failed", extra={"reason": str(e.__cause__ or e.message)})
                return self._error_page(400, "Sign-in could not be completed.")
            self._start(tokens)
            return redirect(self._return_target(txn["return_to"], txn["origin"]))

        @bp.get("/logout")
        @public
        def logout():
            id_token = self._cookies.read(request, "_idt") or ""
            self._clear_session()
            return_to, origin = self._return_params()
            post_logout = self._return_target(return_to, origin) if origin else self._config.post_logout_redirect_url
            return redirect(self._client.end_session_url(id_token, post_logout))

        @bp.get("/me")
        def me():
            principal = current_principal()
            return {"authenticated": True, "sub": principal.claims["sub"], "username": principal.username,
                    "name": principal.claims["name"] or principal.username, "email": principal.claims["email"]}

        return bp

    def _return_params(self) -> tuple[str, str]:
        return_to, origin = request.args.get("returnTo", ""), request.args.get("origin", "")
        return (return_to if self._is_safe_path(return_to) else "",
                origin if origin in self._config.return_origins else "")

    def _return_target(self, path: str, origin: str) -> str:
        return origin + (path or self._config.post_login_redirect_path)

    def _error_page(self, status: int, message: str) -> Response:
        retry = self._login_url
        if self._config.return_origins:
            retry += "?origin=" + quote(self._config.return_origins[0], safe="")
        body = ('<!doctype html><meta charset="utf-8"><title>Sign-in failed</title>'
                f'<body style="font:14px system-ui;padding:2rem"><p>{html.escape(message)}</p>'
                f'<p><a href="{html.escape(retry)}">Sign in again</a></p>')
        return Response(body, status=status, content_type="text/html; charset=utf-8")

    @staticmethod
    def _is_safe_path(path: str) -> bool:
        if not path.startswith("/") or path.startswith("//"):
            return False
        if any(ord(c) < 0x20 or ord(c) == 0x7F or c == "\\" for c in path):
            return False
        url = urlsplit(path)
        return not url.scheme and not url.netloc

    @staticmethod
    def _public_login_url(redirect_url: str) -> str:
        url = urlsplit(redirect_url)
        if not url.scheme or not url.netloc:
            return "/auth/login"
        return f"{url.scheme}://{url.netloc}{url.path.rsplit('/', 1)[0]}/login"


def session_auth() -> SessionAuth:
    oidc, config = get_oidc_client_config(), get_session_config()
    client = OidcClient(get_auth_config().issuer_url, oidc.client_id, oidc.client_secret, config.redirect_url)
    return SessionAuth(client, config)
