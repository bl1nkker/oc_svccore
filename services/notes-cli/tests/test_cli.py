import threading

import pytest
from click.testing import CliRunner
from werkzeug.serving import make_server

from oc_svccore import authn, web
from oc_svccore.testing import Issuer
from oc_svccore.testing.dev_issuer import DevIssuerServer
from notes_cli.__main__ import app
from notes_cli.cli_config import get_notes_cli_config


@pytest.fixture
def keycloak():
    srv = DevIssuerServer()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def serve(verifier):
    app = web.create_app(__name__, service="notes_stub", authenticate=web.bearer(verifier))

    @app.get("/api/v1/notes")
    def list_notes():
        return {"items": [], "seenBy": web.current_principal().username}

    server = make_server("127.0.0.1", 0, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def env(monkeypatch, tmp_path, keycloak):
    monkeypatch.chdir(tmp_path)
    for key in ("SPRING_CLOUD_CONFIG_URI", "VAULT_URL"):
        monkeypatch.delenv(key, raising=False)
    notes = serve(authn.keycloak_verifier(keycloak.issuer.url))
    values = {"OIDC_ISSUER_URL": keycloak.issuer.url, "OIDC_CLIENT_ID": "f1-api-gateway",
              "OIDC_CLIENT_SECRET": "secret", "NOTES_CLI_ACCOUNT_USERNAME": "svc-notes-cli",
              "NOTES_CLI_ACCOUNT_PASSWORD": "pw", "NOTES_URL": f"http://127.0.0.1:{notes.server_port}"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for get in (authn.get_auth_config, authn.get_oidc_client_config, get_notes_cli_config):
        get.cache_clear()
    yield monkeypatch
    notes.shutdown()
    for get in (authn.get_auth_config, authn.get_oidc_client_config, get_notes_cli_config):
        get.cache_clear()


def run(*args):
    return CliRunner().invoke(app, list(args))


def test_whoami_shows_the_service_account(env):
    r = run("whoami")
    assert (r.exit_code, r.stdout) == (0, "svc-notes-cli\n"), r.stderr


def test_list_calls_notes_as_the_service_account(env):
    r = run("list")
    assert r.exit_code == 0 and '"seenBy": "svc-notes-cli"' in r.stdout, r.stderr


def test_keycloak_down_is_a_short_error(env):
    env.setenv("OIDC_ISSUER_URL", "http://127.0.0.1:1/realms/x")
    authn.get_auth_config.cache_clear()
    r = run("whoami")
    assert (r.exit_code, r.stderr) == (1, "error: _err_msg_keycloak_unavailable\n"), r.stderr


def test_notes_rejecting_the_token_is_a_short_error(env):
    foreign = serve(Issuer().verifier())
    env.setenv("NOTES_URL", f"http://127.0.0.1:{foreign.server_port}")
    get_notes_cli_config.cache_clear()
    r = run("list")
    assert r.exit_code == 1 and r.stderr.splitlines()[-1] == 'error: _err_msg_notes_rejected {"status": 401}', r.stderr
    foreign.shutdown()
