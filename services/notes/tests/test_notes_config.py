import pytest

from notes.notes_config import get_notes_config


@pytest.fixture(autouse=True)
def fresh_config(monkeypatch):
    monkeypatch.delenv("SPRING_CLOUD_CONFIG_URI", raising=False)
    monkeypatch.delenv("VAULT_URL", raising=False)
    get_notes_config.cache_clear()
    yield
    get_notes_config.cache_clear()


def test_writers_come_from_a_comma_list(monkeypatch):
    monkeypatch.setenv("NOTES_WRITERS", "alice,,bob")
    assert get_notes_config().writers == {"alice", "bob"}


def test_nobody_writes_when_writers_are_not_set(monkeypatch):
    monkeypatch.delenv("NOTES_WRITERS", raising=False)
    assert get_notes_config().writers == frozenset()
