from typing import Any

from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str
    claims: dict[str, Any] = {}


class OidcTokens(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str
    username: str
    name: str
    email: str
    id_token: str
    refresh_token: str
