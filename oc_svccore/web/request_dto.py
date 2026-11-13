from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from flask import request

from oc_svccore.dto import ApiModel

F = TypeVar("F", bound=Callable[..., Any])


def body(model: type[ApiModel]) -> Callable[[F], F]:
    return _inject("body", model, lambda: request.get_json())


def query(model: type[ApiModel]) -> Callable[[F], F]:
    return _inject("query", model, lambda: request.args.to_dict())


def _inject(name: str, model: type[ApiModel], read: Callable[[], Any]) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            kwargs[name] = model.parse(read())
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
