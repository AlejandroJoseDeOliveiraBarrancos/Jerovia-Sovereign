"""``AuditStore`` port: append-only, replayable records.

An answer nobody can replay is an answer nobody can audit, which in a regulated
context means the number is unusable regardless of whether it was correct.

The record must be enough to re-run the extraction and get the same result:
document and parser version, chunk ids and ranks, prompt hash, model id and
parameters, the raw model output, validator findings and the retry count.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from domain.extraction import ExtractionResult
from domain.ids import DocId, MetricId, RunId
from domain.validation import ValidationFinding


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One immutable, self-contained record of a single metric answer.

    Field choices are audit choices:

    * ``model_id``, ``parser_version`` and ``prompt_hash`` pin *what* produced the
      value, so a replay does not silently use a newer component.
    * ``raw_model_output`` keeps the untrusted text, because a validator verdict is
      only meaningful against the exact response it judged.
    * ``failures`` lists every retry and violation, so a rising retry rate is
      visible as a leading indicator of a broken upstream stage.
    """

    run_id: RunId
    doc_id: DocId
    metric: MetricId
    started_at: datetime
    completed_at: datetime | None = None
    query_text: str | None = None
    requested_period: str | None = None
    chunk_ids: tuple[str, ...] = ()
    ranks: dict[str, int] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    model_id: str | None = None
    model_params: dict[str, Any] = field(default_factory=dict)
    prompt_hash: str | None = None
    parser_version: str | None = None
    chunker_version: str | None = None
    raw_model_output: str | None = None
    result: ExtractionResult | None = None
    value: Decimal | None = None
    findings: tuple[ValidationFinding, ...] = ()
    failures: tuple[str, ...] = ()
    retry_count: int = 0

    def replayable(self) -> bool:
        """Whether this record carries enough state to re-run the extraction.

        A record without a document version, prompt hash or raw output cannot be
        replayed and must not be presented as auditable.
        """
        return bool(
            self.doc_id
            and self.parser_version
            and self.prompt_hash
            and self.raw_model_output is not None
            and self.result is not None
        )


@runtime_checkable
class AuditStore(Protocol):
    """Persist audit records immutably and read them back by key.

    Contract:
        * Append only. There is no update and no delete: a correction is a new
          record. Mutability would make the audit log as unreliable as the data it
          vouches for.
        * ``append`` must not fail silently. A lost audit record is a lost answer
          even when the answer was correct, so the pipeline fails the run.
        * Records are returned exactly as written, including their ordering fields.
        * Writable from the ingestion and query paths, both carrying their
          ``run_id``.

    Failure modes:
        * :class:`~domain.errors.AuditStoreError` - store unreachable, a
          record that violates the schema, or a duplicate ``run_id``/``metric``
          write. Duplicate writes indicate a replayed job and are an error, not an
          upsert.
        * Must not swallow a serialisation failure: an unserialisable record means
          the record schema and the code have diverged.

    Determinism: reads are deterministic and ordered by ``started_at`` then
    ``run_id``.
    """

    name: str

    async def append(self, record: AuditRecord) -> None:
        """Write one record, immutably.

        Args:
            record: the audit record to persist.

        Raises:
            AuditStoreError: if the record cannot be stored or already exists.
        """
        ...

    async def get(self, run_id: RunId, metric: MetricId) -> AuditRecord | None:
        """Return one record, or ``None`` if there is none.

        Args:
            run_id: the run that produced the answer.
            metric: the metric that was requested.

        Returns:
            The stored record, or ``None``.

        Raises:
            AuditStoreError: on store failure.
        """
        ...

    async def list_for_document(self, doc_id: DocId) -> list[AuditRecord]:
        """Return every record for a document, oldest first.

        Args:
            doc_id: the document to inspect.

        Returns:
            Records ordered by ``started_at`` then ``run_id``; empty if none exist.

        Raises:
            AuditStoreError: on store failure.
        """
        ...
