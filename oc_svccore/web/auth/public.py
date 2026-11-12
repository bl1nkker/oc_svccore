from collections.abc import Callable
from typing import Any, TypeVar

View = TypeVar("View", bound=Callable[..., Any])


def public(view: View) -> View:
    setattr(view, "_oc_svccore_public", True)
    return view


def is_public(view: Callable[..., Any]) -> bool:
    return getattr(view, "_oc_svccore_public", False)
