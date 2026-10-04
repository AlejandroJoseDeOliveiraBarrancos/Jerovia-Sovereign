"""Ports: the interfaces the application depends on.

Every port is a ``Protocol``, so an adapter is any object with the right methods
and tests can substitute a fake without inheritance. Each docstring states three
things, because an unstated contract becomes a silent failure:

* **Contract** - what the implementation must guarantee.
* **Failure modes** - which typed error it raises, and what it must never do.
* **Determinism note** - whether the same input yields the same output, since the
  pipeline's guarantees depend on knowing which steps are reproducible.

The application layer imports ports only; adapters import ports and domain; the
domain imports nothing from either.
"""

from ports.audit import AuditRecord, AuditStore
from ports.chunking import Chunker
from ports.document_parser import DocumentParser
from ports.embedding import Embedder, SparseEncoder
from ports.llm import LLMClient, LLMRequest, LLMResponse, TokenUsage
from ports.validation import Validator
from ports.vector_store import VectorStore

__all__ = [
    "AuditRecord",
    "AuditStore",
    "Chunker",
    "DocumentParser",
    "Embedder",
    "LLMClient",
    "LLMRequest",
    "LLMResponse",
    "SparseEncoder",
    "TokenUsage",
    "Validator",
    "VectorStore",
]
