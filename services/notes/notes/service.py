from oc_svccore.db import Pagination
from notes.errors import NoteNotFoundError, NoteTitleTakenError
from notes.models import Note
from notes.repo import NoteRepo


class NoteService:
    def __init__(self, repo: NoteRepo):
        self._repo = repo

    def list(self, page: int, page_size: int, sort: str | None) -> Pagination[Note]:
        return self._repo.list_paged(page, page_size, self._repo.order_by(sort))

    def get(self, note_id: int) -> Note:
        note = self._repo.get_by_db_id(note_id)
        if note is None:
            raise NoteNotFoundError()
        return note

    def create(self, title: str, author: str) -> Note:
        with self._repo.session():
            if self._repo.find_by_title(title):
                raise NoteTitleTakenError()
            return self._repo.save_or_update(Note(title=title, author=author))
