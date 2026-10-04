"""Tests for the delivery layer: health, readiness and correlation headers."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from observability.logging import clear_context
from settings import VERSION


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client over a freshly composed application."""
    with TestClient(create_app()) as test_client:
        yield test_client
    clear_context()


def test_health_reports_the_running_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": VERSION}


def test_ready_reports_pinned_component_versions(client: TestClient) -> None:
    body = client.get("/ready").json()
    assert body["status"] == "ready"
    assert body["pinned"]["prompt_version"]
    assert body["pinned"]["chunker"].startswith("parent-child-structural@v")


def test_ready_never_returns_secret_values(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.json()["secrets_present"] == {"openai_api_key": False, "postgres_dsn": False}
    assert "sk-" not in response.text


def test_run_id_header_reaches_the_log_context(client: TestClient) -> None:
    response = client.get("/health", headers={"x-run-id": "run_header", "x-doc-id": "doc_header"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


class TestProductionGuards:
    """A deployment without pinned versions must not come up at all."""

    def test_production_without_pins_fails_at_startup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pydantic import ValidationError

        monkeypatch.setenv("RAG_ENVIRONMENT", "production")
        with pytest.raises(ValidationError, match="unpinned component versions"):
            create_app()

    def test_fully_pinned_production_comes_up_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_ENVIRONMENT", "production")
        monkeypatch.setenv("RAG_PARSER_VERSION", "2.1.0")
        monkeypatch.setenv("RAG_CHUNKER_VERSION", "v1")
        monkeypatch.setenv("RAG_PROMPT_VERSION", "v3")
        with TestClient(create_app()) as production_client:
            body = production_client.get("/ready").json()
        assert body["status"] == "ready"
        assert body["pinned"]["prompt_version"] == "v3"
