"""Deterministic in-memory fakes for the ports.

Properties shared by everything in this package:

* **Deterministic.** No randomness, no clock, no network, no filesystem writes.
  Hashing uses :mod:`hashlib`, never ``hash()``, so results are stable across
  processes and machines regardless of ``PYTHONHASHSEED``.
* **Contract-preserving.** Each fake honours the port's contract, including the
  error cases: a fake that silently succeeds teaches the tests nothing.
* **Observable.** Every fake records what it was asked to do, so a test can assert
  on the interaction (which chunk ids were searched, how many LLM calls happened)
  instead of only on the final value.
"""

from adapters.fakes.document_parser import FakeDocumentParser
from adapters.fakes.embedding import FakeEmbedder, FakeSparseEncoder, tokenize
from adapters.fakes.llm import FakeLLMClient, ScriptedResponse
from adapters.fakes.vector_store import FakeVectorStore

__all__ = [
    "FakeDocumentParser",
    "FakeEmbedder",
    "FakeLLMClient",
    "FakeSparseEncoder",
    "FakeVectorStore",
    "ScriptedResponse",
    "tokenize",
]
