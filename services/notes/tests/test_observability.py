import pytest
from prometheus_client import REGISTRY

from oc_svccore import web
from oc_svccore.db import Database
from notes.main import create_app

OUTCOMES = ("success", "failed", "rejected")


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def create(client, headers, title):
    return client.post("/api/v1/notes", json={"title": title}, headers=headers)


@pytest.fixture
def down_client(issuer):
    database = Database("postgresql+psycopg2://notes:notes@127.0.0.1:1/notes")
    return create_app(database, web.bearer(issuer.verifier()), frozenset()).test_client()


def test_liveness_and_readiness_answer_ok_when_database_is_down(down_client):
    for path in ("/health/liveness", "/health/readiness"):
        r = down_client.get(path)
        assert r.status_code == 200, path
        assert r.json == {"status": "ok"}


def test_deep_health_reports_failed_database_by_name_only(down_client):
    r = down_client.get("/health")
    assert r.status_code == 503
    assert r.json == {"status": "unavailable", "checks": {"postgres": "fail"}}


def test_deep_health_is_ok_when_database_is_up(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json == {"status": "ok", "checks": {"postgres": "ok"}}


def test_dependency_up_shows_failed_database_on_scrape_without_health_call(down_client):
    body = down_client.get("/metrics").text
    assert 'notes_dependency_up{dependency="postgres"} 0.0' in body


def test_metrics_expose_runtime_infrastructure_and_business_metrics(client):
    body = client.get("/metrics").text
    expected = [
        "process_cpu_seconds_total",
        'notes_build_info{git_sha="unknown",version="unknown"} 1.0',
        "notes_http_requests_total",
        "notes_http_request_duration_seconds",
        'notes_dependency_up{dependency="postgres"} 1.0',
        "notes_dependency_request_duration_seconds",
        "notes_create_note_duration_seconds",
        "notes_create_note_last_success_timestamp_seconds",
        *(f'notes_create_note_total{{outcome="{o}"}}' for o in OUTCOMES),
    ]
    for name in expected:
        assert name in body, name


def test_unknown_path_is_counted_as_unmatched_without_the_raw_path(client):
    client.get("/no-such-path-xyz")
    body = client.get("/metrics").text
    assert 'route="unmatched"' in body
    assert "no-such-path-xyz" not in body


def test_route_label_is_the_route_template(client, reader):
    client.get("/api/v1/notes/424242", headers=reader)
    body = client.get("/metrics").text
    assert 'route="/api/v1/notes/{note_id}"' in body
    assert "424242" not in body


def test_create_note_counts_success_and_rejected_attempts(client, writer, reader):
    before = {o: sample("notes_create_note_total", outcome=o) for o in OUTCOMES}
    create(client, writer, "counted")
    create(client, writer, "counted")
    create(client, reader, "by-reader")
    create(client, writer, "")
    after = {o: sample("notes_create_note_total", outcome=o) for o in OUTCOMES}
    assert after["success"] - before["success"] == 1
    assert after["rejected"] - before["rejected"] == 3
    assert after["failed"] == before["failed"]
    assert sample("notes_create_note_last_success_timestamp_seconds") > 0
