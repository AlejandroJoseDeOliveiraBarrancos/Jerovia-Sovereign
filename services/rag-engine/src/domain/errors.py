"""Typed error hierarchy for the pipeline.

Every port failure is one of these types. The taxonomy is deliberately shallow:
callers branch on the *kind* of failure (retry, refuse, or fail the job), not on
the vendor that produced it. Adapters translate provider exceptions into these.

Failure policy (see ADR-001):

* a port must not return a partial or best-effort result for a correctness-critical
  step; it must raise;
* ``Violation`` is the one exception: it carries *detected* bad data (a grounding
  failure, a schema violation) as a value so the pipeline can record the reason and
  fail closed with a typed refusal.
"""

from dataclasses import dataclass


class PipelineError(Exception):
    """Base class for every error raised by this service."""


class DocumentParserError(PipelineError):
    """A document could not be read into structured elements."""


class ChunkerError(PipelineError):
    """A parsed document could not be split into chunks."""


class EmbedderError(PipelineError):
    """Text could not be embedded (provider error, dimension mismatch, empty input)."""


class VectorStoreError(PipelineError):
    """A vector store read or write failed."""


class LLMClientError(PipelineError):
    """The model call failed (transport, timeout, rate limit, unparseable output)."""


class ExtractionError(PipelineError):
    """A model response could not be coerced into the extraction schema."""


class AuditStoreError(PipelineError):
    """An audit record could not be written or read back."""


class RetrievalError(PipelineError):
    """Retrieval could not be served (no candidates, filter rejected, store down)."""


@dataclass(frozen=True, slots=True)
class Violation:
    """A detected defect in a candidate result, carried as a value.

    ``code`` is a stable machine-readable identifier from the error taxonomy
    (``QUOTE_NOT_FOUND``, ``NUMBER_NOT_IN_QUOTE``, ``SCALE_MISMATCH``, ...). Codes
    are part of the eval report contract, so they must not be reworded casually.
    """

    code: str
    message: str
    field: str | None = None
