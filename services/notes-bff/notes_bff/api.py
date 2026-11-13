from flask import Blueprint

from oc_svccore import web
from oc_svccore.dto import ListQuery
from notes_bff.notes_client import NotesClient


def build_blueprint(notes: NotesClient) -> Blueprint:
    bp = Blueprint("notes", __name__, url_prefix="/api/v1/notes")

    @bp.get("")
    @web.query(ListQuery)
    def list_notes(query: ListQuery):
        return notes.list_notes(query.model_dump(mode="json", exclude_none=True))

    return bp
