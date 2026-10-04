"""``LLMClient`` port: the one probabilistic component in the system.

The adapter is the only place allowed to know about a model vendor, temperature
or SDK. The application sees "send this request, get JSON back", which is what
makes the model swappable and the tests offline.

The port is intentionally *not* schema-aware beyond receiving a JSON schema. The
retry-with-validation-error loop lives in the application: it must apply to the
project's own grounding checks, not only to pydantic parsing inside a vendor
library.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from domain.errors import LLMClientError


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """One model call.

    ``json_schema`` is a JSON Schema object; the adapter maps it to the provider's
    structured-output feature when available, so shape errors are prevented rather
    than retried. ``prompt_hash`` is computed by the caller from the exact prompt
    text and stored in the audit record, so a result can be replayed.
    """

    system: str
    prompt: str
    json_schema: dict[str, Any] | None = None
    temperature: float = 0.0
    max_output_tokens: int = 1024
    model_id: str | None = None
    prompt_hash: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token accounting for one call, used for the latency and cost budget."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """A model response as untrusted data.

    ``content`` is the raw text. Parsing, schema validation and grounding checks
    happen downstream and are allowed to reject it; a provider-level guarantee
    that ``content`` is valid JSON is a convenience, never a correctness claim.
    """

    content: str
    model_id: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        """Parse ``content`` as a JSON object.

        Returns:
            The decoded object.

        Raises:
            LLMClientError: if the content is not a JSON object. Adapters of
                structured-output providers still raise here: a model that emits
                prose instead of JSON is an expected failure mode, not a bug.
        """
        try:
            decoded = json.loads(self.content)
        except ValueError as exc:
            raise LLMClientError(f"model response is not valid JSON: {exc}") from exc
        if not isinstance(decoded, dict):
            raise LLMClientError("model response JSON must be an object")
        return decoded


@runtime_checkable
class LLMClient(Protocol):
    """Send a request to a model and return untrusted text.

    Contract:
        * Return the response as data. The client must not repair, round, rescale
          or reformat a value on the model's behalf, and must not retry silently in
          a way that hides the attempt count: each attempt is one ``LLMResponse``.
        * Honour ``json_schema`` with the provider's constrained decoding when
          available, and report the model id actually used.
        * Record ``usage`` so the latency budget can attribute time to tokens.
        * Use the pinned model id from settings unless the request overrides it,
          so an audit record can never claim a model that was not called.

    Failure modes:
        * :class:`~domain.errors.LLMClientError` - transport error,
          timeout, rate limit, refusal, or content that is not JSON.
        * :class:`~domain.errors.LLMClientError` - a response truncated
          before the closing brace. The pipeline treats it as a retryable schema
          failure, because it usually means the output budget was too small.
        * Must not raise on semantically wrong content: wrong numbers are handled
          by validators, not by the transport layer.

    Determinism: none. This is the only stage that is allowed to vary between
    runs; the envelope around it is what makes the system reproducible.
    """

    name: str

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Run one model call.

        Args:
            request: prompt, optional JSON schema and sampling parameters.

        Returns:
            The raw response plus usage accounting.

        Raises:
            LLMClientError: on any transport, provider or JSON failure.
        """
        ...
