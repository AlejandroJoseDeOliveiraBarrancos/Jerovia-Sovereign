"""Tests for the domain core: the extraction envelope and the money parser.

These are the cheapest tests in the repository and the most valuable, because
``parse_printed_value`` is a pure function that turns printed text into money. A
decimal shift here is invisible downstream and fatal to the 0% accuracy KPI.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from domain.chunks import ChildChunk, ParentChunk
from domain.extraction import (
    Evidence,
    ExtractionResult,
    MetricExtraction,
    Scale,
    Status,
    parse_printed_value,
)
from domain.ids import ChunkId, DocId
from domain.retrieval import MetadataFilter
from domain.validation import GroundingContext, RetrievedContext, Severity

QUOTE = "Purchases of property and equipment (10,959) (11,085) (10,708)"


def found_extraction(**overrides: object) -> MetricExtraction:
    """Build a valid ``found`` candidate, optionally with field overrides."""
    payload: dict[str, object] = {
        "metric": "capex",
        "status": Status.FOUND,
        "evidence": Evidence(page=57, quote=QUOTE, table_id="doc_1:t:3"),
        "printed_value": "(10,959)",
        "scale": Scale.MILLIONS,
        "currency": "USD",
        "period_label": "Fiscal year ended Sep 28, 2024",
    }
    payload.update(overrides)
    return MetricExtraction(**payload)


class TestMetricExtractionSchema:
    """The schema must make the invalid states unrepresentable."""

    def test_found_requires_evidence(self) -> None:
        with pytest.raises(ValidationError, match="requires evidence"):
            found_extraction(evidence=None)

    def test_found_requires_printed_value_and_scale(self) -> None:
        with pytest.raises(ValidationError, match="printed_value"):
            found_extraction(printed_value=None)

    def test_refusal_requires_a_reason(self) -> None:
        with pytest.raises(ValidationError, match="requires a reason"):
            MetricExtraction(metric="capex", status=Status.NOT_FOUND)

    def test_refusal_is_a_valid_answer(self) -> None:
        result = MetricExtraction(
            metric="capex", status=Status.NOT_FOUND, reason="no investing section in this filing"
        )
        assert result.status is Status.NOT_FOUND
        assert result.printed_value is None

    def test_unknown_fields_are_rejected_so_hallucinated_keys_surface(self) -> None:
        candidate: dict[str, object] = {
            "metric": "capex",
            "status": Status.NOT_FOUND,
            "reason": "absent",
            "confidence": 0.99,
        }
        with pytest.raises(ValidationError):
            MetricExtraction.model_validate(candidate)

    def test_blank_printed_value_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be blank"):
            found_extraction(printed_value="   ")

    def test_evidence_page_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Evidence(page=0, quote=QUOTE)


class TestExtractionResult:
    """Money never arrives as a float."""

    def test_float_values_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="never float"):
            ExtractionResult(metric="capex", status=Status.FOUND, value=125.0)

    def test_decimal_values_are_accepted(self) -> None:
        result = ExtractionResult(metric="capex", status=Status.FOUND, value=Decimal("-125"))
        assert result.value == Decimal("-125")

    def test_failed_closed_results_keep_their_violations(self) -> None:
        from domain.errors import Violation

        result = ExtractionResult(
            metric="capex",
            status=Status.NOT_FOUND,
            violations=(Violation(code="QUOTE_NOT_FOUND", message="no quote in context"),),
        )
        assert [violation.code for violation in result.violations] == ["QUOTE_NOT_FOUND"]


class TestParsePrintedValue:
    """Printed text to Decimal: parentheses, separators, signs and scales."""

    @pytest.mark.parametrize(
        ("printed", "scale", "expected"),
        [
            ("(10,959)", Scale.MILLIONS, Decimal("-10959000000")),
            ("4,521.3", Scale.MILLIONS, Decimal("4521300000.0")),
            ("$ 1,250", Scale.THOUSANDS, Decimal("1250000")),
            ("1,234.5", Scale.UNITS, Decimal("1234.5")),
            ("(1.5)", Scale.BILLIONS, Decimal("-1500000000")),
            ("+2,000", Scale.THOUSANDS, Decimal("2000000")),
            ("1250", Scale.UNITS, Decimal("1250")),
            ("(1,234.5)", Scale.MILLIONS, Decimal("-1234500000.0")),
        ],
    )
    def test_known_shapes(self, printed: str, scale: Scale, expected: Decimal) -> None:
        assert parse_printed_value(printed, scale) == expected

    def test_result_is_exact_not_floating_point(self) -> None:
        value = parse_printed_value("0.1", Scale.BILLIONS)
        assert isinstance(value, Decimal)
        assert str(value) == "100000000.0"

    @pytest.mark.parametrize("printed", ["", "   ", "—", "-", "n/a", "abc", "(1,23a)", "$"])
    def test_unparseable_values_raise_instead_of_coercing(self, printed: str) -> None:
        with pytest.raises(ValueError):
            parse_printed_value(printed, Scale.MILLIONS)

    def test_dash_is_rejected_because_zero_and_na_differ(self) -> None:
        with pytest.raises(ValueError, match="dash"):
            parse_printed_value("—", Scale.MILLIONS)


class TestChunkTypes:
    """Contextualisation is deterministic and part of the indexed text."""

    def test_child_indexable_text_prepends_the_context(self) -> None:
        child = ChildChunk(
            chunk_id=ChunkId("c1"),
            doc_id=DocId("doc_1"),
            parent_id=ChunkId("p1"),
            text="Purchases of property and equipment: (10,959)",
            page=57,
            context_prefix="[10-K | FY2024 | in millions USD | columns: FY2024, FY2023]",
        )
        assert child.indexable_text.startswith("[10-K | FY2024")
        assert child.indexable_text.endswith("(10,959)")

    def test_chunk_without_prefix_indexes_its_own_text(self) -> None:
        parent = ParentChunk(
            chunk_id=ChunkId("p1"), doc_id=DocId("doc_1"), text="Body", pages=(57,)
        )
        assert parent.indexable_text == "Body"

    def test_metadata_filter_defaults_to_matching_everything(self) -> None:
        child = ChildChunk(
            chunk_id=ChunkId("c1"),
            doc_id=DocId("doc_1"),
            parent_id=ChunkId("p1"),
            text="row",
            page=1,
        )
        assert child.metadata_filter.matches({})
        assert not MetadataFilter(equality=(("doc_id", "doc_2"),)).matches({"doc_id": "doc_1"})


class TestGroundingContext:
    """The context object is what quote-containment is checked against."""

    def test_page_text_lookup_prefers_explicit_page_text(self) -> None:
        context = GroundingContext(
            contexts=(RetrievedContext(chunk_id=ChunkId("p1"), text=QUOTE, pages=(57,)),),
            page_texts={57: "the page as parsed"},
        )
        assert context.text_for_page(57) == "the page as parsed"

    def test_page_text_falls_back_to_retrieved_contexts(self) -> None:
        context = GroundingContext(
            contexts=(RetrievedContext(chunk_id=ChunkId("p1"), text=QUOTE, pages=(57,)),)
        )
        assert context.text_for_page(57) == QUOTE

    def test_unknown_page_returns_none_rather_than_guessing(self) -> None:
        assert GroundingContext().text_for_page(99) is None

    def test_reports_separate_fatal_from_warning_findings(self) -> None:
        from domain.validation import ValidationFinding, ValidationReport

        report = ValidationReport(
            findings=(
                ValidationFinding(code="QUOTE_NOT_FOUND", severity=Severity.ERROR, message="x"),
                ValidationFinding(
                    code="IMPLAUSIBLE_MAGNITUDE", severity=Severity.WARNING, message="y"
                ),
            )
        )
        assert report.ok is False
        assert [finding.code for finding in report.errors] == ["QUOTE_NOT_FOUND"]
