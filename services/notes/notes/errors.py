from oc_svccore.errors import ConflictError, NotFoundError


class NoteNotFoundError(NotFoundError):
    code = "note_not_found"


class NoteTitleTakenError(ConflictError):
    code = "note_title_taken"
