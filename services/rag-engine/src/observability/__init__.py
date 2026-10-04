"""Observability: structured logging and, later, tracing hooks.

Tracing (OpenTelemetry / Langfuse, aligned with Project 4) plugs in next to the
JSON logs; the ``run_id`` recorded here is the join key between the two.
"""

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

__all__ = [
    "ContextFilter",
    "JsonFormatter",
    "bind_context",
    "clear_context",
    "configure_logging",
    "get_context",
    "get_logger",
    "new_context",
    "run_context",
]
