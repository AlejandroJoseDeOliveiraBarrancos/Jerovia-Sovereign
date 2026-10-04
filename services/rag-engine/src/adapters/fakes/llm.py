"""Deterministic ``LLMClient`` fake.

Tests (and the offline eval harness) need to reproduce two situations that are
awkward with a real provider: a specific *wrong* answer, and a failure such as a
timeout or unparseable output. Both are first-class here, so a test can drive the
retry loop and the fail-closed path without touching the network.

Scripting rules, in priority order:

1. entries whose ``match`` substring appears in the prompt are consumed in order;
2. otherwise, the first unconsumed catch-all entry (``match is None``) is used;
3. otherwise the fake raises, because silently returning a plausible answer would
   hide a missing fixture.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from domain.errors import LLMClientError
from ports.llm import LLMRequest, LLMResponse, TokenUsage


@dataclass(frozen=True, slots=True)
class ScriptedResponse:
    """One scripted model outcome.

    Attributes:
        match: substring that must appear in the prompt, or ``None`` for a
            catch-all entry consumed in declaration order.
        content: raw response text. Invalid JSON is allowed on purpose: it
            exercises the retry loop.
        error: when set, the fake raises this instead of responding.
        model_id: model id to report; defaults to the client's fake model id.
        input_tokens, output_tokens: usage to report.
        metadata: free-form annotations recorded on the recorded call.
    """

    match: str | None = None
    content: str = "{}"
    error: Exception | None = None
    model_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class FakeLLMClient:
    """Scripted model client with a recorded call history.

    Attributes:
        name: adapter name.
        model_id: fake model identity reported on every response.
    """

    name = "fake_llm_client"

    def __init__(
        self,
        script: Sequence[ScriptedResponse] = (),
        model_id: str = "fake-model-v1",
    ) -> None:
        self.model_id = model_id
        self.script: list[ScriptedResponse] = list(script)
        self.calls: list[LLMRequest] = []
        self._consumed: set[int] = set()

    @property
    def call_count(self) -> int:
        """Number of calls received, for asserting on retry behaviour."""
        return len(self.calls)

    def reset(self) -> None:
        """Forget recorded calls and re-arm the script from the beginning.

        Test isolation: without this, script state leaks between cases and a
        second run of the same test would see different behaviour.
        """
        self.calls.clear()
        self._consumed.clear()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the next scripted response.

        Args:
            request: the prompt and parameters; recorded verbatim.

        Returns:
            The scripted response, with the requested model id honoured.

        Raises:
            LLMClientError: if the scripted entry requests an error, or if the
                script is exhausted for this prompt.
        """
        self.calls.append(request)
        entry = self._next_entry(request.prompt)
        if entry is None:
            raise LLMClientError(
                f"fake LLM has no scripted response for prompt {request.prompt[:80]!r}"
            )
        if entry.error is not None:
            raise entry.error
        return LLMResponse(
            content=entry.content,
            model_id=request.model_id or entry.model_id or self.model_id,
            usage=TokenUsage(
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
            ),
            raw={"fake": True, **entry.metadata},
        )

    def _next_entry(self, prompt: str) -> ScriptedResponse | None:
        """Consume and return the next entry matching ``prompt``, or ``None``.

        The first pass takes entries whose ``match`` appears in the prompt, the
        second pass falls back to the first catch-all, so declaration order never
        lets an unrelated catch-all shadow a specific script entry.
        """
        for require_match in (True, False):
            for index, entry in enumerate(self.script):
                if index in self._consumed:
                    continue
                is_match = entry.match is not None and entry.match in prompt
                if is_match is not require_match:
                    continue
                self._consumed.add(index)
                return entry
        return None
