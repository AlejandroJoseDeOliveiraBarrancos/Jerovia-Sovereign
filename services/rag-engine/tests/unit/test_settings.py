"""Tests for typed settings and pinned versions (E0-05)."""

import pytest
from pydantic import SecretStr, ValidationError

from settings import Settings, get_settings, redact


class TestSettingsDefaults:
    """The documented defaults are the contract the Makefile and CI assume."""

    def test_environment_defaults_to_local(self) -> None:
        assert Settings().environment == "local"

    def test_component_versions_are_pinned_by_default(self) -> None:
        settings = Settings()
        assert settings.llm_model_id
        assert settings.chunker_version == "v1"
        assert settings.prompt_version == "v1"
        assert settings.embedder_dimension == 1536

    def test_retrieval_defaults_leave_fusion_headroom(self) -> None:
        settings = Settings()
        assert settings.retrieval_candidates >= settings.retrieval_top_k

    def test_vector_store_starts_on_the_fake_until_e6_decides(self) -> None:
        assert Settings().vector_store_provider == "fake"


class TestSettingsEnvironment:
    """Environment overrides use the ``RAG_`` prefix and are typed."""

    def test_env_overrides_are_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("RAG_RETRIEVAL_TOP_K", "25")
        settings = Settings()
        assert settings.log_level == "DEBUG"
        assert settings.retrieval_top_k == 25

    def test_invalid_value_fails_fast_at_startup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_TOP_K", "not-a-number")
        with pytest.raises(ValidationError):
            Settings()

    def test_unknown_environment_variables_are_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAG_SOMETHING_ELSE", "x")
        assert Settings().environment == "local"

    def test_secrets_are_read_as_secret_strings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_OPENAI_API_KEY", "sk-not-logged")
        settings = Settings()
        assert settings.openai_api_key == SecretStr("sk-not-logged")
        assert "sk-not-logged" not in repr(settings)


class TestSettingsInvariants:
    """Invariants that would otherwise be discovered during an incident."""

    def test_candidates_below_top_k_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_RETRIEVAL_TOP_K", "20")
        monkeypatch.setenv("RAG_RETRIEVAL_CANDIDATES", "10")
        with pytest.raises(ValidationError, match="retrieval_candidates"):
            Settings()

    def test_retry_cap_is_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_LLM_MAX_RETRIES", "9")
        with pytest.raises(ValidationError):
            Settings()

    def test_production_refuses_unpinned_component_versions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAG_ENVIRONMENT", "production")
        with pytest.raises(ValidationError, match="unpinned component versions"):
            Settings()

    def test_production_accepts_fully_pinned_versions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAG_ENVIRONMENT", "staging")
        monkeypatch.setenv("RAG_PARSER_VERSION", "2.1.0")
        monkeypatch.setenv("RAG_CHUNKER_VERSION", "v1")
        monkeypatch.setenv("RAG_PROMPT_VERSION", "v3")
        settings = Settings()
        assert settings.parser_version == "2.1.0"

    def test_settings_are_immutable(self) -> None:
        settings = Settings()
        with pytest.raises(ValidationError):
            settings.llm_model_id = "other"  # type: ignore[misc]


class TestSettingsHelpers:
    """Cached accessor and secret redaction used by logging."""

    def test_get_settings_is_cached(self) -> None:
        assert get_settings() is get_settings()

    def test_redact_never_returns_a_secret_value(self) -> None:
        assert redact(SecretStr("sk-live")) == "***"
        assert redact(None) == "unset"
