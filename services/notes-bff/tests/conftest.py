import base64
import os
import threading
from urllib.parse import urlsplit

import pytest
import requests
from flask import request
from werkzeug.serving import make_server

from oc_svccore import authn, errors, web
from oc_svccore.testing import Issuer
from oc_svccore.testing.dev_issuer import DevIssuerServer
from notes_bff.bff_config import get_notes_bff_config
from notes_bff.main import create_app
from notes_bff.notes_client import notes_client

CONFIGS = (authn.get_auth_config, authn.get_oidc_client_config, web.get_session_config, get_notes_bff_config)


@pytest.fixture
def keycloak():
    srv = DevIssuerServer(user="someone")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


class NotesStub:
    def __init__(self, verifier):
        self.calls = []
        app = web.create_app(__name__, service="notes_stub", authenticate=web.bearer(verifier))

        @app.get("/api/v1/notes")
        def list_notes():
            self.calls.append(request.args.to_dict())
            if request.args.get("sort") == "author":
                raise errors.InvalidDataError("_err_msg_invalid_sort", code="invalid_sort",
                                              data={"sort": "author", "allowed": ["createdAt", "id", "title"]})
            return {"items": [], "page": 1, "pageSize": 50, "total": 0, "seenBy": web.current_principal().username}

        self.server = make_server("127.0.0.1", 0, app)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def notes(keycloak):
    stub = NotesStub(authn.keycloak_verifier(keycloak.issuer.url))
    yield stub
    stub.server.shutdown()


@pytest.fixture
def foreign_notes():
    stub = NotesStub(Issuer().verifier())
    yield stub
    stub.server.shutdown()


@pytest.fixture
def make_bff(monkeypatch, keycloak):
    def make(notes_url):
        key = base64.b64encode(os.urandom(32)).decode()
        values = {
            "OIDC_ISSUER_URL": keycloak.issuer.url, "OIDC_CLIENT_ID": "portal", "OIDC_CLIENT_SECRET": "secret",
            "OIDC_REDIRECT_URL": "http://bff.test/auth/callback", "SESSION_HASH_KEY": key, "SESSION_BLOCK_KEY": key,
            "SESSION_COOKIE_SECURE": "false", "NOTES_URL": notes_url,
            "NOTES_BFF_ACCOUNT_USERNAME": "svc-notes-bff", "NOTES_BFF_ACCOUNT_PASSWORD": "pw",
        }
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        for get in CONFIGS:
            get.cache_clear()
        app = create_app(web.session_auth(), notes_client())
        app.testing = True
        return app

    for name in ("VAULT_URL", "SPRING_CLOUD_CONFIG_URI"):
        monkeypatch.delenv(name, raising=False)
    yield make
    for get in CONFIGS:
        get.cache_clear()


@pytest.fixture
def bff(make_bff, notes):
    return make_bff(notes.url)


@pytest.fixture
def signed_in():
    def sign_in(app):
        client = app.test_client()
        r = client.get("/auth/login")
        assert r.status_code == 302, r.data
        callback = urlsplit(requests.get(r.location, allow_redirects=False, timeout=5).headers["Location"])
        assert client.get(f"{callback.path}?{callback.query}").status_code == 302
        return client

    return sign_in


@pytest.fixture
def user(bff, signed_in):
    return signed_in(bff)
