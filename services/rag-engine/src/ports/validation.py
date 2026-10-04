"""``Validator`` port: deterministic checks on a candidate extraction.

Validators are the project's main weapon against hallucination. Heuristic: a
number the model states that cannot be found in the source text cannot pass quote
containment, which turns "hallucination" from a fuzzy risk into a countable,
testable event.

Every check in this port family must be a pure function of its inputs: same
extraction plus same context must yield the same findings, on every machine and
in every process. A validator that calls a model is not a validator.
"""

from typing import Protocol, runtime_checkable

from domain.extraction import MetricExtraction
from domain.validation import GroundingContext, ValidationReport


@runtime_checkable
class Validator(Protocol):
    """Check one candidate extraction against the context it was given.

    Contract:
        * Pure and side-effect free: no I/O, no clock, no randomness, no model
          calls. Findings must be reproducible for a recorded fixture.
        * Report every problem it finds rather than stopping at the first, so one
          retry can address several defects at once.
        * Never modify or "fix" the candidate. A validator that repairs a value
          would launder a hallucination into an apparently verified number.
        * Use stable ``code`` values from the error taxonomy; the eval slices are
          keyed on them.

    Failure modes:
        * Returns findings instead of raising for bad data. It raises only if it
          cannot run at all (a context that does not correspond to the candidate),
          because then the check would silently pass everything.
        * Absence of a value is not a failure: a ``not_found`` or ``ambiguous``
          candidate is valid output, so validators only inspect candidates whose
          ``status`` is ``found``.

    Determinism: guaranteed. This is the load-bearing property of the port.
    """

    name: str

    def validate(self, extraction: MetricExtraction, context: GroundingContext) -> ValidationReport:
        """Return all findings for one candidate.

        Args:
            extraction: the model's candidate answer, still untrusted.
            context: the retrieved context, page texts, expected scale and expected
                period the candidate is supposed to be grounded in.

        Returns:
            A report whose ``ok`` is true only when no fatal finding was raised.

        Raises:
            Exception: only if the check cannot be evaluated at all; never for a
                merely wrong candidate.
        """
        ...
