"""Shared fixtures.

Every test runs against the deterministic fakes with an isolated environment and
an empty logging context, so no test can depend on a developer's shell, on the
network, or on another test's bound ``run_id``.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from adapters.fakes import (
    FakeDocumentParser,
    FakeEmbedder,
    FakeLLMClient,
    FakeSparseEncoder,
    FakeVectorStore,
)
from domain.chunks import IndexedChunk
from domain.ids import ChunkId, DocId
from domain.retrieval import MetadataFilter
from observability.logging import clear_context
from settings import get_settings

DOC_ID = DocId("doc_test_0001")
OTHER_DOC_ID = DocId("doc_test_0002")
EMBED_DIMENSION = 64


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove ambient ``RAG_*`` variables so settings are the documented defaults."""
    import os

    for name in [key for key in os.environ if key.startswith("RAG_")]:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    clear_context()
    get_settings.cache_clear()


@pytest.fixture
def embedder() -> FakeEmbedder:
    """A 64-dimension deterministic embedder."""
    return FakeEmbedder(dimension=EMBED_DIMENSION)


@pytest.fixture
def sparse() -> FakeSparseEncoder:
    """A deterministic sparse encoder."""
    return FakeSparseEncoder()


@pytest.fixture
def store() -> FakeVectorStore:
    """An empty in-memory store with the dimension already fixed."""
    return FakeVectorStore(dimension=EMBED_DIMENSION)


@pytest.fixture
def llm() -> FakeLLMClient:
    """An LLM client with an empty script (a test must declare its own responses)."""
    return FakeLLMClient()


@pytest.fixture
def parser() -> FakeDocumentParser:
    """A deterministic parser."""
    return FakeDocumentParser()


def make_chunk(
    embedder: FakeEmbedder,
    sparse: FakeSparseEncoder,
    *,
    chunk_id: str,
    text: str,
    doc_id: DocId = DOC_ID,
    statement_type: str = "cash_flow",
) -> IndexedChunk:
    """Build an indexed child chunk for the fake store, synchronously.

    The fakes expose synchronous ``embed``/``encode`` helpers so tests and fixtures
    can build an index without an event loop.

    Args:
        embedder: fake embedder used for the dense vector.
        sparse: fake sparse encoder used for the sparse vector.
        chunk_id: id to store the chunk under.
        text: chunk text (contextualised text in real usage).
        doc_id: document the chunk belongs to.
        statement_type: statement metadata used in filter tests.

    Returns:
        The indexed chunk, with ``doc_id`` and ``statement_type`` in its payload.
    """
    return IndexedChunk(
        chunk_id=ChunkId(chunk_id),
        text=text,
        dense=embedder.embed(text),
        sparse=sparse.encode(text),
        metadata_filter=MetadataFilter(equality=(("doc_id", str(doc_id)),)),
        payload={"statement_type": statement_type, "page": 42},
    )


def write_text_fixture(tmp_path: Path, name: str, body: str) -> Path:
    """Write a plain-text document fixture and return its path."""
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path
