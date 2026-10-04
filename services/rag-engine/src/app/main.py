"""FastAPI composition root.

Two endpoints only for now:

* ``/health`` - liveness: the process is up.
* ``/ready`` - readiness: configuration resolved and components pinned.

Both answer with the pinned versions, because "which model answered this number"
is an operational question as much as an audit one. Secrets are reported as
present/absent, never as values.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from domain.ids import DocId, RunId, new_run_id
from observability.logging import configure_logging, get_logger, run_context
from settings import VERSION, get_settings

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Build the ASGI application.

    Returns:
        A configured FastAPI app. Settings are resolved eagerly so an invalid
        environment fails at startup rather than on the first request.
    """
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    application = FastAPI(
        title="rag-engine",
        version=VERSION,
        summary="Deterministic financial statement extraction",
    )

    @application.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok", "version": VERSION}

    @application.get("/ready", tags=["ops"])
    async def ready() -> JSONResponse:
        """Readiness probe reporting the pinned component versions."""
        body: dict[str, Any] = {
            "status": "ready",
            "environment": settings.environment,
            "pinned": {
                "llm_model_id": settings.llm_model_id,
                "parser": f"{settings.parser_name}@{settings.parser_version}",
                "chunker": f"{settings.chunker_name}@{settings.chunker_version}",
                "prompt_version": settings.prompt_version,
                "embedder_model_id": settings.embedder_model_id,
                "sparse_model_id": settings.sparse_model_id,
            },
            "vector_store_provider": settings.vector_store_provider,
            "secrets_present": {
                "openai_api_key": settings.openai_api_key is not None,
                "postgres_dsn": settings.postgres_dsn is not None,
            },
        }
        pinned_ok = settings.environment not in {"staging", "production"} or (
            settings.parser_version != "unpinned"
            and settings.chunker_version != "unpinned"
            and settings.prompt_version != "unpinned"
        )
        if not pinned_ok:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={**body, "status": "not_ready"},
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content=body)

    @application.middleware("http")
    async def correlate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Stamp ``run_id`` and ``doc_id`` on every request and its log lines."""
        run_id = RunId(request.headers.get("x-run-id") or new_run_id())
        doc_id_header = request.headers.get("x-doc-id")
        with run_context(run_id=run_id, doc_id=DocId(doc_id_header) if doc_id_header else None):
            logger.info(
                "http_request",
                extra={"method": request.method, "path": request.url.path},
            )
            return await call_next(request)

    return application


app = create_app()


def run() -> None:
    """Console-script entrypoint: serve with uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
