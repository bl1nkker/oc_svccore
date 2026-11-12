import os
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def db_migrations() -> Callable[[Engine], None]:
    return lambda engine: None


@pytest.fixture(scope="session")
def db_engine(db_migrations: Callable[[Engine], None]) -> Iterator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is not set: db tests need a real database")
    engine = create_engine(url)
    db_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
