"""Validation vocabulary.

Validators are deterministic, side-effect-free functions packaged behind the
:class:`~ports.validation.Validator` port. They answer two questions:

* is this candidate answer **grounded** in the text the model was given?
* do the numbers cohere with each other and with the declared units?

A validator never repairs a value and never asks the model anything. It returns
findings; the pipeline decides whether findings are fatal, which is what keeps
"verification" separable from "generation".
"""

from dataclasses import dataclass, field
from enum import StrEnum

from domain.ids import ChunkId, TableId


class Severity(StrEnum):
    """How a finding affects the verdict.

    ``ERROR`` blocks acceptance and forces a retry or a typed refusal.
    ``WARNING`` is recorded (for the confidence signals and the eval slices) but
    does not by itself block a value, because some checks are heuristic.
    """

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One detected problem.

    ``code`` values come from the error taxonomy and are part of the eval report
    contract, for example ``QUOTE_NOT_FOUND``, ``NUMBER_NOT_IN_QUOTE``,
    ``PAGE_MISMATCH``, ``SCALE_MISMATCH``, ``PERIOD_MISMATCH``, ``SIGN_CONVENTION``,
    ``IMPLAUSIBLE_MAGNITUDE``, ``MISSING_EVIDENCE``.
    """

    code: str
    severity: Severity
    message: str
    field: str | None = None

    @property
    def is_fatal(self) -> bool:
        """Whether this finding blocks acceptance of the candidate."""
        return self.severity is Severity.ERROR


@dataclass(frozen=True, slots=True)
class RetrievedContext:
    """One assembled parent chunk that was shown to the model."""

    chunk_id: ChunkId
    text: str
    pages: tuple[int, ...]
    table_id: TableId | None = None
    unit_scale: str | None = None


@dataclass(frozen=True, slots=True)
class GroundingContext:
    """Everything needed to verify a candidate against the source.

    ``page_texts`` maps page number to the text of that page, which is what the
    quote-containment check needs. A quote that cannot be found here is a
    hallucination signal, regardless of how plausible the number looks.
    """

    contexts: tuple[RetrievedContext, ...] = ()
    page_texts: dict[int, str] = field(default_factory=dict)
    expected_scale: str | None = None
    expected_period_label: str | None = None

    @property
    def all_text(self) -> str:
        """Concatenated text of every retrieved context, for substring checks."""
        return "\n".join(context.text for context in self.contexts)

    def text_for_page(self, page: int) -> str | None:
        """Return the text of ``page`` from any source available, or ``None``."""
        if page in self.page_texts:
            return self.page_texts[page]
        for context in self.contexts:
            if page in context.pages:
                return context.text
        return None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The verdict for one candidate: all findings plus the fatal subset."""

    findings: tuple[ValidationFinding, ...] = ()

    @property
    def errors(self) -> tuple[ValidationFinding, ...]:
        """Findings that block acceptance."""
        return tuple(finding for finding in self.findings if finding.is_fatal)

    @property
    def ok(self) -> bool:
        """Whether the candidate may be accepted."""
        return not self.errors
