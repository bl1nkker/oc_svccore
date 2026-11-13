from pydantic import BaseModel

from oc_svccore.config import getter


class NotesConfig(BaseModel):
    writers: frozenset[str] = frozenset()


get_notes_config = getter(
    NotesConfig,
    lambda get: dict(writers={name for name in (get("NOTES_WRITERS") or "").split(",") if name}),
)
