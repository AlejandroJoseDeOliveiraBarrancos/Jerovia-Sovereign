"""Deterministic in-memory ``VectorStore`` fake.

It implements exactly the ranking semantics the eval harness needs to compare
dense-only, sparse-only and fused retrieval against one index:

* metadata filtering happens **before** scoring;
* fusion is Reciprocal Rank Fusion over the two ranked lists, using the ``rrf_k``
  from the request;
* ties break on ``chunk_id``, so two runs over the same index return the same
  ranking in the same order.

The sparse score is a deterministic overlap score, not BM25. It exists to make
fusion testable, not to be evaluated as a retrieval baseline.
"""

import math
from collections.abc import Sequence

from domain.chunks import IndexedChunk
from domain.errors import VectorStoreError
from domain.ids import ChunkId, DocId
from domain.retrieval import RetrievalHit, SparseVector, Vector
from ports.vector_store import FusionMode, SearchRequest

_MISSING = object()


class FakeVectorStore:
    """In-memory index with exact, deterministic search."""

    name = "fake_vector_store"

    def __init__(self, dimension: int | None = None, collection: str = "fake_chunks") -> None:
        self.collection = collection
        self.dimension = dimension
        self._chunks: dict[ChunkId, IndexedChunk] = {}

    @property
    def chunk_ids(self) -> tuple[ChunkId, ...]:
        """Indexed chunk ids in insertion order."""
        return tuple(self._chunks)

    @staticmethod
    def payload_for(chunk: IndexedChunk) -> dict[str, object]:
        """Return the chunk's effective payload: declared filter plus free payload."""
        return {**dict(chunk.metadata_filter.equality), **chunk.payload}

    async def ensure_collection(self, dimension: int, sparse: bool) -> None:
        """Adopt the expected dimension; ``sparse`` is accepted for parity.

        Args:
            dimension: dense vector dimension the collection expects.
            sparse: whether a sparse index is required; unused by the fake.
        """
        if self.dimension is not None and self.dimension != dimension:
            raise VectorStoreError(
                f"collection {self.collection!r} already expects dimension {self.dimension}"
            )
        self.dimension = dimension

    async def upsert_chunks(self, chunks: Sequence[IndexedChunk]) -> int:
        """Insert or replace chunks by id.

        Args:
            chunks: chunks with dense vectors and filterable payloads.

        Returns:
            The number of chunks written.

        Raises:
            VectorStoreError: on an empty batch, a dimension mismatch, a missing
                ``doc_id`` payload field, or a chunk without a dense vector.
        """
        if not chunks:
            raise VectorStoreError("upsert_chunks requires at least one chunk")
        for chunk in chunks:
            if not chunk.dense:
                raise VectorStoreError(f"chunk {chunk.chunk_id} has no dense vector")
            if self.dimension is None:
                self.dimension = len(chunk.dense)
            elif len(chunk.dense) != self.dimension:
                raise VectorStoreError(
                    f"chunk {chunk.chunk_id} has dimension {len(chunk.dense)}, "
                    f"expected {self.dimension}"
                )
            if self.payload_for(chunk).get("doc_id", _MISSING) is _MISSING:
                raise VectorStoreError(
                    f"chunk {chunk.chunk_id} has no doc_id in its payload; "
                    "a document could not be purged from the index"
                )
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
        return len(chunks)

    async def search(self, request: SearchRequest) -> list[RetrievalHit]:
        """Score the filtered candidates and return the fused ranking.

        Args:
            request: vectors, filter, ``k``, candidate depth and fusion mode.

        Returns:
            At most ``k`` hits ordered best first, ranked from 1, carrying the
            per-retriever scores that produced the order.

        Raises:
            VectorStoreError: if the collection was never initialised.
        """
        if self.dimension is None:
            raise VectorStoreError(f"collection {self.collection!r} was never initialised")

        candidates = [
            chunk
            for chunk in self._chunks.values()
            if request.metadata_filter.matches(self.payload_for(chunk))
        ]
        dense_scores = {chunk.chunk_id: _dot(request.dense, chunk.dense) for chunk in candidates}
        sparse_scores: dict[ChunkId, float] = {}
        if request.sparse is not None:
            sparse_scores = {
                chunk.chunk_id: _overlap(request.sparse, chunk.sparse or {}) for chunk in candidates
            }

        if request.fusion is FusionMode.RRF:
            ordered = _fuse((dense_scores, sparse_scores), request.rrf_k, request.k)
        elif request.fusion is FusionMode.DENSE_ONLY:
            ordered = _order(dense_scores, request.k)
        else:
            ordered = _order(sparse_scores, request.k)

        payloads = {chunk.chunk_id: self.payload_for(chunk) for chunk in candidates}
        return [
            RetrievalHit(
                chunk_id=chunk_id,
                score=score,
                rank=rank,
                dense_score=dense_scores.get(chunk_id),
                sparse_score=sparse_scores.get(chunk_id),
                payload=payloads[chunk_id],
            )
            for rank, (chunk_id, score) in enumerate(ordered, start=1)
        ]

    async def delete_document(self, doc_id: DocId) -> int:
        """Remove every chunk whose payload declares ``doc_id``.

        Args:
            doc_id: the document to purge.

        Returns:
            The number of removed chunks.
        """
        doomed = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if self.payload_for(chunk).get("doc_id") == doc_id
        ]
        for chunk_id in doomed:
            del self._chunks[chunk_id]
        return len(doomed)

    async def count(self, doc_id: DocId | None = None) -> int:
        """Count indexed chunks, optionally for one document.

        Args:
            doc_id: restrict the count to this document, or ``None`` for all.

        Returns:
            The number of indexed chunks.
        """
        if doc_id is None:
            return len(self._chunks)
        return sum(
            1 for chunk in self._chunks.values() if self.payload_for(chunk).get("doc_id") == doc_id
        )


def _dot(left: Vector, right: Vector) -> float:
    """Cosine similarity of two equal-length vectors (both normalised)."""
    return sum(a * b for a, b in zip(left, right, strict=True))


def _overlap(query: SparseVector | None, document: SparseVector) -> float:
    """Deterministic sparse overlap score, cosine-like in ``[0, 1]``."""
    if not query:
        return 0.0
    shared = sum(weight * document[term] for term, weight in query.items() if term in document)
    if shared == 0.0:
        return 0.0
    query_norm = math.sqrt(sum(weight * weight for weight in query.values()))
    document_norm = math.sqrt(sum(weight * weight for weight in document.values()))
    return shared / (query_norm * document_norm)


def _order(scores: dict[ChunkId, float], k: int) -> list[tuple[ChunkId, float]]:
    """Order by descending score, breaking ties on chunk id.

    Non-positive scores are dropped: a chunk with no lexical overlap, or one whose
    dense similarity is negative, is not a match and must not consume a slot of ``k``.
    """
    matched = [
        (chunk_id, score)
        for chunk_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score > 0.0
    ]
    return matched[:k]


def _fuse(
    score_lists: Sequence[dict[ChunkId, float]], rrf_k: int, k: int
) -> list[tuple[ChunkId, float]]:
    """Fuse ranked score maps with ``1 / (rrf_k + rank)`` and keep the top ``k``.

    Only non-zero scores contribute a rank, so a chunk one retriever did not match
    gets no credit for an arbitrary bottom-of-list position.
    """
    fused: dict[ChunkId, float] = {}
    for scores in score_lists:
        for rank, (chunk_id, _score) in enumerate(_order(scores, len(scores)), start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:k]
