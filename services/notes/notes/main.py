from flask import Flask

from oc_svccore import config, logging, web
from oc_svccore.db import Database, get_db_config
from notes.api import build_blueprint
from notes.notes_config import get_notes_config

SERVICE = "notes"


def create_app(database: Database, authenticate: web.Authenticate, writers: frozenset[str]) -> Flask:
    app = web.create_app(
        __name__,
        service=SERVICE,
        authenticate=None,
        checks={"postgres": database.ping},
    )
    app.register_blueprint(build_blueprint(database, writers))
    return app


def main() -> Flask:
    config.setup(SERVICE)
    logging.setup(SERVICE)
    return create_app(
        Database(get_db_config().postgres_url()),
        web.bearer_auth(),
        get_notes_config().writers,
    )
