import argparse
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from oc_svccore.authn.oidc_client import code_challenge
from oc_svccore.testing.issuer import Issuer

TOKEN_TTL = 3600


class _Handler(BaseHTTPRequestHandler):
    server: "DevIssuerServer"

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        if url.path == f"{self.server.base}/certs":
            self._send(200, self.server.issuer.jwks())
        elif url.path == f"{self.server.base}/auth":
            self._authorize(query)
        elif url.path == f"{self.server.base}/logout" and "post_logout_redirect_uri" in query:
            self._redirect(query["post_logout_redirect_uri"])
        elif url.path == f"{self.server.base}/logout":
            self._send(200, {})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != f"{self.server.base}/token":
            self._send(404, {"error": "not_found"})
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        form = {key: values[0] for key, values in parse_qs(body).items()}
        grant = form.get("grant_type", "password")
        if grant == "authorization_code":
            entry = self.server.codes.pop(form.get("code", ""), None)
            if entry is None or code_challenge(form.get("code_verifier", "")) != entry[2]:
                self._send(400, {"error": "invalid_grant"})
                return
            self._send(200, self._oidc_tokens(entry[0], entry[1]))
        elif grant == "refresh_token":
            entry = self.server.refresh_tokens.pop(form.get("refresh_token", ""), None)
            if entry is None:
                self._send(400, {"error": "invalid_grant"})
                return
            self._send(200, self._oidc_tokens(*entry))
        else:
            username = form.get("username", self.server.user)
            self._send(200, {
                "access_token": self.server.issuer.token(username, expires_in=TOKEN_TTL),
                "expires_in": TOKEN_TTL,
                "token_type": "Bearer",
            })

    # Signs in as the server's user at once, where Keycloak would show its login form.
    def _authorize(self, query: dict[str, str]) -> None:
        code = secrets.token_urlsafe(16)
        self.server.codes[code] = (self.server.user, query["client_id"], query["code_challenge"])
        self._redirect(f"{query['redirect_uri']}?{urlencode({'code': code, 'state': query['state']})}")

    def _oidc_tokens(self, username: str, client_id: str) -> dict[str, Any]:
        refresh_token = secrets.token_urlsafe(32)
        self.server.refresh_tokens[refresh_token] = (username, client_id)
        now = int(time.time())
        id_token = self.server.issuer.sign({
            "iss": self.server.issuer.url, "sub": username, "aud": client_id, "preferred_username": username,
            "name": username, "email": f"{username}@dev.local", "iat": now, "exp": now + TOKEN_TTL,
        })
        return {
            "access_token": self.server.issuer.token(username, expires_in=TOKEN_TTL),
            "id_token": id_token,
            "refresh_token": refresh_token,
            "expires_in": TOKEN_TTL,
            "token_type": "Bearer",
        }

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


class DevIssuerServer(ThreadingHTTPServer):
    def __init__(self, port: int = 0, realm: str = "dev", user: str = "dev-user") -> None:
        super().__init__(("localhost", port), _Handler)
        self.issuer = Issuer(f"http://localhost:{self.server_port}/realms/{realm}")
        self.base = f"/realms/{realm}/protocol/openid-connect"
        self.user = user
        self.codes: dict[str, tuple[str, str, str]] = {}
        self.refresh_tokens: dict[str, tuple[str, str]] = {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fake Keycloak for local development: JWKS, password grant, and the login flow of a BFF")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--realm", default="dev")
    parser.add_argument("--user", default="dev-user", help="who the password grant and the browser login sign in as")
    args = parser.parse_args()
    server = DevIssuerServer(args.port, args.realm, args.user)
    print(f"OIDC_ISSUER_URL={server.issuer.url}")
    print(f"token for {args.user}: {server.issuer.token(args.user, expires_in=86400)}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
