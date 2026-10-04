"""Parsed-document types (the "Silver" layer of the ingestion medallion).

The shapes here are the *contract* between the parser adapter (E2) and everything
downstream. Two rules are load-bearing for the 0% numerical-accuracy KPI:

1. **Provenance is captured at parse time.** Page numbers and bounding boxes cannot
   be reconstructed later; if the parser drops them the audit trail is gone.
2. **Table structure is data, not text.** A table keeps its cell grid, column
   header paths, unit scale and footnotes, so validation can check that a number
   came from the requested period column rather than trusting a quote alone.

Markdown cannot express ``colspan``/``rowspan``, so it is a derived view for
prompting only; the grid below is the canonical form.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from domain.ids import DocId, TableId
from domain.retrieval import MetadataFilter


class BlockKind(StrEnum):
    """Coarse classification of a parsed block, used for metadata filtering."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FOOTNOTE = "footnote"
    CAPTION = "caption"


@dataclass(frozen=True, slots=True)
class TableCell:
    """One cell of a parsed table.

    ``text`` is the cell exactly as printed (``"(10,959)"``, ``"—"``, ``"n/a"``);
    normalization is a later, deterministic step. ``row``/``col`` are zero-based
    grid coordinates and ``row_span``/``col_span`` express merged cells, so a
    multi-level header survives parsing.
    """

    row: int
    col: int
    text: str
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False


@dataclass(frozen=True, slots=True)
class ParsedTable:
    """A table recognised as a grid, with its header paths and footnotes.

    ``header_paths[col]`` is the flattened header of that column (for example
    ``"Year Ended December 31 | 2024"``), which is what lets a validator confirm
    that an extracted number belongs to the requested period.
    """

    table_id: TableId
    page: int
    cells: tuple[TableCell, ...]
    header_paths: tuple[str, ...] = ()
    unit_scale: str | None = None
    currency: str | None = None
    caption: str | None = None
    footnotes: tuple[str, ...] = ()
    continues_from_previous_page: bool = False
    continues_on_next_page: bool = False

    @property
    def n_rows(self) -> int:
        """Number of grid rows, counting the header rows."""
        return max((cell.row for cell in self.cells), default=-1) + 1

    def row_text(self, row: int, separator: str = " | ") -> str:
        """Render one row left to right, preserving the printed cell text."""
        cells = sorted((cell for cell in self.cells if cell.row == row), key=lambda cell: cell.col)
        return separator.join(cell.text for cell in cells)


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """A non-table block (heading, paragraph, footnote) with its provenance."""

    page: int
    kind: BlockKind
    text: str
    bbox: tuple[float, float, float, float] | None = None
    section_path: tuple[str, ...] = ()
    level: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """The full parse result for one document."""

    doc_id: DocId
    checksum: str
    page_count: int
    blocks: tuple[ParsedBlock, ...]
    tables: tuple[ParsedTable, ...] = ()
    parser_version: str = "unpinned"
    metadata_filter: MetadataFilter = field(default_factory=MetadataFilter)
    source_name: str | None = None

    def page_text(self, page: int) -> str:
        """Concatenate the text of one page, for quote-containment checks.

        Table cells are included because the quote a model returns may come from a
        cell rather than from a prose block.
        """
        parts = [block.text for block in self.blocks if block.page == page]
        for table in self.tables:
            if table.page != page:
                continue
            parts.append(table.caption or "")
            for row in range(table.n_rows):
                parts.append(table.row_text(row))
            parts.extend(table.footnotes)
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """A pointer to raw document bytes plus what is known about them.

    ``path`` is only a convenience for local files; a production adapter may resolve
    the same object from object storage. ``pages_expected`` is an assertion the
    parser must satisfy: a page count mismatch is a parse failure, not a warning.
    """

    doc_id: DocId
    path: Path
    checksum: str
    pages_expected: int | None = None
    mime_type: str = "application/pdf"
