# oc-svccore

Shared base for Python services: errors, authentication, web app factory, logging, metrics, config and database helpers.

## Modules

- [errors](#errors) - base errors and how to define service errors
- [config](#config) - settings and secrets from env, Vault and the config server
- [logging](#logging) - ECS JSON logs and tracing
- [db](#db) - database, transactions and repositories
- [metrics](#metrics) - Prometheus metrics and dependency checks
- [authn](#authn) - token checks and the service's own token for outgoing calls
- [dto](#dto) - base DTOs: camelCase fields and the shape of lists
- [web](#web) - Flask app factory
- [cli](#cli-experimental) - command line app factory, experimental
- [testing](#testing) - test tokens, a fake Keycloak and pytest fixtures

`web` and `cli` are the two ways in. The other modules work the same behind either of them; an adapter only turns its input into calls and the errors into its own answer, an HTTP response or an exit code.

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
    _order_by_map = {"title": Note.title, "createdAt": Note.created_at}

    def find_by_title(self, title: str) -> Note | None:
        return self.first(self.query().filter(Note.title == title))
```

| Method                                             | Does                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `query()`                                          | a `Query` of the model                                             |
| `get_by_db_id(id)`                                 | the row with this `id`, or `None`                                  |
| `first(q)`, `single(q)`, `list_all(q)`, `count(q)` | run a query, `query()` by default                                  |
| `list_paged(page, page_size, q)`                   | `Pagination(page, page_size, total, items)`, `page` starts at 1    |
| `order_by(sort, q)`                                | sorts by `sort` of a list query, see below                         |
| `with_for_update(q)`                               | `SELECT ... FOR UPDATE`                                            |
| `save_or_update(entity)`, `delete(entity)`         | add or delete and flush; the commit is up to the transaction scope |

`list_paged` does not check `page` and `page_size`, the API layer validates them. `BaseRepo` is a repository without the model methods, for raw SQL.

`order_by(sort)` takes `sort` as the caller sent it in a [list query](#lists): `createdAt`, or `-createdAt` for descending. The keys of `_order_by_map` are these API names, so only the listed fields can be sorted by. Without `sort` the rows are sorted by `_default_order_by` (`id`). Any other field raises `InvalidSortError`, a 400:

```json
{ "message": "_err_msg_invalid_sort", "code": "invalid_sort", "data": { "sort": "author", "allowed": ["createdAt", "title"] } }
```

## metrics

`oc_svccore.metrics` defines the Prometheus metrics of a process, with the names and labels of the observability guardrails, and the ways to update them. The metrics live in the memory of the process. Serving them is up to the process: `web` adds `GET /metrics`, a worker starts its own endpoint. The module does not depend on HTTP, a framework or a database library.

- `kinds/` - the metrics: `build_info.py`, `dependencies.py`, `operation.py`;
- `setup.py`, `registry.py`, `checks.py`, `build_config.py` - the setup, the registry with the service prefix, the dependency checks and the build config.

### Startup

A web service gets it from `create_app(service="notes", checks=...)`. A worker calls it itself and serves the metrics with `prometheus_client`:

```python
from prometheus_client import start_http_server

metrics.setup("notes_worker", {"postgres": database.ping})
start_http_server(8080)
```

Every metric name starts with the service name, `-` and other non-word characters replaced by `_`. Each metric is created once per process, so building the app again in tests does not fail on a duplicate.

### Metrics

| Metric                                                 | Labels                                    | Updated                                                                 |
| ------------------------------------------------------ | ----------------------------------------- | ----------------------------------------------------------------------- |
| `<service>_build_info`                                 | `version`, `git_sha`                      | at setup, from `APP_VERSION` and `GIT_SHA`, `unknown` when not set      |
| `<service>_dependency_up`                              | `dependency`                              | on every scrape, by running the checks                                  |
| `<service>_dependency_request_duration_seconds`        | `dependency`, `outcome` (`success`/`error`) | on every database query and every `metrics.dependency` block          |
| `<service>_<operation>_total`                          | `outcome`                                 | on every attempt of a business operation                                |
| `<service>_<operation>_duration_seconds`               |                                           | on every attempt                                                        |
| `<service>_<operation>_last_success_timestamp_seconds` |                                           | on success, `0` until the first one                                     |

The default runtime metrics of `prometheus_client` stay on. The HTTP request metrics are made by [web](#metrics-endpoint).

### Business operations

Declare an operation once, at module level, and wrap the code that does it:

```python
CREATE_NOTE = metrics.operation("create_note")


@bp.post("")
@CREATE_NOTE
def create_note():
    ...


with CREATE_NOTE.track():
    ...
```

| `outcome`  | When                                                                                     |
| ---------- | ---------------------------------------------------------------------------------------- |
| `success`  | no exception                                                                             |
| `rejected` | a `BaseError` other than `UpstreamError`, input that fails `parse` among them: the caller's mistake |
| `failed`   | an `UpstreamError` or any other exception: the service's own failure, the one that alerts |

Every outcome starts at `0`, so the series exist before the first attempt. An operation may be declared before `metrics.setup`, it is bound at setup.

### Dependencies

Time an outgoing call; an exception inside counts as `error`:

```python
with metrics.dependency("dp"):
    dp.get_delivery(delivery_id)
```

Database queries are timed by [db](#database) itself.

A check is a function that raises when the dependency is down, such as `database.ping`. The checks run in parallel, 2 seconds for all of them; a check that takes longer counts as down. They feed `dependency_up` and `/health`. A dependency that goes down is logged once at WARNING with the reason, and once at INFO when it is back. The reason is never in a metric or a response.

### Rules

- labels hold only values from a small fixed set: never an id, a user name, an e-mail, a URL or exception text;
- the service README lists every business metric, and a test checks that `/metrics` has it.

## authn

`oc_svccore.authn` checks whose token it is, gets the service's own token for outgoing calls and talks the OIDC login of a BFF, all through Keycloak. It does not depend on HTTP or a framework: reading the token or the session from a request is done by [web](#authentication).

| Case | Use |
| --- | --- |
| a resource service: other services call it with a Keycloak token | `web.bearer_auth()`, see [Authentication](#authentication) |
| a BFF: a browser calls it with a session cookie | `web.session_auth()`, see [BFF session](#bff-session) |
| the service calls another service | `PasswordTokenAuth`, see [Outgoing calls](#outgoing-calls) |
| a token comes outside an HTTP request, in a worker or a CLI | `verifier.principal(token)`, see [Checking a token](#checking-a-token) |

### Config

| Key                   | For                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------ |
| `OIDC__ISSUER_URL`    | the realm, `https://<keycloak>/realms/<realm>`: issuer of the tokens, base of the key and token endpoints |
| `OIDC__CLIENT_ID`     | the client for outgoing calls                                                        |
| `OIDC__CLIENT_SECRET` | its secret, optional                                                                 |

### Principal

`Principal(username, claims)` is who made the call. `username` is `preferred_username` of the token, or `sub` when there is none; `claims` holds every field of the checked token. For a resource service it is usually the technical account of the calling service, not a person.

### Checking a token

```python
verifier = authn.keycloak_verifier(authn.get_auth_config().issuer_url)
principal = verifier.principal(token)
```

- the signature is checked with the realm keys (JWKS), and so are the issuer and the expiry. `aud` is checked only when given, `keycloak_verifier(url, audience="portal")`: every token of the realm has the same `aud` today, so a resource service gains nothing from it;
- the keys are fetched from Keycloak with a 5 second timeout (`JWKS_TIMEOUT_SEC`) and cached for 5 minutes;
- a bad, expired or foreign token raises `UnauthorizedError("_err_msg_invalid_token")` and logs one WARNING line with the reason;
- Keycloak not answering raises `UpstreamUnavailableError("_err_msg_keycloak_unavailable")`.

`verifier.verify(token)` returns the claims only. In tests, `oc_svccore.testing.Issuer` signs tokens and its `verifier()` checks them without Keycloak.

### Outgoing calls

`PasswordTokenAuth` is a `requests` auth: it gets a token with the password grant of the service account and adds `Authorization: Bearer` to every call.

```python
oidc = authn.get_oidc_client_config()
dp = get_dp_client_config()
auth = authn.PasswordTokenAuth(issuer_url, oidc.client_id, oidc.client_secret, dp.username, dp.password)

requests.get(f"{dp.url}/api/v1/deliveries", auth=auth, timeout=10)
api.web.auth = auth  # an oc_cdtapi client
```

- the token is kept until 30 seconds before it expires, one fetch at a time across threads;
- the token endpoint is called with a 10 second timeout, `timeout=` changes it;
- Keycloak not answering or answering 5xx raises `UpstreamUnavailableError("_err_msg_keycloak_unavailable")` (503);
- a 4xx, such as a wrong password, raises `UpstreamError("_err_msg_keycloak_rejected_credentials")` (502), so a wrong secret is not mistaken for an outage.

The account and the password are in the config of the service that makes the calls, see [Defining a config](#defining-a-config).

### Login of a BFF

`OidcClient(issuer_url, client_id, client_secret, redirect_url)` is the Keycloak side of the browser login: the login URL with PKCE (S256) and the scopes `openid profile email`, the code exchange, the refresh and the logout URL. The id token is checked with `aud` equal to the client id. A refresh that Keycloak refuses (`invalid_grant`) raises `RefreshRejectedError`; Keycloak not answering raises `UpstreamUnavailableError`. The cookies and the `/auth/*` routes around it are [web.SessionAuth](#bff-session).

## dto

`oc_svccore.dto` holds the base DTOs of the API contract: the field names on the wire and the shape of lists. It does not depend on HTTP or a framework, so a client, such as a CLI that reads the answer of a service, uses the same DTOs.

### Fields

`ApiModel` is the base of request and response models. The fields are snake_case in Python and camelCase in JSON and in the query string:

```python
class ReadNote(ApiModel):
    note_id: str
    created_at: datetime


ReadNote.model_validate(note).model_dump(mode="json")  # {"noteId": "1", "createdAt": "2026-11-09T10:15:00Z"}
```

- input is read by either name, `createdAt` or `created_at`;
- `model_dump` writes camelCase without `by_alias=True`;
- `model_validate` takes an ORM object as well as a dict.

Input from a caller is read with `parse`, output with `model_validate`:

```python
note_dto.Create.parse({"title": ""})  # raises ValidationFailedError: 400 validation, every wrong field in data.errors
```

`ValidationFailedError` is an `InvalidDataError`, so wrong input is a 400 and an operation counts it as `rejected`. A pydantic `ValidationError` from `model_validate` is not translated: a response that does not fit its model is the service's bug, a logged 500 `internal`. In a web service `@web.body` and `@web.query` call `parse`, see [Request body and query](#request-body-and-query).

### Lists

```
GET /api/v1/notes?page=2&pageSize=50&sort=-createdAt&search=report
{ "items": [ ... ], "page": 2, "pageSize": 50, "total": 1342 }
```

`ListQuery` reads the query string: `page` from 1 to 1000000, `pageSize` 50 by default and at most 500, `sort` as `field` or `-field`, and `search`, free text the service looks up as it sees fit. A wrong value is a 400 that names the parameter, `"field": "pageSize"`. Filters go into a subclass and are named after their field:

```python
class NoteQuery(ListQuery):
    author: str | None = None


@bp.get("")
@web.query(NoteQuery)
def list_notes(query: NoteQuery):
    pagination = service().list(query.page, query.page_size, query.sort)
    return Page[ReadNote].model_validate(pagination).model_dump(mode="json")
```

`Page[T]` is the answer, always wrapped in `items`. It is built from the `Pagination` of `list_paged`, and `sort` goes to `order_by`, see [Repositories](#repositories).

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
| request body or query fails `parse`             | 400    | `validation`           | `_err_msg_validation`           |
| no `Authorization: Bearer` header               | 401    | `unauthorized`         | `_err_msg_missing_token`        |
| token with a bad signature, issuer or expiry    | 401    | `unauthorized`         | `_err_msg_invalid_token`        |
| no session, or the session ended (BFF)          | 401    | `unauthorized`         | `_err_msg_no_session`           |
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

A pydantic `ValidationError` that is not from `parse`, such as a response model that does not fit, is a 500 `internal`.

A 500 never shows the exception text. Each 5xx is logged once at ERROR with the stack trace; 4xx are the caller's mistake and are not logged at ERROR.

### Request logs

`create_app` adds to every request except the probes and `/metrics`:

- one access line on the `access` logger with `http.request.method`, `url.path`, `http.response.status_code` and `event.duration` in nanoseconds;
- a span that continues an incoming `traceparent` header;
- `user.name` of the caller on every line logged inside the request, once the caller is authenticated;
- the `X-Request-Id` response header with the trace id, the same as `trace.id` in the logs and `traceId` in an error body.

Query strings and request bodies are not logged.

### Authentication

`create_app(authenticate=...)` checks every request before the view. The service picks how:

```python
app = web.create_app(__name__, service="dp", authenticate=web.bearer_auth())    # a resource service
app = web.create_app(__name__, service="bff", authenticate=web.session_auth())  # a BFF
```

| | `web.bearer_auth()` | `web.session_auth()` |
| --- | --- | --- |
| Caller | another service with a Keycloak token | a browser with a session cookie |
| Each request | `Authorization: Bearer <token>`, checked by [authn](#checking-a-token) | the session cookie, refreshed in Keycloak when it is older than the refresh interval |
| Extra routes | none | `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me`, see [BFF session](#bff-session) |
| Config | [authn](#authn) | authn plus the session keys below |

Both build everything from the config. `web.bearer(verifier)` and `web.SessionAuth(client, config)` take the parts directly, for tests.

- every route needs a caller except views marked `@web.public`. The probes and `/metrics` are public; an unknown path is a 404 without a check;
- in a view, `web.current_principal()` returns the caller. In a public view it raises `UnauthorizedError`;
- `authenticate` may also be any other function from a request to a `Principal`.

```python
@bp.post("")
def create_note():
    author = web.current_principal().username
    ...
```

A service without authentication says so with `authenticate=None`. Then no request is checked and `web.current_principal()` raises `UnauthorizedError` everywhere. The argument has no default, so a service that forgets it does not start instead of being open to everyone:

```python
app = web.create_app(__name__, service="dlgen", authenticate=None)
```

### BFF session

`web.session_auth()` works like the Go bff (`idp-bff/internal/auth`), so the frontend and the deployment config are the same for both:

| Route | Does |
| --- | --- |
| `GET /auth/login?returnTo=<path>&origin=<origin>` | starts the Keycloak login with PKCE and redirects there. `returnTo` is kept only when it is a plain path of this site, `origin` only when it is in `OIDC_RETURN_ORIGINS` |
| `GET /auth/callback` | checks the state, exchanges the code, starts the session, redirects to `origin` + `returnTo`, or to `POST_LOGIN_REDIRECT_PATH`. A failure shows a short page with a "Sign in again" link |
| `GET /auth/logout?returnTo=&origin=` | drops the session and redirects to the Keycloak logout |
| `GET /auth/me` | `{"authenticated": true, "sub", "username", "name", "email"}`, or 401 without a session |

- the session lives in HttpOnly, SameSite=Lax cookies, encrypted and signed: `<name>` (who and until when), `<name>_rt` (the refresh token), `<name>_idt` (the id token for the logout) and `<name>_txn` for the 30 minutes of a login;
- a session older than `SESSION_REFRESH_INTERVAL` is refreshed in Keycloak on the next request. When Keycloak refuses the refresh, the session is dropped and the request gets 401; when Keycloak does not answer, the current session goes on;
- a session ends after `SESSION_TTL` without a refresh;
- the cookie format is not the one of the Go bff (gorilla securecookie), so a cookie of one does not work in the other;
- `/auth/me` has no `permissions`: they are authorization, which is not in this library.

| Key | Default | For |
| --- | --- | --- |
| `OIDC_REDIRECT_URL` | | the callback, `https://<bff>/auth/callback` |
| `OIDC_RETURN_ORIGINS` | none | origins allowed in `origin`, comma separated |
| `POST_LOGIN_REDIRECT_PATH` | `/` | where to go after the login without `returnTo` |
| `OIDC_POST_LOGOUT_REDIRECT_URL` | origin of the redirect url + `POST_LOGIN_REDIRECT_PATH` | where Keycloak returns after the logout without `origin` |
| `SESSION__HASH_KEY`, `SESSION__BLOCK_KEY` | | base64, at least 16 bytes each: signing and encryption keys of the cookies |
| `SESSION_COOKIE_NAME` | `session` | |
| `SESSION_COOKIE_SECURE` | `true` | `false` only for plain http in local runs |
| `SESSION_TTL` | `8h` | in the Go format: `8h`, `5m`, `1m30s` |
| `SESSION_REFRESH_INTERVAL` | `5m` | |

The client is `OIDC__CLIENT_ID` and `OIDC__CLIENT_SECRET` of [authn](#authn). Locally, `python -m oc_svccore.testing.dev_issuer` also answers the browser login and signs in as `--user` at once. `services/notes-bff` is an example BFF that reads notes with its technical account.

### Metrics endpoint

`create_app` sets up [metrics](#metrics) with its `service` and `checks` and adds:

- `GET /metrics` in the Prometheus text format, without authentication;
- `<service>_http_requests_total{method, route, status}` and `<service>_http_request_duration_seconds{method, route}`. `route` is the route template (`/notes/{note_id}`), an unknown path is `unmatched`. The probes and `/metrics` are not counted.

The metrics are in the memory of one process, so gunicorn runs one worker per pod (`workers = 1`) and scales with threads and replicas.

### Request body and query

`@web.body(Model)` reads the JSON body, `@web.query(Model)` the query string. Each calls `Model.parse` and passes the DTO to the view as `body` or `query`, next to the path parameters:

```python
@bp.put("/<int:note_id>")
@UPDATE_NOTE
@web.body(note_dto.Update)
def update_note(note_id: int, body: note_dto.Update):
    note = service().update(note_id, body.title)
    return note_dto.Read.model_validate(note).model_dump(mode="json")
```

- a wrong value is a 400 `validation` before the view runs, so it is checked before any permission inside the view;
- below a [business operation](#business-operations), wrong input counts as `rejected`. Above it, the operation never sees the attempt;
- the answer is not serialized for the view: it returns `model_dump(mode="json")` as before.

### Database session

`web.request_session(database)` gives the session of the current request: one per database, opened on first use and closed when the request ends.

```python
def service() -> NoteService:
    return NoteService(NoteRepo(web.request_session(database)))
```

## cli (experimental)

`oc_svccore.cli` is the command line counterpart of `web.create_app`, on click. It comes with the `cli` extra, `pip install oc-svccore[cli]`, and does not depend on HTTP. Experimental: the API may change.

```python
import click

from oc_svccore import cli

app = cli.create_app("notes-cli")


@app.command(help="List notes.")
def list_notes():
    click.echo(...)


if __name__ == "__main__":
    app()
```

`cli.create_app(service)` returns a click group that:

- calls `config.setup(service)` before any command, so `.env`, Vault and the config server work as in a web service;
- logs to stderr as plain text, so the logs never mix with what a command prints: WARNING by default, `-v` for INFO, `-vv` for DEBUG. It does not use `logging.setup`, whose ECS JSON goes to stdout;
- turns errors into exit codes:

| Case | stderr | Exit code |
| --- | --- | --- |
| success | | `0` |
| a `BaseError` | `error: <message> <data as JSON>` | `1` |
| a `config.ConfigError` | `error: <the config error>` | `1` |
| any other exception | the stack trace | `1` |
| wrong command or arguments | click's usage error | `2` |

Metrics, tracing and health are not set up: a short process does not keep them. `services/notes-cli` is an example that signs in with a service account and calls notes.

## testing

`oc_svccore.testing` comes with the `testing` extra, `pip install oc-svccore[testing]`.

### Tokens without Keycloak

```python
from oc_svccore.testing import Issuer, bearer

issuer = Issuer()
app = create_app(database, web.bearer(issuer.verifier()))
app.test_client().get("/notes", headers=bearer(issuer.token("writer")))
```

- `Issuer()` makes its own RSA key. `token(username, *groups, expires_in=3600)` signs a token with `preferred_username`, `groups` and the expiry; `sign(claims)` signs any claims, for an expired or a foreign token;
- `issuer.verifier()` checks its tokens the way `keycloak_verifier` checks the ones of Keycloak, so authentication runs for real and nothing is patched;
- `bearer(token)` is the `Authorization` header.

### pytest fixtures

The package registers a pytest plugin, so the fixtures need no import:

| Fixture | Scope | Gives |
| --- | --- | --- |
| `issuer` | session | an `Issuer` |
| `client` | test | `app.test_client()` of the `app` fixture, which the service defines |
| `db_migrations` | session | a function that gets the engine and creates the tables. Does nothing until the service overrides it |
| `db_engine` | session | an engine on `TEST_DATABASE_URL`, after `db_migrations`. The test fails when the variable is not set |
| `db_session` | test | a session in a transaction that is rolled back after the test. A commit in the code only releases a savepoint |

The `db_*` fixtures are there with the `db` extra.

```python
@pytest.fixture(scope="session")
def db_migrations():
    return migrate


@pytest.fixture
def app(issuer, db_session):
    database = Database(os.environ["TEST_DATABASE_URL"])
    database.sessionmaker = lambda: db_session
    return create_app(database, web.bearer(issuer.verifier()))
```

### Fake Keycloak

`python -m oc_svccore.testing.dev_issuer --port 8099 --user dev-user` stands in for Keycloak in local runs and in tests over HTTP:

- it answers the keys (JWKS), the password grant (any password, the token is for the given username), the browser login with PKCE (signs in as `--user` at once, without a form), the refresh and the logout;
- it prints `OIDC_ISSUER_URL` for the services and a token for `--user` that lives 24 hours;
- in tests, `DevIssuerServer()` runs it on a free port, and its `issuer` signs tokens for it.

Every local service that calls another must point to the same issuer.

### Spec

```python
def test_routes_match_the_spec(app):
    assert_spec(app, "spec/openapi.yaml")
```

`assert_spec` compares the routes of the app with `paths` of the spec, method by method, and fails with the list of routes missing from the spec and of paths that are not served. Path parameters are compared by place, not by name: `/notes/<int:note_id>` matches `/notes/{noteId}`. The routes of the library itself (the probes, `/metrics`, `/auth/*` of a BFF) may be in the spec or not, as the service prefers. The bodies are not compared. It needs PyYAML, which comes with the `testing` extra.

### Plans

Services and repositories are to be tested on a real database instead of fakes, with the `db_*` fixtures above: each test in its own transaction that is rolled back. For that `db_migrations` needs migrations that build the schema of the database from scratch, and our databases do not have them yet. Until then a service tests its API with `app.test_client()` and its services with `MagicMock` repositories, and the repositories are not tested. `services/notes` already runs on a real database with its alembic migrations.
