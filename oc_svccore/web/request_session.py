from __future__ import annotations

from typing import TYPE_CHECKING

from flask import g

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from oc_svccore.db import Database

_SESSIONS = "oc_svccore_db_sessions"


def request_session(database: Database) -> Session:
    sessions = g.setdefault(_SESSIONS, {})
    if database not in sessions:
        sessions[database] = database.sessionmaker()
    return sessions[database]


def close_request_sessions(_exc: BaseException | None) -> None:
    for session in g.pop(_SESSIONS, {}).values():
        session.close()
