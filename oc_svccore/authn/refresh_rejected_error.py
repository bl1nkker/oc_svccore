from oc_svccore.errors import UnauthorizedError


class RefreshRejectedError(UnauthorizedError):
    code = "session_ended"
