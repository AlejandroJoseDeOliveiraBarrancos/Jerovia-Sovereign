"""Deterministic ``DocumentParser`` fake.

A real parser is the highest-risk component in the project (WP2, U=5), so the
tests around everything downstream must not depend on one. This fake reads a
registered :class:`ParsedDocument` when the caller has one, and otherwise treats
the file as plain UTF-8 text split into paragraphs on blank lines. That is enough
to exercise ingestion, chunking, retrieval and extraction end to end, offline.

It still honours the port contract where that is observable: a page count that
disagrees with the source is a ``DocumentParserError``, and an unreadable file is
an error rather than an empty document.
"""

from pathlib import Path

from domain.documents import (
    BlockKind,
    DocumentSource,
    ParsedBlock,
    ParsedDocument,
)
from domain.errors import DocumentParserError


class FakeDocumentParser:
    """Text-backed parser that never invents structure it cannot see."""

    name = "fake_document_parser"

    def __init__(
        self,
        documents: dict[str, ParsedDocument] | None = None,
        parser_version: str = "fake-parser-v1",
        healthy: bool = True,
    ) -> None:
        self.parser_version = parser_version
        self.healthy = healthy
        self.documents = dict(documents or {})
        self.calls: list[DocumentSource] = []

    def register(self, document: ParsedDocument) -> None:
        """Register a parsed document to return for its ``doc_id``.

        Args:
            document: the fixture to hand back verbatim, so a test can pin an
                exact table grid, unit scale and page layout.
        """
        self.documents[document.doc_id] = document

    async def parse(self, source: DocumentSource) -> ParsedDocument:
        """Return the registered fixture, or parse the file as plain text.

        Args:
            source: pointer to the raw bytes plus the expected page count.

        Returns:
            A parsed document whose ``parser_version`` is this fake's version.

        Raises:
            DocumentParserError: if the file is missing or unreadable, or if the
                resulting page count disagrees with ``pages_expected``.
        """
        self.calls.append(source)
        registered = self.documents.get(source.doc_id)
        if registered is not None:
            self._check_page_count(registered.page_count, source)
            return ParsedDocument(
                doc_id=registered.doc_id,
                checksum=registered.checksum,
                page_count=registered.page_count,
                blocks=registered.blocks,
                tables=registered.tables,
                parser_version=self.parser_version,
                metadata_filter=registered.metadata_filter,
                source_name=registered.source_name,
            )

        blocks = self._read_text(source.path)
        parsed = ParsedDocument(
            doc_id=source.doc_id,
            checksum=source.checksum,
            page_count=1,
            blocks=blocks,
            parser_version=self.parser_version,
            source_name=source.path.name,
        )
        self._check_page_count(parsed.page_count, source)
        return parsed

    async def health_check(self) -> bool:
        """Return the configured health flag."""
        return self.healthy

    @staticmethod
    def _read_text(path: Path) -> tuple[ParsedBlock, ...]:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocumentParserError(f"cannot read {path}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise DocumentParserError(f"{path} is not decodable text: {exc}") from exc

        blocks: list[ParsedBlock] = []
        for paragraph in (chunk.strip() for chunk in raw.split("\n\n")):
            if not paragraph:
                continue
            kind = BlockKind.HEADING if paragraph.startswith("#") else BlockKind.PARAGRAPH
            blocks.append(
                ParsedBlock(
                    page=1,
                    kind=kind,
                    text=paragraph.lstrip("# ").strip(),
                    level=1 if kind is BlockKind.HEADING else None,
                )
            )
        if not blocks:
            raise DocumentParserError(
                f"{path} produced no text; refusing to return an empty document"
            )
        return tuple(blocks)

    @staticmethod
    def _check_page_count(page_count: int, source: DocumentSource) -> None:
        expected = source.pages_expected
        if expected is not None and expected != page_count:
            raise DocumentParserError(
                f"page count mismatch for {source.doc_id}: expected {expected}, parsed {page_count}"
            )
