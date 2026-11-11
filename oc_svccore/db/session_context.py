from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

_DEPTH = "oc_svccore_scope_depth"


@contextmanager
def session_context(session: Session) -> Iterator[Session]:
    depth = session.info.get(_DEPTH, 0)
    session.info[_DEPTH] = depth + 1
    try:
        if depth:
            with session.begin_nested():
                yield session
            return
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
    finally:
        session.info[_DEPTH] = depth
