from datetime import datetime

from pydantic import Field

from oc_svccore.dto import ApiModel


class Create(ApiModel):
    title: str = Field(min_length=1, max_length=200)


class Read(ApiModel):
    id: int
    title: str
    author: str
    created_at: datetime
