"""Domain core of the rag-engine.

This package holds pure data types and rules: no framework imports, no I/O, no
network. Everything the pipeline reads or writes is described here so that ports,
adapters and tests all agree on one vocabulary.
"""

from domain.chunks import (
    ChildChunk,
    ChunkKind,
    ChunkSet,
    IndexedChunk,
    ParentChunk,
    StatementType,
)
from domain.documents import (
    BlockKind,
    DocumentSource,
    ParsedBlock,
    ParsedDocument,
    ParsedTable,
    TableCell,
)
from domain.errors import (
    AuditStoreError,
    ChunkerError,
    DocumentParserError,
    EmbedderError,
    ExtractionError,
    LLMClientError,
    PipelineError,
    RetrievalError,
    VectorStoreError,
    Violation,
)
from domain.extraction import (
    Evidence,
    ExtractionResult,
    MetricExtraction,
    Scale,
    Status,
    parse_printed_value,
)
from domain.ids import (
    ChunkId,
    DocId,
    MetricId,
    RunId,
    TableId,
    new_doc_id,
    new_run_id,
)
from domain.retrieval import (
    MetadataFilter,
    Query,
    RetrievalHit,
    SparseVector,
    Vector,
)
from domain.validation import (
    GroundingContext,
    RetrievedContext,
    Severity,
    ValidationFinding,
    ValidationReport,
)

__all__ = [
    "AuditStoreError",
    "BlockKind",
    "ChildChunk",
    "ChunkId",
    "ChunkKind",
    "ChunkSet",
    "ChunkerError",
    "DocId",
    "DocumentParserError",
    "DocumentSource",
    "EmbedderError",
    "Evidence",
    "ExtractionError",
    "ExtractionResult",
    "GroundingContext",
    "IndexedChunk",
    "LLMClientError",
    "MetadataFilter",
    "MetricExtraction",
    "MetricId",
    "ParentChunk",
    "ParsedBlock",
    "ParsedDocument",
    "ParsedTable",
    "PipelineError",
    "Query",
    "RetrievalError",
    "RetrievalHit",
    "RetrievedContext",
    "RunId",
    "Scale",
    "Severity",
    "SparseVector",
    "StatementType",
    "Status",
    "TableCell",
    "TableId",
    "ValidationFinding",
    "ValidationReport",
    "Vector",
    "VectorStoreError",
    "Violation",
    "new_doc_id",
    "new_run_id",
    "parse_printed_value",
]
