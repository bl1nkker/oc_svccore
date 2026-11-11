# oc-svccore

Shared base for Python services: errors, authentication, web app factory, logging, metrics, config and database helpers.

## Modules

- [errors](#errors) - base errors and how to define service errors
- [config](#config) - settings and secrets from env, Vault and the config server
- [logging](#logging) - ECS JSON logs and tracing
- [db](#db) - database, transactions and repositories
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

## logging

`oc_svccore.logging` sets up the logs and traces of a process through `oc-logging`: every record, from the service and its libraries, is one ECS JSON object per line on stdout. It works the same for a web service, a worker or a CLI command.

### Startup

Call `logging.setup` in `main`, right after `config.setup`:

```python
def main():
    config.setup("notes")
    logging.setup("notes")
    ...
```

It:

- writes ECS JSON with `service.name` and `service.environment` (`PYTHON_ENV` in lower case);
- sets up OpenTelemetry tracing: a line logged inside a span has `trace.id` and `span.id`, and every call made with `requests` sends a `traceparent` header, so one `trace.id` finds a request in every service it went through;
- sets `OTEL_SERVICE_NAME` to the service name when it is not set, so traces and logs have the same name.

Spans are exported over OTLP only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Trace ids are made and passed on either way.

### Config

| Key         | Default | For                                                                     |
| ----------- | ------- | ----------------------------------------------------------------------- |
| `LOG_LEVEL` | `INFO`  | root level: `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, any case |

A wrong value fails the start with `config.ConfigError`.

### gunicorn

gunicorn logs through `logconfig_dict` in `gunicorn.conf.py`, so its own lines are ECS JSON too:

```python
from oc_logging.ecs import ecs_logconfig

from notes.main import SERVICE

logconfig_dict = ecs_logconfig(SERVICE)
```

`gunicorn.conf.py` runs before the service, so gunicorn's own lines take `LOG_LEVEL` from the environment only, not from Vault or the config server.

### Writing logs

Use the standard `logging` module. Extra fields go to `extra` with dotted names, which come out nested:

```python
log = logging.getLogger(__name__)

log.info("notes exported", extra={"notes.count": len(notes)})
```

```json
{"@timestamp": "2026-11-11T07:26:33.346Z", "log.level": "info", "message": "notes exported",
 "log": {"logger": "notes.export"}, "service": {"name": "notes"},
 "trace": {"id": "bf4b57dee6ae2b235d7dc377122a43fa"}, "span": {"id": "a1256df6da8ad7db"}, "notes": {"count": 3}}
```

Rules:

- never log secrets, tokens or request bodies;
- log a failure once, at ERROR with `exc_info`, where it is handled. Do not log and re-raise.

## db

`oc_svccore.db` is the database layer on SQLAlchemy 2: an engine with metrics, transaction scopes and base repositories. It comes with the `db` extra, `pip install oc-svccore[db]`. It does not depend on HTTP, so a worker or a script uses it the same way as a web service.

### Config

| Key              | For                                                   |
| ---------------- | ----------------------------------------------------- |
| `PSQL__URL`      | `host:port/db`, optionally `?search_path=schema`      |
| `PSQL__USER`     | user                                                  |
| `PSQL__PASSWORD` | password                                              |

The keys follow the [config](#config) rules: `PSQL_URL` in env, the field `URL` of the Vault secret `PSQL`.

`get_db_config().postgres_url()` builds the connection string. The user and the password are escaped, and `search_path` goes to `options=-csearch_path=...`, since PostgreSQL does not take it as a url parameter.

### Database

```python
database = Database(get_db_config().postgres_url())
```

- `database.engine` checks a connection before use (`pool_pre_ping`) and has the default pool: 5 connections, 10 more under load;
- connecting gives up after 5 seconds (`CONNECT_TIMEOUT_SEC`). Change it with `Database(url, connect_args={"connect_timeout": 10})`; other keyword arguments go to `create_engine`;
- `database.sessionmaker()` opens a session;
- `database.ping()` runs `select 1`, for the health checks: `checks={"postgres": database.ping}`;
- every query is timed in `dependency_request_duration_seconds{dependency="postgres"}`. `Database(url, name="cnt")` changes the label.

In a web service the session of a request comes from `web.request_session(database)`, see [Database session](#database-session). A worker or a script opens its own:

```python
with database.sessionmaker() as session:
    NoteService(NoteRepo(session)).archive_old()
```

### Transactions

`repo.session()` (the same as `session_context(session)`) is a transaction scope:

- the outermost scope commits on success and rolls back on any exception;
- a nested scope is a savepoint: when the outer code catches an error from it, only the nested part is rolled back;
- reads need no scope.

```python
def create(self, title: str, author: str) -> Note:
    with self._repo.session():
        if self._repo.find_by_title(title):
            raise NoteTitleTakenError()
        return self._repo.save_or_update(Note(title=title, author=author))
```

Every outermost scope is a commit of its own. When one operation writes through several repositories, the service opens one scope around all of them, so either all is saved or nothing. Repositories built on the same session share its scopes.

### Repositories

`DataRepo[T]` holds the common operations on one model. A repository adds its own queries on top:

```python
class NoteRepo(DataRepo[Note]):
    _type = Note
    _order_by_map = {"title": Note.title, "created_at": Note.created_at}

    def find_by_title(self, title: str) -> Note | None:
        return self.first(self.query().filter(Note.title == title))
```

| Method                                             | Does                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `query()`                                          | a `Query` of the model                                             |
| `get_by_db_id(id)`                                 | the row with this `id`, or `None`                                  |
| `first(q)`, `single(q)`, `list_all(q)`, `count(q)` | run a query, `query()` by default                                  |
| `list_paged(page, page_size, q)`                   | `Pagination(page, page_size, total, items)`, `page` starts at 1    |
| `order_by(key, asc, q)`                            | sorts by a key of `_order_by_map`; an unknown key sorts by `id`    |
| `with_for_update(q)`                               | `SELECT ... FOR UPDATE`                                            |
| `save_or_update(entity)`, `delete(entity)`         | add or delete and flush; the commit is up to the transaction scope |

`list_paged` does not check `page` and `page_size`, the API layer validates them. `BaseRepo` is a repository without the model methods, for raw SQL.

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

### Request logs

`create_app` adds to every request except the probes and `/metrics`:

- one access line on the `access` logger with `http.request.method`, `url.path`, `http.response.status_code` and `event.duration` in nanoseconds;
- a span that continues an incoming `traceparent` header;
- `user.name` of the caller on every line logged inside the request, once the caller is authenticated;
- the `X-Request-Id` response header with the trace id, the same as `trace.id` in the logs and `traceId` in an error body.

Query strings and request bodies are not logged.

### Database session

`web.request_session(database)` gives the session of the current request: one per database, opened on first use and closed when the request ends.

```python
def service() -> NoteService:
    return NoteService(NoteRepo(web.request_session(database)))
```
