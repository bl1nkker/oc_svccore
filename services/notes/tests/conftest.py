import os

import pytest

from oc_svccore import web
from oc_svccore.db import Database
from oc_svccore.testing import bearer
from notes.main import create_app
from notes.migrate import migrate


@pytest.fixture(scope="session")
def db_migrations():
    return migrate


@pytest.fixture
def app(issuer, db_session):
    database = Database(os.environ["TEST_DATABASE_URL"])
    database.sessionmaker = lambda: db_session
    return create_app(database, web.bearer(issuer.verifier()), writers=frozenset({"writer"}))


@pytest.fixture
def writer(issuer):
    return bearer(issuer.token("writer"))


@pytest.fixture
def reader(issuer):
    return bearer(issuer.token("reader"))
