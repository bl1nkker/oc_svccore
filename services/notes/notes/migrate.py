from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from oc_svccore import config, logging
from oc_svccore.db import Database, get_db_config
from notes.main import SERVICE

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def migrate(engine: Engine) -> None:
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


if __name__ == "__main__":
    config.setup(SERVICE)
    logging.setup(SERVICE)
    migrate(Database(get_db_config().postgres_url()).engine)
