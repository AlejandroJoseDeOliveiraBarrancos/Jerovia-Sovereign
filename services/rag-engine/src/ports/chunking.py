"""``Chunker`` port: parsed document to indexed parent/child chunks."""

from typing import Protocol, runtime_checkable

from domain.chunks import ChunkSet
from domain.documents import ParsedDocument


@runtime_checkable
class Chunker(Protocol):
    """Split a parsed document into matchable children and contextual parents.

    Contract:
        * Follow document structure. Tables are atomic as parents and split into row
          children; prose is split on sentence boundaries. Never chunk by a fixed
          character count, which would cut a table mid-row and detach a number from
          its header.
        * Build each child's ``context_prefix`` deterministically from parse output
          (company, filing type, fiscal period, statement, unit scale, column
          labels). No model-generated enrichment: enrichment that can hallucinate is
          enrichment that corrupts retrieval.
        * Stitch tables that continue across pages into one parent, and keep the
          repeated header of the continuation.
        * Emit chunks in a stable order and record ``ChunkSet.chunker_version``; the
          same document and version must yield the same chunk ids, otherwise
          re-indexing invalidates every recorded retrieval.

    Failure modes:
        * :class:`~domain.errors.ChunkerError` - a table cannot be split
          into rows coherently (empty grid, no header row to attribute columns to).
        * :class:`~domain.errors.ChunkerError` - a child references a
          parent that was not emitted, which would make provenance unrecoverable.
        * Never drops a block silently: content that cannot be chunked must be
          surfaced, because an unindexed cash-flow row looks exactly like a
          retrieval miss.

    Determinism: fully deterministic given the same parse output and version.
    """

    name: str

    def chunk(self, document: ParsedDocument) -> ChunkSet:
        """Produce the parent/child chunk set for ``document``.

        Args:
            document: parse output carrying pages, bboxes and table grids.

        Returns:
            Chunk set with every parent referenced by exactly one or more children.

        Raises:
            ChunkerError: if a table or block cannot be chunked coherently.
        """
        ...
