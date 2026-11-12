from typing import Any, Generic, TypeVar

from sqlalchemy import desc
from sqlalchemy.orm import Query

from oc_svccore.db.base_repo import BaseRepo
from oc_svccore.db.invalid_sort_error import InvalidSortError
from oc_svccore.db.pagination import Pagination

T = TypeVar("T")


class DataRepo(BaseRepo, Generic[T]):
    _type: type[T]
    _order_by_map: dict[str, Any] = {}
    _default_order_by: str = "id"

    def query(self) -> Query[T]:
        return self._session.query(self._type)

    def save_or_update(self, entity: T) -> T:
        self._session.add(entity)
        self._session.flush()
        return entity

    def delete(self, entity: T) -> T:
        self._session.delete(entity)
        self._session.flush()
        return entity

    def get_by_db_id(self, db_id: Any, query: Query[T] | None = None) -> T | None:
        return self._q(query).filter(self._type.id == db_id).first()

    def single(self, query: Query[T] | None = None) -> T:
        return self._q(query).one()

    def first(self, query: Query[T] | None = None) -> T | None:
        return self._q(query).first()

    def list_all(self, query: Query[T] | None = None) -> list[T]:
        return self._q(query).all()

    def count(self, query: Query[T] | None = None) -> int:
        return self._q(query).count()

    def list_paged(self, page: int = 1, page_size: int = 10, query: Query[T] | None = None) -> Pagination[T]:
        query = self._q(query)
        total = query.order_by(None).count()
        items = query.limit(page_size).offset((page - 1) * page_size).all()
        return Pagination(page=page, page_size=page_size, total=total, items=items)

    def with_for_update(self, query: Query[T] | None = None) -> Query[T]:
        return self._q(query).with_for_update()

    def order_by(self, sort: str | None = None, query: Query[T] | None = None) -> Query[T]:
        if not sort:
            return self._q(query).order_by(getattr(self._type, self._default_order_by))
        column = self._order_by_map.get(sort.removeprefix("-"))
        if column is None:
            raise InvalidSortError(data={"sort": sort, "allowed": sorted(self._order_by_map)})
        return self._q(query).order_by(desc(column) if sort.startswith("-") else column)

    def _q(self, query: Query[T] | None) -> Query[T]:
        return self.query() if query is None else query
