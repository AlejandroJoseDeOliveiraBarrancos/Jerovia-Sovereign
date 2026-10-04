"""Tests for structured logging and context propagation (E0-06)."""

import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from domain.ids import DocId, RunId
from observability.logging import (
    ContextFilter,
    JsonFormatter,
    bind_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
    new_context,
    run_context,
)


@pytest.fixture
def recorder() -> Iterator[list[logging.LogRecord]]:
    """Attach an in-memory handler to the service logger and yield the records."""
    logger = logging.getLogger("rag_engine")
    clear_context()
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _ListHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        clear_context()


class TestContext:
    """Every line must carry the run id and, once known, the document id."""

    def test_run_and_document_ids_are_stamped_on_every_line(self, recorder: Any) -> None:
        logger = get_logger("rag_engine.test")
        with run_context(run_id=RunId("run_abc"), doc_id=DocId("doc_xyz")):
            logger.info("parse complete", extra={"pages": 42})
            logger.info("retrieval complete")

        payloads = [json.loads(JsonFormatter().format(record)) for record in recorder]
        assert [payload["run_id"] for payload in payloads] == ["run_abc", "run_abc"]
        assert [payload["doc_id"] for payload in payloads] == ["doc_xyz", "doc_xyz"]
        assert payloads[0]["pages"] == 42

    def test_document_id_is_bound_after_the_first_log_line(self, recorder: Any) -> None:
        logger = get_logger("rag_engine.test")
        with run_context(run_id=RunId("run_abc")):
            logger.info("ingest started")
            bind_context(doc_id=DocId("doc_late"))
            logger.info("parsed")

        first, second = [json.loads(JsonFormatter().format(r)) for r in recorder]
        assert "doc_id" not in first
        assert second["doc_id"] == "doc_late"

    def test_context_is_restored_after_the_block(self, recorder: Any) -> None:
        with run_context(run_id=RunId("run_outer")):
            with run_context(run_id=RunId("run_inner")):
                assert get_context()["run_id"] == "run_inner"
            assert get_context()["run_id"] == "run_outer"
        assert get_context() == {}

    async def test_context_is_isolated_between_concurrent_runs(self) -> None:
        seen: dict[str, str] = {}

        async def worker(name: str) -> None:
            with run_context(run_id=RunId(name)):
                await asyncio.sleep(0)
                seen[name] = get_context()["run_id"]

        await asyncio.gather(worker("run_1"), worker("run_2"))
        assert seen == {"run_1": "run_1", "run_2": "run_2"}

    def test_new_context_generates_a_run_id(self) -> None:
        context = new_context()
        assert context["run_id"].startswith("run_")
        assert new_context()["run_id"] != context["run_id"]

    def test_get_context_returns_a_copy(self) -> None:
        with run_context(run_id=RunId("run_abc")):
            snapshot: dict[str, str] = dict(get_context())
            snapshot["run_id"] = "tampered"
            assert get_context()["run_id"] == "run_abc"


class TestFormatter:
    """The output must be one JSON object per line, always with the core fields."""

    def test_core_fields_are_always_present(self, recorder: Any) -> None:
        get_logger("rag_engine.test").warning("slow retrieval")
        payload = json.loads(JsonFormatter().format(recorder[0]))
        assert payload["level"] == "WARNING"
        assert payload["logger"] == "rag_engine.test"
        assert payload["message"] == "slow retrieval"
        assert "timestamp" in payload

    def test_non_serialisable_extras_are_stringified_not_dropped(self, recorder: Any) -> None:
        get_logger("rag_engine.test").info("chunk", extra={"chunk": {"page_count": 3}})
        payload = json.loads(JsonFormatter().format(recorder[0]))
        assert payload["chunk"] == {"page_count": 3}

    def test_exceptions_are_included(self, recorder: Any) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            get_logger("rag_engine.test").exception("parse failed")
        payload = json.loads(JsonFormatter().format(recorder[0]))
        assert "ValueError: boom" in payload["exception"]

    def test_output_is_a_single_line(self, recorder: Any) -> None:
        get_logger("rag_engine.test").info("multi\nline\nmessage")
        assert "\n" not in JsonFormatter().format(recorder[0])


class TestConfigureLogging:
    """Configuration is idempotent so tests and the server can both call it."""

    def test_repeated_configuration_does_not_duplicate_handlers(self) -> None:
        configure_logging(level="INFO")
        configure_logging(level="INFO")
        assert len(logging.getLogger("rag_engine").handlers) == 1

    def test_human_readable_output_is_available(self, recorder: Any) -> None:
        configure_logging(level="INFO", json_output=False)
        handler = logging.getLogger("rag_engine").handlers[0]
        assert not isinstance(handler.formatter, JsonFormatter)
        configure_logging(level="INFO", json_output=True)
        assert isinstance(logging.getLogger("rag_engine").handlers[0].formatter, JsonFormatter)


class TestLoggerFactory:
    """Child loggers must stay under the service logger to inherit handlers."""

    def test_module_names_map_under_the_service_logger(self) -> None:
        assert get_logger("rag_engine.adapters.fakes.llm").name == "rag_engine.adapters.fakes.llm"
        assert get_logger("rag_engine").name == "rag_engine"
        assert get_logger().name == "rag_engine"
