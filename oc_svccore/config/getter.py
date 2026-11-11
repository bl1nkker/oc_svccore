import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from oc_svccore.config.config_error import ConfigError
from oc_svccore.config.resolver import resolve

M = TypeVar("M", bound=BaseModel)

log = logging.getLogger(__name__)


def getter(model: type[M], build: Callable[[Callable[..., Any]], dict[str, Any]]) -> Callable[[], M]:
    @functools.cache
    def get() -> M:
        sources: dict[str, str] = {}

        def lookup(key: str, default: Any = None) -> Any:
            value, source = resolve(key)
            if value is None:
                value, source = default, "default" if default is not None else "not set"
            sources[key] = source
            return value

        values = {name: value for name, value in build(lookup).items() if value is not None}
        try:
            config = model(**values)
        except ValidationError as e:
            raise ConfigError(_describe(model, e, sources)) from None
        log.info("config: %s built", model.__name__, extra={"config.model": model.__name__, "config.sources": sources})
        return config

    return get


def _describe(model: type[BaseModel], error: ValidationError, sources: dict[str, str]) -> str:
    problems = "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
        for e in error.errors(include_url=False, include_context=False, include_input=False)
    )
    missing = [key for key, source in sources.items() if source == "not set"]
    hint = f" (no value for {', '.join(missing)} in env, vault or config server)" if missing else ""
    return f"{model.__name__}: {problems}{hint}"
