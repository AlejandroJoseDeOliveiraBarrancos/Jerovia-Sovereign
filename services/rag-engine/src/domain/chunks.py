"""Chunk types (the "Gold" layer of the ingestion medallion).

Parent-child ("small-to-big") chunking: children are indexed for precise matching,
parents are returned to the model for context. Chunking follows document
structure, never a fixed character count, because a fixed window cuts a table
mid-row and separates numbers from their headers.

Every chunk carries the deterministic context prefix that was indexed with it
(company, filing type, fiscal period, statement, unit scale, column labels). The
prefix is assembled from parse output only, so it cannot be wrong in the way
model-generated enrichment can.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from domain.ids import ChunkId, DocId, TableId
from domain.retrieval import MetadataFilter, SparseVector, Vector


class ChunkKind(StrEnum):
    """Whether a chunk is matched directly or expanded into its parent."""

    PARENT = "parent"
    CHILD = "child"


class StatementType(StrEnum):
    """Statement or note a chunk belongs to; used as a metadata filter."""

    UNKNOWN = "unknown"
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    EQUITY = "equity_statement"
    NOTES = "notes"
    MD_AND_A = "md_and_a"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ParentChunk:
    """A retrievable unit of context returned to the model.

    A table is atomic as a parent: its rows may be children, but the parent text is
    the whole stitched table, including a page-spanning continuation.
    """

    chunk_id: ChunkId
    doc_id: DocId
    text: str
    pages: tuple[int, ...]
    statement_type: StatementType = StatementType.UNKNOWN
    table_id: TableId | None = None
    unit_scale: str | None = None
    currency: str | None = None
    context_prefix: str = ""
    metadata_filter: MetadataFilter = field(default_factory=MetadataFilter)

    @property
    def indexable_text(self) -> str:
        """The text as indexed and as shown to the model: prefix plus body."""
        return f"{self.context_prefix}\n{self.text}".strip() if self.context_prefix else self.text


@dataclass(frozen=True, slots=True)
class ChildChunk:
    """A small matchable unit: one table row or one sentence.

    ``context_prefix`` must be prepended before embedding and BM25 indexing;
    ``row_ref`` lets a validator resolve the number back to its exact cell.
    """

    chunk_id: ChunkId
    doc_id: DocId
    parent_id: ChunkId
    text: str
    page: int
    statement_type: StatementType = StatementType.UNKNOWN
    table_id: TableId | None = None
    row_ref: int | None = None
    context_prefix: str = ""
    metadata_filter: MetadataFilter = field(default_factory=MetadataFilter)

    @property
    def indexable_text(self) -> str:
        """The text as indexed: deterministic context prefix plus the row itself."""
        return f"{self.context_prefix}\n{self.text}".strip() if self.context_prefix else self.text


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    """A chunk plus the vectors computed for it.

    The dense vector is required; the sparse vector is optional so a dense-only
    experiment can run against the same type.
    """

    chunk_id: ChunkId
    text: str
    dense: Vector
    sparse: SparseVector | None = None
    metadata_filter: MetadataFilter = field(default_factory=MetadataFilter)
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChunkSet:
    """All chunks produced from one document, in deterministic order."""

    doc_id: DocId
    chunker_version: str
    parents: tuple[ParentChunk, ...]
    children: tuple[ChildChunk, ...]

    def parent_by_id(self, chunk_id: ChunkId) -> ParentChunk | None:
        """Return the parent with this id, or ``None`` (a dangling child is a bug)."""
        for parent in self.parents:
            if parent.chunk_id == chunk_id:
                return parent
        return None
