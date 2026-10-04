"""Extraction output types.

This is the heart of the deterministic envelope (ADR-001). The model is an
*untrusted parser*: it may only report what a source page literally prints,
together with a verbatim quote, and it is allowed to say "I cannot find it".

Three design rules are encoded here rather than in a prompt:

1. **Absence is representable.** ``status`` is ``found | not_found | ambiguous`` and
   value fields are optional, so refusing is a valid answer. A schema that cannot
   express absence manufactures hallucinations.
2. **The model never computes.** It returns ``printed_value`` exactly as printed
   (plus ``scale``/``currency``); :func:`parse_printed_value` turns that string into
   a ``Decimal`` in code, so the digits can be matched against the source.
3. **Evidence precedes value.** Field order is evidence first, because a model
   generates left to right: the value that follows a quote is conditioned on text
   rather than on a guess.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.errors import Violation
from domain.ids import MetricId, TableId

SCALE_EXPONENT: dict[str, int] = {
    "units": 0,
    "thousands": 3,
    "millions": 6,
    "billions": 9,
}


class Status(StrEnum):
    """Outcome of one metric lookup."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class Scale(StrEnum):
    """Multiplicative scale declared by the table header ("in millions")."""

    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


class Evidence(BaseModel):
    """Where a value was found. Required whenever ``status`` is ``found``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int = Field(ge=1, description="1-based page number in the source document.")
    quote: str = Field(min_length=1, description="Verbatim snippet containing printed_value.")
    table_id: TableId | None = Field(default=None, description="Table the quote came from.")
    row_ref: int | None = Field(default=None, description="Grid row of the value's cell.")
    column_index: int | None = Field(default=None, description="Grid column of the value's cell.")


class MetricExtraction(BaseModel):
    """One metric, as reported by the model and checked by the validators.

    ``printed_value`` is the string as it appears in the document, e.g.
    ``"(10,959)"``. The normalised :class:`decimal.Decimal` is *not* a model field;
    it is computed by :func:`parse_printed_value`.
    """

    model_config = ConfigDict(extra="forbid")

    metric: MetricId = Field(description="Canonical metric id from the metric ontology.")
    status: Status
    evidence: Evidence | None = None
    printed_value: str | None = None
    scale: Scale | None = None
    currency: str | None = None
    period_label: str | None = None
    reason: str | None = None

    @field_validator("printed_value")
    @classmethod
    def _printed_value_must_be_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("printed_value must not be blank")
        return value

    @model_validator(mode="after")
    def _status_implies_evidence(self) -> Self:
        if self.status is Status.FOUND:
            missing = [
                name
                for name, value in (
                    ("evidence", self.evidence),
                    ("printed_value", self.printed_value),
                    ("scale", self.scale),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"status=found requires {', '.join(missing)}")
        if self.status is not Status.FOUND and not self.reason:
            raise ValueError(f"status={self.status} requires a reason")
        return self


class ExtractionResult(BaseModel):
    """The full answer for one query: a status plus per-metric extractions.

    ``failed_closed`` is set when at least one requested metric could not be
    verified; the response is still returned (with the reason) instead of raising,
    so a caller can render a typed refusal rather than a stack trace.
    """

    model_config = ConfigDict(extra="forbid")

    metric: MetricId
    status: Status
    extraction: MetricExtraction | None = None
    value: Decimal | None = Field(
        default=None, description="Deterministically normalised value; never computed by the model."
    )
    confidence_label: str | None = Field(
        default=None, description="Calibrated label (high/medium/low); None until E7 calibration."
    )
    confidence_signals: dict[str, bool] = Field(default_factory=dict)
    violations: tuple[Violation, ...] = ()
    period_label: str | None = None
    requested_period: str | None = None
    retrieved_at: date | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("use Decimal, never float, for monetary values")
        return value


def parse_printed_value(printed_value: str, scale: Scale) -> Decimal:
    """Convert a printed financial value into a scaled :class:`~decimal.Decimal`.

    Rules, all deterministic and independently property-tested:

    * surrounding currency symbols and whitespace are stripped;
    * thousands separators (``,``), spaces and apostrophes are removed;
    * parentheses mean negative: ``"(1,234.5)"`` -> ``Decimal("-1234.5")``;
    * an em dash means zero *or* not applicable, which are different answers, so a
      bare dash is rejected: the caller must decide which one it is;
    * a percent sign is **not** stripped. This function parses money; a ratio is a
      different metric with a different contract;
    * ``scale`` multiplies by its power of ten after the sign is applied.

    Raises:
        ValueError: if the string is not a parseable number. Silent coercion of a
            malformed value would defeat the 0% numerical-accuracy KPI.
    """
    text = printed_value.strip()
    if text in {"\u2014", "\u2013", "-", "--"}:
        raise ValueError(
            f"printed value {printed_value!r} is a dash: zero and not-applicable are "
            "different answers, so the caller must decide which one it is"
        )
    for token in ("$", "\u20ac", "\u00a3", "\u00a5", " ", "\u00a0"):
        text = text.replace(token, "")
    text = text.replace(",", "").replace("'", "")
    if text.startswith("+"):
        text = text[1:]

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    if not text or not (text[0].isdigit() or text[0] == "." or text[0] == "-"):
        raise ValueError(f"printed value {printed_value!r} is not numeric")

    try:
        magnitude = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the checks above
        raise ValueError(f"printed value {printed_value!r} is not numeric") from exc

    if negative:
        magnitude = -magnitude
    return magnitude * (Decimal(10) ** SCALE_EXPONENT[scale.value])
