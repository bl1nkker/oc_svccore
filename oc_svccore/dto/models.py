from typing import Any, Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

from oc_svccore.dto.validation_failed_error import ValidationFailedError

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        from_attributes=True,
    )

    @classmethod
    def parse(cls, data: Any) -> Self:
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ValidationFailedError.from_pydantic(e) from None


class ListQuery(ApiModel):
    page: int = Field(1, ge=1, le=1_000_000)
    page_size: int = Field(50, ge=1, le=500)
    sort: str | None = None
    search: str | None = None


class Page(ApiModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
