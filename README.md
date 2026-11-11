# oc-svccore

Shared base for Python services: errors, authentication, web app factory, logging, metrics, config and database helpers.

## Modules

- [errors](#errors) - base errors and how to define service errors
- [config](#config) - settings and secrets from env, Vault and the config server
- [web](#web) - Flask app factory

## errors

`oc_svccore.errors` holds the base errors and the way to define service errors on top of them. It does not depend on HTTP or any framework.

### Base errors

| Class                               | `code`                 | Default message                 | Means                                                            |
| ----------------------------------- | ---------------------- | ------------------------------- | ---------------------------------------------------------------- |
| `BaseError`                         | `error`                | `_err_msg_error`                | root of all service errors                                       |
| `InvalidDataError`                  | `invalid_data`         | `_err_msg_invalid_data`         | the input is wrong                                               |
| `UnauthorizedError`                 | `unauthorized`         | `_err_msg_unauthorized`         | the caller is unknown or the credentials are invalid             |
| `PermissionDeniedError(permission)` | `forbidden`            | `_err_msg_forbidden`            | the caller is known but lacks `permission`, also put into `data` |
| `NotFoundError`                     | `not_found`            | `_err_msg_not_found`            | the thing does not exist                                         |
| `ConflictError`                     | `conflict`             | `_err_msg_conflict`             | a duplicate or a wrong state                                     |
| `UpstreamError`                     | `upstream_error`       | `_err_msg_upstream_error`       | a dependency failed                                              |
| `UpstreamUnavailableError`          | `upstream_unavailable` | `_err_msg_upstream_unavailable` | a dependency cannot be reached; an `UpstreamError`               |

### Every error has

- `code` - a stable category for programs and metrics, set per class;
- `message` - a translation key of the text for people, `_err_msg_<name>`;
- `data` - extra values, `{}` by default.

### Defining a service error

Subclass the base error with the right meaning and set `code`:

```python
from oc_svccore.errors import ConflictError, NotFoundError


class NoteNotFoundError(NotFoundError):
    code = "note_not_found"


class NoteTitleTakenError(ConflictError):
    code = "note_title_taken"
```

Other modules treat an error by its base class, so a `NoteNotFoundError` is handled as any `NotFoundError`.

### Messages

A message is a translation key, not text. By default it is built from `code`:

```python
raise NoteTitleTakenError()                 # message "_err_msg_note_title_taken"
```

When one `code` needs a more specific text, set the key on the class or pass it at raise:

```python
class NoteLockedError(ConflictError):
    code = "note_locked"
    message = "_err_msg_note_is_locked"


raise InvalidDataError("_err_msg_title_too_long", data={"max": 200})
```

Rules:

- keys always start with `_err_msg_`, for base and service errors alike;
- no f-strings in messages: values go to `data`, and whoever shows the text puts them into the translation;
- one `code` may have several keys (`invalid_data` with `_err_msg_title_too_long` or `_err_msg_bad_period`).

## config

`oc_svccore.config` reads settings and secrets from a fixed list of sources and turns them into typed configs, one per module, as in novacore.

### Source order

For a key `K` the first source that has a value wins:

1. **Environment.** Real environment variables first, then the `.env` file, which never overrides them. A key in the Vault form `PATH__KEY` is also looked up as `PATH_KEY`, so `DP_ACCOUNT__PASSWORD` is found by `DP_ACCOUNT_PASSWORD`.
2. **Vault**, only for keys `PATH__KEY`, through `oc_cdtapi.VaultAPI`: the field `KEY` of the KV v2 secret `PATH` under `VAULT_MOUNT_POINT`, or `KEY_TEST` when `PYTHON_ENV=test`. Skipped when `VAULT_URL` is not set.
3. **Spring Cloud Config server**, by both names like the environment. `${KEY}` and `${KEY:default}` placeholders in its values are resolved. Its values stay in memory and are not written to `os.environ`.
4. **The default** given in code.

The environment comes first because Vault and the config server are themselves configured from it. These keys are read from the environment (or `.env`) only:

| Key                                                    | For                                                            |
| ------------------------------------------------------ | -------------------------------------------------------------- |
| `VAULT_URL`, `VAULT_TOKEN`, `VAULT_MOUNT_POINT`        | Vault                                                          |
| `SPRING_CLOUD_CONFIG_URI`                              | config server; not set means no config server                  |
| `VAULT_TOKEN`, `SPRING_PROFILES_ACTIVE`                | config server token (`X-Config-Token`) and profile             |
| `SPRING_APPLICATION_NAME`, `SPRING_CLOUD_CONFIG_LABEL` | optional; the name defaults to the one given to `config.setup` |
| `PYTHON_ENV`                                           | `test` switches Vault keys to `KEY_TEST`                       |

### Startup

Call `config.setup` first in `main`, before any config is read. It loads `.env` from the current directory and remembers the application name for the config server:

```python
def main():
    config.setup("notes")
    logging.setup("notes")
    ...
```

### Defining a config

A config is a pydantic model plus a getter that maps keys to its fields:

```python
from pydantic import BaseModel

from oc_svccore.config import getter


class DpClientConfig(BaseModel):
    url: str
    username: str
    password: str
    timeout: int = 10


get_dp_client_config = getter(DpClientConfig, lambda get: dict(
    url=get("DP_URL"),
    username=get("DP_ACCOUNT__USERNAME"),
    password=get("DP_ACCOUNT__PASSWORD"),
    timeout=get("DP_TIMEOUT"),
))
```

- a key with no value gives `None`, and then the model default applies; a required field without a value fails with `config.ConfigError`, see [Failures](#failures);
- `get(key, default)` takes a default too, and `config.get_value(key)` reads a single key outside a config;
- service accounts for outgoing calls live in the config of the service that needs them, as above: a service may have several, one per target.

### Using a config

Call getters in `main`, right after `config.setup`, and pass the values on:

```python
from oc_svccore import config
from notes.dp_client_config import get_dp_client_config


def main():
    config.setup("notes")
    dp = get_dp_client_config()
    client = DpClient(dp.url, auth=(dp.username, dp.password), timeout=dp.timeout)
    ...
```

Getters load lazily. A getter first called inside a request handler would go to Vault or the config server on that request, and a missing secret would fail that request instead of the start.

The same code gets its values from a different place in each environment:

- locally, from `.env` next to the service:

  ```
  DP_URL=https://dp.test.local
  DP_ACCOUNT_USERNAME=svc-notes
  DP_ACCOUNT_PASSWORD=local-secret
  ```

- in OKD, `DP_URL` from the deployment env or the config server, and the account from Vault: secret `DP_ACCOUNT`, fields `USERNAME` and `PASSWORD`.

A single value without a model:

```python
if config.get_value("NOTES_EXPORT_ENABLED", "false") == "true":
    ...
```

In tests, set the environment and reset the getter:

```python
def test_timeout_defaults_to_10(monkeypatch):
    monkeypatch.setenv("DP_URL", "https://dp.test")
    monkeypatch.setenv("DP_ACCOUNT_USERNAME", "u")
    monkeypatch.setenv("DP_ACCOUNT_PASSWORD", "p")
    get_dp_client_config.cache_clear()
    assert get_dp_client_config().timeout == 10
```

### Loading and caching

Each source is loaded once per process, when it is first needed:

- `.env` is read by `config.setup`, which does no network calls;
- Vault is asked once per secret, when a getter that needs it runs for the first time;
- the config server is asked once, for all its values, when the first key is not found in the environment or Vault; when every key is found earlier, it is not called at all;
- a getter builds its model once and then returns the same object. Tests reset it with `get_dp_client_config.cache_clear()`.

A rotated secret is picked up after a restart.

### Failures

- a required field without a value, or a value of the wrong type, raises `config.ConfigError` with the model, the fields and the keys that had no value. Values never appear in the message:

  ```
  DpClientConfig: url: Field required (no value for DP_URL in env, vault or config server)
  ```

- config server: a missing `VAULT_TOKEN` or `SPRING_PROFILES_ACTIVE`, a failed request or a non-2xx answer raise `config.ConfigError`, so the service does not start;
- Vault: `oc_cdtapi` logs a warning and the lookup goes on to the config server and the default.

### Logging

Every built config logs one INFO line with the source of each key, never the values:

```json
{"log.level": "info", "message": "config: DpClientConfig built",
 "config": {"model": "DpClientConfig", "sources": {"DP_URL": "config_server", "DP_ACCOUNT__USERNAME": "vault",
                                                   "DP_ACCOUNT__PASSWORD": "vault", "DP_TIMEOUT": "not set"}}}
```

A source is `env`, `vault`, `config_server`, `default` (the default passed to `get`) or `not set` (the model default applies, if there is one). Configs built before `logging.setup` are not logged.

## web

### Error responses

Every error response has the same JSON body, `Content-Type: application/json`:

```json
{
  "message": "_err_msg_title_too_long",
  "code": "invalid_data",
  "data": { "max": 200 },
  "traceId": "bf4b57dee6ae2b235d7dc377122a43fa"
}
```

| Field     | For                                                                                                                                                      |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `message` | the frontend, translation key of the text                                                                                                                |
| `code`    | programs and metrics                                                                                                                                     |
| `data`    | values for the text and for programs, `{}` when there are none                                                                                           |
| `traceId` | support: the same as `trace.id` in the logs. Present when tracing is set up (`oc_svccore.logging.setup`) or the request came with a `traceparent` header |

The body has no HTTP status and no title: the status is already in the response, and a title adds nothing to `code` and `message`. This is our proposal in place of the RFC 9457 `application/problem+json` format from the R&D API guideline.

The status is looked up by the error's class hierarchy:

| Error                           | Status |
| ------------------------------- | ------ |
| `BaseError`, `InvalidDataError` | 400    |
| `UnauthorizedError`             | 401    |
| `PermissionDeniedError`         | 403    |
| `NotFoundError`                 | 404    |
| `ConflictError`                 | 409    |
| `UpstreamError`                 | 502    |
| `UpstreamUnavailableError`      | 503    |

A service changes or adds a status with `create_app(errors_mapping={NoteLockedError: 423})`.

Errors made by the web layer itself:

| Case                                            | Status | `code`                 | `message`                       |
| ----------------------------------------------- | ------ | ---------------------- | ------------------------------- |
| request body or query fails pydantic validation | 400    | `validation`           | `_err_msg_validation`           |
| no `Authorization: Bearer` header               | 401    | `unauthorized`         | `_err_msg_missing_token`        |
| token with a bad signature, issuer or expiry    | 401    | `unauthorized`         | `_err_msg_invalid_token`        |
| unknown route                                   | 404    | `not_found`            | `_err_msg_not_found`            |
| method not allowed on a route                   | 405    | `method_not_allowed`   | `_err_msg_method_not_allowed`   |
| Keycloak keys cannot be fetched                 | 503    | `upstream_unavailable` | `_err_msg_keycloak_unavailable` |
| any other exception                             | 500    | `internal`             | `_err_msg_internal`             |

A validation error lists every wrong field in `data.errors`. `field` is the path to the value, `message` is `_err_msg_` plus the pydantic error type:

```json
{
  "message": "_err_msg_validation",
  "code": "validation",
  "data": {
    "errors": [
      { "field": "title", "message": "_err_msg_string_too_short" },
      { "field": "items[1].title", "message": "_err_msg_missing" }
    ]
  },
  "traceId": "bf4b57dee6ae2b235d7dc377122a43fa"
}
```

A 500 never shows the exception text. Each 5xx is logged once at ERROR with the stack trace; 4xx are the caller's mistake and are not logged at ERROR.
