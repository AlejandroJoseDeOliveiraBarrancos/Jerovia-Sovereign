"""Structured JSON logging with request-scoped context.

Every log line carries the run id and document id, so a single answer can be
followed end to end: parse, retrieve, extract, validate, persist. That is the
cheapest observability available and it costs one context variable.

Design notes:

* Context lives in a :class:`~contextvars.ContextVar`, which is safe under asyncio
  and threads: two concurrent runs never see each other's ids.
* The formatter emits one JSON object per line. Machine-readable logs beat prose
  for an audit trail, and a reviewer should be able to ``jq`` a run together.
* Secrets are never logged. Settings are dumped through a redacting helper, and
  the logging module refuses to serialise ``SecretStr`` values.
"""

import json
import logging
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

from domain.ids import DocId, RunId, new_run_id

LOGGER_NAME: Final = "rag_engine"

#: Correlation ids attached to every line emitted inside the context. The default is
#: ``None``, not an empty dict: a mutable ContextVar default is shared by every task.
_context: ContextVar[Mapping[str, str] | None] = ContextVar("rag_engine_log_context", default=None)

#: Attributes present on every ``LogRecord``; anything else is treated as extra.
_RESERVED: Final = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

#: Fields the formatter owns; an extra field never overwrites them.
_CORE_FIELDS: Final = frozenset({"timestamp", "level", "logger", "message"})


def new_context(run_id: RunId | None = None, doc_id: DocId | None = None) -> dict[str, str]:
    """Build a fresh context mapping for a run.

    Args:
        run_id: run identifier; generated when omitted.
        doc_id: document identifier, when known.

    Returns:
        A new mapping; never a shared mutable object.
    """
    context = {"run_id": str(run_id or new_run_id())}
    if doc_id is not None:
        context["doc_id"] = str(doc_id)
    return context


def bind_context(*, run_id: RunId | None = None, doc_id: DocId | None = None, **extra: str) -> None:
    """Merge ids into the current context for the rest of the task.

    Call this at the start of a run, not at every log site: log sites should not
    care which run they belong to.
    """
    updates: dict[str, str] = {}
    if run_id is not None:
        updates["run_id"] = str(run_id)
    if doc_id is not None:
        updates["doc_id"] = str(doc_id)
    updates.update(extra)
    if updates:
        _context.set({**(_context.get() or {}), **updates})


def get_context() -> Mapping[str, str]:
    """Return a copy of the current context mapping."""
    return dict(_context.get() or {})


def clear_context() -> None:
    """Reset the context for the current task.

    Tests call this between cases; production code should prefer
    :func:`run_context`, which restores the previous value on exit.
    """
    _context.set(None)


@contextmanager
def run_context(
    *, run_id: RunId | None = None, doc_id: DocId | None = None, **extra: str
) -> Iterator[Mapping[str, str]]:
    """Scope ids to a block and restore the previous context afterwards.

    Example:
        >>> with run_context(doc_id=DocId("doc_abc")) as ctx:
        ...     logging.getLogger("rag_engine").info("parsed", extra={"pages": 42})
        ...     ctx["doc_id"]
        'doc_abc'
    """
    previous = _context.get()
    bind_context(run_id=run_id, doc_id=doc_id, **extra)
    try:
        yield get_context()
    finally:
        _context.set(previous)


class ContextFilter(logging.Filter):
    """Stamp the bound context onto the record as it is emitted.

    The filter, not the formatter, reads the context variable. A record formatted
    later (a queue handler, a buffered writer, a test that keeps records) must
    still carry the ids of the run that produced it, so the values are frozen onto
    the record at emit time.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Copy the current context onto ``record`` without overwriting extras."""
        for key, value in (_context.get() or {}).items():
            record.__dict__.setdefault(key, value)
        return True


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON line.

    The output always contains ``timestamp``, ``level``, ``logger``, ``message``
    and the bound context. Extra fields are merged at the top level, and
    non-serialisable values are stringified rather than dropped, because a lost
    field in an incident is worse than a stringified one.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Return the JSON representation of ``record``."""
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **dict(_context.get() or {}),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key in _CORE_FIELDS:
                continue
            payload[key] = _safe(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def _safe(value: object) -> object:
    """Return a JSON-safe view of ``value``."""
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, dict | list | tuple):
        return _safe_collection(value)
    return str(value)


def _safe_collection(value: dict[Any, Any] | list[Any] | tuple[Any, ...]) -> object:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    return [_safe(item) for item in value]


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Install the JSON formatter on the service logger.

    Idempotent: calling it twice does not duplicate handlers, so tests and the
    ASGI server can both call it safely.

    Args:
        level: minimum level to emit.
        json_output: emit JSON when true, otherwise a human-readable line.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_output else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(ContextFilter())
    logger.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the service logger.

    Args:
        name: dotted module name, usually ``__name__``.

    Returns:
        A logger under :data:`LOGGER_NAME`, so handler configuration applies.
    """
    if name is None or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    suffix = name.removeprefix("rag_engine.").removeprefix("rag_engine")
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}" if suffix else LOGGER_NAME)
