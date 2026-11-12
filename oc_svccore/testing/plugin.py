from importlib.util import find_spec

import pytest
from flask import Flask
from flask.testing import FlaskClient

from oc_svccore.testing.issuer import Issuer

if find_spec("sqlalchemy"):
    from oc_svccore.testing.db import db_engine, db_migrations, db_session  # noqa: F401


@pytest.fixture(scope="session")
def issuer() -> Issuer:
    return Issuer()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    app.testing = True
    return app.test_client()
