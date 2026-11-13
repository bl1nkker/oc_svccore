from oc_svccore.db import DataRepo
from notes.models import Note


class NoteRepo(DataRepo[Note]):
    _type = Note
    _order_by_map = {"id": Note.id, "title": Note.title, "createdAt": Note.created_at}

    def find_by_title(self, title: str) -> Note | None:
        return self.first(self.query().filter(Note.title == title))
