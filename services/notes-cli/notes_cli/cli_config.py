from pydantic import BaseModel

from oc_svccore.config import getter


class NotesCliConfig(BaseModel):
    notes_url: str
    username: str
    password: str


get_notes_cli_config = getter(NotesCliConfig, lambda get: dict(
    notes_url=get("NOTES_URL"),
    username=get("NOTES_CLI_ACCOUNT__USERNAME"),
    password=get("NOTES_CLI_ACCOUNT__PASSWORD"),
))
