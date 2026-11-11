from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator

from oc_svccore.config import getter


class LogConfig(BaseModel):
    level: Annotated[Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], BeforeValidator(str.upper)] = "INFO"


get_log_config = getter(LogConfig, lambda get: dict(level=get("LOG_LEVEL")))
