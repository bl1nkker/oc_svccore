import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from oc_svccore.authn import Verifier


class Issuer:
    kid = "oc-svccore-test"

    def __init__(self, url: str = "https://keycloak.test/realms/test") -> None:
        self.url = url
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def verifier(self, audience: str | None = None) -> Verifier:
        return Verifier(self.url, key=self._key.public_key(), audience=audience)

    def jwks(self) -> dict[str, Any]:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def token(self, username: str, *groups: str, expires_in: int = 3600) -> str:
        now = int(time.time())
        return self.sign({
            "iss": self.url,
            "sub": username,
            "preferred_username": username,
            "groups": list(groups),
            "iat": now,
            "exp": now + expires_in,
        })

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": self.kid})
