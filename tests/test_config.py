from waybackmachine.config import get_database_url


def test_get_database_url_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    url = get_database_url()
    assert url.startswith("sqlite:///")
    assert "wayback.sqlite" in url or "wayback" in url


def test_get_database_url_respects_env(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "/var/data/forum.sqlite")
    url = get_database_url()
    assert "sqlite:////var/data/forum.sqlite" == url


def test_get_database_url_memory(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", ":memory:")
    url = get_database_url()
    assert url == "sqlite:///:memory:"
