from pydantic import BaseModel

from oc_svccore.config import getter


class OidcClientConfig(BaseModel):
    client_id: str
    client_secret: str | None = None


get_oidc_client_config = getter(
    OidcClientConfig,
    lambda get: dict(client_id=get("OIDC__CLIENT_ID"), client_secret=get("OIDC__CLIENT_SECRET")),
)
