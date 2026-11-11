import time
from typing import Any

from sqlalchemy import Connection, create_engine, event, text
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.orm import sessionmaker

from oc_svccore.metrics import observe_dependency

CONNECT_TIMEOUT_SEC = 5

_QUERY_STARTED = "oc_svccore_query_started"


class Database:
    def __init__(self, url: str, *, name: str = "postgres", **engine_kwargs: Any):
        self.name = name
        connect_args = {"connect_timeout": CONNECT_TIMEOUT_SEC, **engine_kwargs.pop("connect_args", {})}
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args, **engine_kwargs)
        self.sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)
        event.listen(self.engine, "before_cursor_execute", self._query_started)
        event.listen(self.engine, "after_cursor_execute", self._query_finished)
        event.listen(self.engine, "handle_error", self._query_failed)

    def ping(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))

    @staticmethod
    def _query_started(conn: Connection, *_: Any) -> None:
        conn.info.setdefault(_QUERY_STARTED, []).append(time.perf_counter())

    def _query_finished(self, conn: Connection, *_: Any) -> None:
        self._observe(conn, "success")

    def _query_failed(self, ctx: ExceptionContext) -> None:
        if ctx.connection is not None:
            self._observe(ctx.connection, "error")

    def _observe(self, conn: Connection, outcome: str) -> None:
        started = conn.info.get(_QUERY_STARTED)
        if started:
            observe_dependency(self.name, outcome, time.perf_counter() - started.pop())
