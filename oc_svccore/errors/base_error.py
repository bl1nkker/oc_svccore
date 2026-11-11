from typing import Any


class BaseError(Exception):
    code = "error"
    message: str | None = None

    def __init__(self, message: str | None = None, *, code: str | None = None, data: dict[str, Any] | None = None):
        self.code = code or self.code
        self.message = message or self.message or f"_err_msg_{self.code.lower()}"
        self.data = data or {}
        super().__init__(self.message)
