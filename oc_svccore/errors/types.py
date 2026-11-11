from oc_svccore.errors.base_error import BaseError


class InvalidDataError(BaseError):
    code = "invalid_data"


class NotFoundError(BaseError):
    code = "not_found"


class ConflictError(BaseError):
    code = "conflict"


class UnauthorizedError(BaseError):
    code = "unauthorized"


class PermissionDeniedError(BaseError):
    code = "forbidden"

    def __init__(self, permission: str):
        super().__init__(data={"permission": permission})
        self.permission = permission


class UpstreamError(BaseError):
    code = "upstream_error"


class UpstreamUnavailableError(UpstreamError):
    code = "upstream_unavailable"
