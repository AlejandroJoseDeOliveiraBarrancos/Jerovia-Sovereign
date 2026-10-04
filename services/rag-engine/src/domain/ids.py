"""Identifier types.

Identifiers are opaque strings wrapped in ``NewType`` so that a chunk id can never
be passed where a document id is expected. ``new_doc_id``/``new_run_id`` generate
UUID4 values: they are unique, not ordered, and not reproducible across runs,
which is exactly what an audit key needs.
"""

from typing import NewType
from uuid import uuid4

ChunkId = NewType("ChunkId", str)
"""Stable id of a chunk inside one document (``<doc_id>:c:<n>``)."""

DocId = NewType("DocId", str)
"""Stable id of an ingested document, derived from its content checksum."""

MetricId = NewType("MetricId", str)
"""Canonical metric id from the metric ontology (populated in E1-08)."""

RunId = NewType("RunId", str)
"""Id of a single pipeline execution, stamped on every log line and audit record."""

TableId = NewType("TableId", str)
"""Stable id of a parsed table (``<doc_id>:t:<n>``)."""


def new_run_id() -> RunId:
    """Return a fresh run id."""
    return RunId(f"run_{uuid4().hex}")


def new_doc_id(checksum: str) -> DocId:
    """Return a document id derived from the document checksum.

    Deriving the id from the checksum keeps ingestion idempotent: re-uploading the
    same bytes must resolve to the same document.
    """
    if not checksum:
        raise ValueError("checksum must not be empty")
    return DocId(f"doc_{checksum[:32]}")
