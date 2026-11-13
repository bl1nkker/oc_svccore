from flask import Blueprint

from notes import note_dto
from notes.repo import NoteRepo
from notes.service import NoteService
from oc_svccore import metrics, web
from oc_svccore.db import Database
from oc_svccore.dto import ListQuery, Page
from oc_svccore.errors import PermissionDeniedError

CREATE_NOTE = metrics.operation("create_note")
GET_NOTE = metrics.operation("get_note")
LIST_NOTES = metrics.operation("list_notes")


def build_blueprint(database: Database, writers: frozenset[str]) -> Blueprint:
    bp = Blueprint("notes", __name__, url_prefix="/api/v1/notes")

    def service() -> NoteService:
        return NoteService(NoteRepo(web.request_session(database)))

    @bp.get("")
    @LIST_NOTES
    @web.query(ListQuery)
    def list_notes(query: ListQuery):
        page = service().list(query.page, query.page_size, query.sort)
        return Page[note_dto.Read].model_validate(page).model_dump(mode="json")

    @bp.get("/<int:note_id>")
    @GET_NOTE
    def get_note(note_id: int):
        return note_dto.Read.model_validate(service().get(note_id)).model_dump(
            mode="json"
        )

    @bp.post("")
    @CREATE_NOTE
    @web.body(note_dto.Create)
    def create_note(body: note_dto.Create):
        author = web.current_principal().username
        if author not in writers:
            raise PermissionDeniedError("notes.write")
        note = service().create(body.title, author)
        return note_dto.Read.model_validate(note).model_dump(mode="json"), 201

    return bp
