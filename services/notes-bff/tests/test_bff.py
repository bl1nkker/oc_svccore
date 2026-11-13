from pathlib import Path

from oc_svccore.testing import assert_spec

SPEC = Path(__file__).resolve().parent.parent / "spec" / "openapi.yaml"


def test_without_a_session_notes_and_me_are_401(bff):
    client = bff.test_client()
    for path in ("/api/v1/notes", "/auth/me"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json["message"] == "_err_msg_no_session"


def test_signed_in_user_sees_notes_read_by_the_service_account(user, notes):
    assert user.get("/auth/me").json["username"] == "someone"
    r = user.get("/api/v1/notes")
    assert r.status_code == 200
    assert r.json["seenBy"] == "svc-notes-bff"
    assert notes.calls == [{"page": "1", "pageSize": "50"}]


def test_page_and_sort_reach_notes(user, notes):
    user.get("/api/v1/notes?page=2&pageSize=10&sort=-createdAt&other=x")
    assert notes.calls == [{"page": "2", "pageSize": "10", "sort": "-createdAt"}]


def test_page_size_over_the_limit_stops_in_the_bff(user, notes):
    r = user.get("/api/v1/notes?pageSize=501")
    assert r.status_code == 400
    assert r.json["data"]["errors"][0]["field"] == "pageSize"
    assert notes.calls == []


def test_a_wrong_sort_comes_back_as_notes_answered(user):
    r = user.get("/api/v1/notes?sort=author")
    assert r.status_code == 400
    assert (r.json["code"], r.json["message"]) == ("invalid_sort", "_err_msg_invalid_sort")
    assert r.json["data"] == {"sort": "author", "allowed": ["createdAt", "id", "title"]}


def test_notes_down_is_503(make_bff, signed_in):
    r = signed_in(make_bff("http://127.0.0.1:1")).get("/api/v1/notes")
    assert r.status_code == 503
    assert r.json["message"] == "_err_msg_notes_unavailable"


def test_notes_refusing_the_bff_is_502(make_bff, signed_in, foreign_notes):
    r = signed_in(make_bff(foreign_notes.url)).get("/api/v1/notes")
    assert r.status_code == 502
    assert (r.json["message"], r.json["data"]) == ("_err_msg_notes_rejected", {"status": 401})


def test_health_checks_notes(make_bff, notes):
    assert make_bff(notes.url).test_client().get("/health").json == {"status": "ok", "checks": {"notes": "ok"}}
    r = make_bff("http://127.0.0.1:1").test_client().get("/health")
    assert r.status_code == 503 and r.json["checks"] == {"notes": "fail"}


def test_routes_match_the_spec(bff):
    assert_spec(bff, SPEC)
