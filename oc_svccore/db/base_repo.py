from sqlalchemy.orm import Session

from oc_svccore.db.session_context import session_context


class BaseRepo:
    def __init__(self, session: Session):
        self._session = session

    def session(self):
        return session_context(self._session)
