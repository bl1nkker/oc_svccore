from flask import Flask

from oc_svccore import config, logging, web
from notes_bff.api import build_blueprint
from notes_bff.notes_client import NotesClient, notes_client

SERVICE = "notes_bff"


def create_app(authenticate: web.Authenticate, notes: NotesClient) -> Flask:
    app = web.create_app(__name__, service=SERVICE, authenticate=authenticate, checks={"notes": notes.ping})
    app.register_blueprint(build_blueprint(notes))
    return app


def main() -> Flask:
    config.setup(SERVICE)
    logging.setup(SERVICE)
    return create_app(web.session_auth(), notes_client())
