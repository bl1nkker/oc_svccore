from pydantic import BaseModel

from oc_svccore.config import getter


class BuildConfig(BaseModel):
    version: str = "unknown"
    git_sha: str = "unknown"


get_build_config = getter(BuildConfig, lambda get: dict(version=get("APP_VERSION"), git_sha=get("GIT_SHA")))
