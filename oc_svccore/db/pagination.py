from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Pagination(BaseModel, Generic[T]):
    # Items are usually ORM objects, which pydantic only checks by isinstance.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    page: int
    page_size: int
    total: int
    items: list[T]
