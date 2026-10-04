"""``DocumentParser`` port: raw filing bytes to structured elements."""

from typing import Protocol, runtime_checkable

from domain.documents import DocumentSource, ParsedDocument


@runtime_checkable
class DocumentParser(Protocol):
    """Turn a raw document into a :class:`ParsedDocument`.

    Contract:
        * Consume the bytes referenced by ``DocumentSource.path`` and return every
          page, block and table with page numbers and bounding boxes populated.
          Provenance is captured here because it cannot be reconstructed later.
        * Preserve table structure as a cell grid: merged cells via
          ``row_span``/``col_span``, multi-level headers flattened into
          ``ParsedTable.header_paths``, plus the table's unit scale and footnotes.
        * Never truncate text. A dropped page or cell is a correctness failure, not
          a formatting choice.
        * Report ``ParsedDocument.parser_version`` truthfully; it is part of the
          audit record and must change whenever output changes.

    Failure modes:
        * :class:`~domain.errors.DocumentParserError` - unreadable or
          corrupt file, unsupported format, or a page count that disagrees with
          ``DocumentSource.pages_expected``.
        * :class:`~domain.errors.DocumentParserError` - a page whose
          table structure could not be recognised with acceptable confidence. The
          parser flags it (parse QA) instead of guessing; see the risk section of
          the project spec.
        * Never returns a partially parsed document as if it were complete, and
          never substitutes invented text for unreadable text.

    Determinism: the same bytes with the same ``parser_version`` must produce an
    equivalent document, so a re-run of Bronze to Gold is safe.
    """

    name: str

    async def parse(self, source: DocumentSource) -> ParsedDocument:
        """Parse ``source`` into structured elements.

        Args:
            source: pointer to the raw bytes plus the expected page count.

        Returns:
            The parsed document, including tables with header paths and units.

        Raises:
            DocumentParserError: on any unrecoverable parse problem, including a
                page-count mismatch.
        """
        ...

    async def health_check(self) -> bool:
        """Return whether the parser is usable (dependencies present, model loaded).

        Used by the service health endpoint so a container that starts but cannot
        parse is reported as unhealthy instead of failing on the first filing.
        """
        ...
