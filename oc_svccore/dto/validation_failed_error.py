from pydantic import ValidationError

from oc_svccore.errors import InvalidDataError


class ValidationFailedError(InvalidDataError):
    code = "validation"

    @classmethod
    def from_pydantic(cls, e: ValidationError) -> "ValidationFailedError":
        errors = [{"field": _field(err["loc"]), "message": f"_err_msg_{err['type']}"} for err in e.errors()]
        return cls(data={"errors": errors})


def _field(loc: tuple[int | str, ...]) -> str:
    return "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in loc).lstrip(".")
