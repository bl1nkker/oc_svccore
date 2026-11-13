from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from notes.migrate import alembic_config
from notes.models import Base


def test_database_is_at_the_latest_migration(db_engine):
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with db_engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head


def test_models_match_the_migrations(db_engine):
    with db_engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
