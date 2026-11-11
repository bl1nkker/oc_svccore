import functools
import os
import re
from typing import Any

from oc_svccore.config.config_server import fetch_config_server
from oc_svccore.config.env_file import load_env_file

SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]*__[A-Z][A-Z0-9_]*$")

_application: str | None = None


def setup(application: str, env_file: str = ".env") -> None:
    global _application
    _application = application
    load_env_file(env_file)


def get_value(key: str, default: Any = None) -> Any:
    value, _ = resolve(key)
    return default if value is None else value


def resolve(key: str) -> tuple[Any, str | None]:
    # Env comes first: Vault and the config server are themselves configured from env.
    for name, source in (("env", _from_env), ("vault", _from_vault), ("config_server", _from_config_server)):
        value = source(key)
        if value is not None:
            return value, name
    return None, None


def _names(key: str) -> tuple[str, ...]:
    return (key, key.replace("__", "_")) if "__" in key else (key,)


def _from_env(key: str) -> str | None:
    return next((os.environ[name] for name in _names(key) if os.environ.get(name)), None)


def _from_vault(key: str) -> Any:
    if not SECRET_NAME.match(key) or not os.environ.get("VAULT_URL"):
        return None
    return _vault().load_secret(key)


def _from_config_server(key: str) -> str | None:
    values = _config_server_values()
    return next((values[name] for name in _names(key) if name in values), None)


@functools.cache
def _vault():
    from oc_cdtapi.VaultAPI import VaultAPI

    return VaultAPI()


@functools.cache
def _config_server_values() -> dict[str, str]:
    return fetch_config_server(_application)
