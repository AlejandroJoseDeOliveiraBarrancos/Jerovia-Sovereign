"""``VectorStore`` port: indexed chunks and hybrid search.

The store owns persistence and scoring, not relevance policy. Fusion mode is a
field of the request rather than a hard-wired behaviour, because dense-only,
sparse-only and hybrid must be measurable against the same index (README Part 8):
the eval harness cannot compare variants it cannot switch between.

Ingestion is offline, so every write here happens in the Bronze to Gold job and
never on the query path.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from domain.chunks import IndexedChunk
from domain.ids import DocId
from domain.retrieval import MetadataFilter, RetrievalHit, SparseVector, Vector


class FusionMode(StrEnum):
    """How multiple ranked lists are combined.

    ``RRF`` is the default (Cormack et al., 2009). ``DENSE_ONLY`` and
    ``SPARSE_ONLY`` exist for evaluation, not for production paths: they are the
    baselines the hybrid result must beat by a measured margin.
    """

    RRF = "rrf"
    DENSE_ONLY = "dense_only"
    SPARSE_ONLY = "sparse_only"


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """One search, fully resolved by query understanding.

    A request carries vectors and a filter, never raw user text: any remaining
    interpretation belongs upstream, so a bug here cannot silently change scope.
    """

    dense: Vector
    sparse: SparseVector | None = None
    metadata_filter: MetadataFilter = field(default_factory=MetadataFilter)
    k: int = 10
    candidates: int = 50
    fusion: FusionMode = FusionMode.RRF
    rrf_k: int = 60

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError("k must be positive")
        if self.fusion in {FusionMode.SPARSE_ONLY, FusionMode.RRF} and self.sparse is None:
            raise ValueError(f"fusion={self.fusion.value} requires a sparse vector")
        if self.candidates < self.k:
            raise ValueError("candidates must be >= k (RRF re-ranking needs headroom)")


@runtime_checkable
class VectorStore(Protocol):
    """Store chunk vectors and serve filtered hybrid search.

    Contract:
        * Upsert is idempotent per ``(doc_id, index_identity)`` where the identity
          includes the embedder and sparse model ids, so re-indexing a document
          after a model change cannot mix embedding spaces in one collection.
        * Apply ``SearchRequest.metadata_filter`` *before* scoring.
        * Return at most ``k`` hits, ordered by descending score, with 1-based
          ``rank`` and the per-retriever scores that produced the fused order.
        * Ties are broken deterministically (by ``chunk_id``); two runs over the
          same index must return the same ranking in the same order.

    Failure modes:
        * :class:`~domain.errors.VectorStoreError` - store unreachable,
          collection missing, dimension mismatch on upsert.
        * :class:`~domain.errors.VectorStoreError` - a rejected filter
          (unknown field). A silently ignored filter returns wrong-document results,
          so it must be an error.
        * Must not raise for an empty result set: zero hits is a valid answer and
          the pipeline turns it into a ``not_found`` refusal.

    Determinism: reads are deterministic. ``score`` is a rank-derived relevance
    signal, **not** a probability of correctness, and must not be labelled
    "confidence" anywhere downstream (ADR-001).
    """

    name: str

    async def ensure_collection(self, dimension: int, sparse: bool) -> None:
        """Create the collection and its indexes if they do not exist.

        Args:
            dimension: dense vector dimension.
            sparse: whether a sparse vector index is required.

        Raises:
            VectorStoreError: if the collection cannot be created or validated.
        """
        ...

    async def upsert_chunks(self, chunks: Sequence[IndexedChunk]) -> int:
        """Insert or replace chunks and their vectors.

        Args:
            chunks: chunks with dense (and optionally sparse) vectors and the
                metadata payload used for filtering.

        Returns:
            The number of chunks written.

        Raises:
            VectorStoreError: on dimension mismatch, payload rejection or a store
                error.
        """
        ...

    async def search(self, request: SearchRequest) -> list[RetrievalHit]:
        """Run one filtered hybrid search.

        Args:
            request: vectors, filter, k and fusion mode.

        Returns:
            At most ``k`` hits, best first, each carrying rank and per-retriever
            scores. An empty list means "no candidate matched", not an error.

        Raises:
            VectorStoreError: on store failure or a rejected filter.
        """
        ...

    async def delete_document(self, doc_id: DocId) -> int:
        """Remove every chunk of a document (re-ingest, or an incorrect parse).

        Args:
            doc_id: the document to purge.

        Returns:
            The number of chunks removed.

        Raises:
            VectorStoreError: on store failure.
        """
        ...

    async def count(self, doc_id: DocId | None = None) -> int:
        """Count indexed chunks, optionally for one document only.

        Args:
            doc_id: restrict the count to this document, or ``None`` for all.

        Returns:
            The number of indexed chunks.

        Raises:
            VectorStoreError: on store failure.
        """
        ...
