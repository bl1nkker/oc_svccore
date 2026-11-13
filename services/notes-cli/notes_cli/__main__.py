import json

import click
import requests

from oc_svccore import authn, cli
from oc_svccore.errors import UpstreamError, UpstreamUnavailableError
from notes_cli.cli_config import get_notes_cli_config

app = cli.create_app("notes-cli")


def service_account() -> tuple[str, authn.PasswordTokenAuth]:
    account, oidc = get_notes_cli_config(), authn.get_oidc_client_config()
    issuer_url = authn.get_auth_config().issuer_url
    return issuer_url, authn.PasswordTokenAuth(issuer_url, oidc.client_id, oidc.client_secret, account.username,
                                               account.password)


@app.command(help="Sign in with the service account and show who the token says it is.")
def whoami() -> None:
    issuer_url, auth = service_account()
    click.echo(authn.keycloak_verifier(issuer_url).principal(auth.token()).username)


@app.command(name="list", help="List notes.")
def list_notes() -> None:
    _, auth = service_account()
    try:
        resp = requests.get(f"{get_notes_cli_config().notes_url}/api/v1/notes", auth=auth, timeout=10)
    except requests.RequestException as e:
        raise UpstreamUnavailableError("_err_msg_notes_unavailable") from e
    if not resp.ok:
        raise UpstreamError("_err_msg_notes_rejected", data={"status": resp.status_code})
    click.echo(json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    app()
