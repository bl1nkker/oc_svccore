def create(client, headers, title):
    return client.post("/api/v1/notes", json={"title": title}, headers=headers)


def test_create_note_as_writer_returns_201_with_author(client, writer):
    r = create(client, writer, "first")
    assert r.status_code == 201
    assert set(r.json) == {"id", "title", "author", "createdAt"}
    assert r.json["title"] == "first"
    assert r.json["author"] == "writer"


def test_create_note_without_token_returns_401(client):
    r = client.post("/api/v1/notes", json={"title": "first"})
    assert r.status_code == 401
    assert r.json["message"] == "_err_msg_missing_token"


def test_create_note_without_permission_returns_403(client, reader):
    r = create(client, reader, "first")
    assert r.status_code == 403
    assert r.json["data"] == {"permission": "notes.write"}
    assert r.json["message"] == "_err_msg_forbidden"


def test_create_note_with_taken_title_returns_409(client, writer):
    create(client, writer, "dup")
    r = create(client, writer, "dup")
    assert r.status_code == 409
    assert r.json["code"] == "note_title_taken"
    assert r.json["message"] == "_err_msg_note_title_taken"


def test_create_note_with_empty_title_returns_400(client, writer):
    r = create(client, writer, "")
    assert r.status_code == 400
    assert r.json["code"] == "validation"
    assert r.json["message"] == "_err_msg_validation"
    assert r.json["data"] == {"errors": [{"field": "title", "message": "_err_msg_string_too_short"}]}


def test_get_note_returns_it(client, writer, reader):
    created = create(client, writer, "first").json
    r = client.get(f"/api/v1/notes/{created['id']}", headers=reader)
    assert r.status_code == 200
    assert r.json == created


def test_get_missing_note_returns_404(client, reader):
    r = client.get("/api/v1/notes/999999", headers=reader)
    assert r.status_code == 404
    assert r.json["code"] == "note_not_found"
    assert r.json["message"] == "_err_msg_note_not_found"


def test_list_notes_is_paged_and_sorted(client, writer, reader):
    for title in ("b", "c", "a"):
        create(client, writer, title)
    r = client.get("/api/v1/notes", query_string={"sort": "-title", "page": 1, "pageSize": 2}, headers=reader)
    assert r.status_code == 200
    assert (r.json["page"], r.json["pageSize"], r.json["total"]) == (1, 2, 3)
    assert [n["title"] for n in r.json["items"]] == ["c", "b"]


def test_list_notes_rejects_an_unknown_sort_field(client, reader):
    r = client.get("/api/v1/notes", query_string={"sort": "author"}, headers=reader)
    assert r.status_code == 400
    assert r.json["code"] == "invalid_sort"
    assert r.json["data"] == {"sort": "author", "allowed": ["createdAt", "id", "title"]}
