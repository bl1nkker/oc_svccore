import logging
import os
import re
from typing import Any

import requests

from oc_svccore.config.config_error import ConfigError

log = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\$\{([^${}]+)\}")


def fetch_config_server(application: str | None) -> dict[str, str]:
    uri = os.getenv("SPRING_CLOUD_CONFIG_URI")
    if not uri:
        return {}
    token, profile = os.getenv("VAULT_TOKEN"), os.getenv("SPRING_PROFILES_ACTIVE")
    for name, value in (("VAULT_TOKEN", token), ("SPRING_PROFILES_ACTIVE", profile)):
        if not value:
            raise ConfigError(f"config server: missing env var {name}")
    application = os.getenv("SPRING_APPLICATION_NAME") or application
    if not application:
        raise ConfigError("config server: application name is not set, call config.setup(application)")
    endpoint = f"{uri.rstrip('/')}/{application}/{profile}"
    if label := os.getenv("SPRING_CLOUD_CONFIG_LABEL"):
        endpoint += f"/{label}"

    try:
        resp = requests.get(endpoint, headers={"X-Config-Token": token}, timeout=30)
    except requests.RequestException as e:
        raise ConfigError(f"config server: request failed: {e}") from e
    if not 200 <= resp.status_code < 300:
        raise ConfigError(f"config server: unexpected status {resp.status_code}")

    props: dict[str, str] = {}
    for source in reversed(resp.json().get("propertySources", [])):
        props.update({k: _to_str(v) for k, v in source.get("source", {}).items()})
    _resolve(props)
    log.info("config server: loaded properties", extra={"count": len(props)})
    return props


def _to_str(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _resolve(props: dict[str, str]) -> None:
    def replace(match: re.Match[str]) -> str:
        key, sep, fallback = match.group(1).partition(":")
        if key in props:
            return props[key]
        return fallback if sep else match.group(0)

    for _ in range(10):
        for key, value in props.items():
            props[key] = _PLACEHOLDER.sub(replace, value)
