# oc-svccore

Shared base for Python services: errors, authentication, web app factory, logging, metrics, config and database helpers.

## Modules

- [errors](#errors) - base errors and how to define service errors
- [web](#web) - Flask app factory

## errors

`oc_svccore.errors` holds the base errors and the way to define service errors on top of them. It does not depend on HTTP or any framework.

### Base errors

| Class | `code` | Default message | Means |
|---|---|---|---|
| `BaseError` | `error` | `_err_msg_error` | root of all service errors |
| `InvalidDataError` | `invalid_data` | `_err_msg_invalid_data` | the input is wrong |
| `UnauthorizedError` | `unauthorized` | `_err_msg_unauthorized` | the caller is unknown or the credentials are invalid |
| `PermissionDeniedError(permission)` | `forbidden` | `_err_msg_forbidden` | the caller is known but lacks `permission`, also put into `data` |
| `NotFoundError` | `not_found` | `_err_msg_not_found` | the thing does not exist |
| `ConflictError` | `conflict` | `_err_msg_conflict` | a duplicate or a wrong state |
| `UpstreamError` | `upstream_error` | `_err_msg_upstream_error` | a dependency failed |
| `UpstreamUnavailableError` | `upstream_unavailable` | `_err_msg_upstream_unavailable` | a dependency cannot be reached; an `UpstreamError` |

`ConfigServerError` is not a `BaseError`: it is a `RuntimeError` raised at startup when the config server cannot be read.

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

## web

### Error responses

Every error response has the same JSON body, `Content-Type: application/json`:

```json
{
  "message": "_err_msg_title_too_long",
  "code": "invalid_data",
  "data": {"max": 200},
  "traceId": "bf4b57dee6ae2b235d7dc377122a43fa"
}
```

| Field | For |
|---|---|
| `message` | the frontend, translation key of the text |
| `code` | programs and metrics |
| `data` | values for the text and for programs, `{}` when there are none |
| `traceId` | support: the same as `trace.id` in the logs. Present when tracing is set up (`oc_svccore.logging.setup`) or the request came with a `traceparent` header |

The body has no HTTP status and no title: the status is already in the response, and a title adds nothing to `code` and `message`. This is our proposal in place of the RFC 9457 `application/problem+json` format from the R&D API guideline.

The status is looked up by the error's class hierarchy:

| Error | Status |
|---|---|
| `BaseError`, `InvalidDataError` | 400 |
| `UnauthorizedError` | 401 |
| `PermissionDeniedError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `UpstreamError` | 502 |
| `UpstreamUnavailableError` | 503 |

A service changes or adds a status with `create_app(errors_mapping={NoteLockedError: 423})`.

Errors made by the web layer itself:

| Case | Status | `code` | `message` |
|---|---|---|---|
| request body or query fails pydantic validation | 400 | `validation` | `_err_msg_validation` |
| no `Authorization: Bearer` header | 401 | `unauthorized` | `_err_msg_missing_token` |
| token with a bad signature, issuer or expiry | 401 | `unauthorized` | `_err_msg_invalid_token` |
| unknown route | 404 | `not_found` | `_err_msg_not_found` |
| method not allowed on a route | 405 | `method_not_allowed` | `_err_msg_method_not_allowed` |
| Keycloak keys cannot be fetched | 503 | `upstream_unavailable` | `_err_msg_keycloak_unavailable` |
| any other exception | 500 | `internal` | `_err_msg_internal` |

A validation error lists every wrong field in `data.errors`. `field` is the path to the value, `message` is `_err_msg_` plus the pydantic error type:

```json
{
  "message": "_err_msg_validation",
  "code": "validation",
  "data": {"errors": [
    {"field": "title", "message": "_err_msg_string_too_short"},
    {"field": "items[1].title", "message": "_err_msg_missing"}
  ]},
  "traceId": "bf4b57dee6ae2b235d7dc377122a43fa"
}
```

A 500 never shows the exception text. Each 5xx is logged once at ERROR with the stack trace; 4xx are the caller's mistake and are not logged at ERROR.
