from pydantic import BaseModel

from oc_svccore.config import getter


class AuthConfig(BaseModel):
    issuer_url: str


get_auth_config = getter(AuthConfig, lambda get: dict(issuer_url=get("OIDC__ISSUER_URL")))
