"""Adapters: concrete and fake implementations of the ports.

Two groups, and the distinction is deliberate:

* ``adapters.fakes`` - deterministic, dependency-free test doubles. They are part
  of the shipped package, not of the test tree, so the eval harness (E1) and the
  tracer bullet can run the whole pipeline with no network, no API key and no
  Docker. Their determinism is a project requirement: a golden-set number that
  moves because a test double got random is a number nobody trusts.
* real adapters (parser E2, store E4, LLM E8) are added next to the fakes; the
  application never learns which one it received.
"""

from adapters.fakes import (
    FakeDocumentParser,
    FakeEmbedder,
    FakeLLMClient,
    FakeSparseEncoder,
    FakeVectorStore,
    ScriptedResponse,
)

__all__ = [
    "FakeDocumentParser",
    "FakeEmbedder",
    "FakeLLMClient",
    "FakeSparseEncoder",
    "FakeVectorStore",
    "ScriptedResponse",
]
