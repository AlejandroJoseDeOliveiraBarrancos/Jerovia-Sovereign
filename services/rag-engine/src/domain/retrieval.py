"""Retrieval vocabulary: vectors, queries, filters and hits.

Vectors are plain tuples of floats. They are *not* pydantic models and carry no
provider semantics, so a fake embedder and a real one are interchangeable. Money
never appears in this module: a vector is not a number that can be audited.
"""

from dataclasses import dataclass, field

from domain.ids import ChunkId, DocId

type Vector = tuple[float, ...]
"""A dense embedding. L2-normalised by contract so cosine similarity is a dot product."""

type SparseVector = dict[str, float]
"""A sparse embedding: term -> weight, with non-zero weights only."""


@dataclass(frozen=True, slots=True)
class MetadataFilter:
    """A conjunctive metadata filter applied *before* similarity search.

    Filtering by document, company and period first eliminates whole classes of
    wrong answers (right metric, wrong year) at negligible cost, so it runs before
    scoring rather than after.
    """

    equality: tuple[tuple[str, str], ...] = ()
    """``(field, value)`` pairs that must all match exactly."""

    def matches(self, payload: dict[str, object]) -> bool:
        """Return whether ``payload`` satisfies every equality constraint."""
        return all(payload.get(field) == value for field, value in self.equality)


@dataclass(frozen=True, slots=True)
class Query:
    """A resolved extraction question.

    ``text`` is the retrieval query; ``metric`` is the canonical metric id and
    ``period_label`` the period the answer must describe. Filters are already
    resolved by query understanding (E5), so retrieval never parses free text.
    """

    text: str
    doc_id: DocId | None = None
    metric: str | None = None
    period_label: str | None = None
    metadata_filter: MetadataFilter = MetadataFilter()


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One scored chunk returned by a store.

    ``rank`` is the 1-based position in the fused ranking; ``dense_score`` and
    ``sparse_score`` are the per-retriever scores that produced the rank. They are
    logged for diagnosis, but they are **not** a confidence (see ADR-001: an
    uncalibrated score must never be presented as confidence).
    """

    chunk_id: ChunkId
    score: float
    rank: int
    dense_score: float | None = None
    sparse_score: float | None = None
    payload: dict[str, object] = field(default_factory=dict)
