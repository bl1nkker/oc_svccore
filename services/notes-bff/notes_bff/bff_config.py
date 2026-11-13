from pydantic import BaseModel

from oc_svccore.config import getter


class NotesBffConfig(BaseModel):
    notes_url: str
    username: str
    password: str


get_notes_bff_config = getter(NotesBffConfig, lambda get: dict(
    notes_url=get("NOTES_URL"),
    username=get("NOTES_BFF_ACCOUNT__USERNAME"),
    password=get("NOTES_BFF_ACCOUNT__PASSWORD"),
))
