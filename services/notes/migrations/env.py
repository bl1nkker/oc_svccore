from alembic import context

from oc_svccore import config
from oc_svccore.db import Database, get_db_config
from notes.main import SERVICE
from notes.models import Base


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if connection := context.config.attributes.get("connection"):
    run(connection)
else:
    config.setup(SERVICE)
    with Database(get_db_config().postgres_url()).engine.connect() as conn:
        run(conn)
