"""``Embedder`` and ``SparseEncoder`` ports: text to vectors.

Dense and sparse retrieval fail in different ways, so the pipeline needs both
(README Part 4). They are separate ports because they are separate components,
call different providers, and get swapped independently during evaluation.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from domain.retrieval import SparseVector, Vector


@runtime_checkable
class Embedder(Protocol):
    """Embed text into a dense vector.

    Contract:
        * Return L2-normalised vectors of length ``dimension`` so cosine similarity
          is a plain dot product and comparable across documents.
        * Embed query and passage with the same model; the pipeline must not mix
          embedding spaces.
        * Preserve input order and count: ``len(out) == len(texts)``.
        * Expose ``model_id`` for the audit record. A change of model invalidates
          every stored vector, so the id must be part of the index identity.

    Failure modes:
        * :class:`~domain.errors.EmbedderError` - provider error, timeout
          or rate limit.
        * :class:`~domain.errors.EmbedderError` - empty input, or input
          exceeding the token limit (silently truncating a table row would corrupt
          the vector).
        * Never returns zero-length vectors or silently truncates.

    Determinism: the same model id and text must yield the same vector. This is a
    precondition for a reproducible index, not a guarantee every provider makes;
    adapters assert it in their own tests with a recorded fixture.
    """

    name: str
    dimension: int
    model_id: str

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed passages in ``texts`` for indexing, preserving order.

        Args:
            texts: contextualised chunk text (prefix included).

        Returns:
            One normalised vector per input, in the same order.

        Raises:
            EmbedderError: on provider failure, empty input, or oversize input.
        """
        ...

    async def embed_query(self, text: str) -> Vector:
        """Embed a single retrieval query with the same model as documents.

        Args:
            text: the retrieval query text.

        Returns:
            One normalised vector of length ``dimension``.

        Raises:
            EmbedderError: on provider failure, empty input, or oversize input.
        """
        ...


@runtime_checkable
class SparseEncoder(Protocol):
    """Encode text into a sparse weighted term representation (BM25 or SPLADE).

    Contract:
        * Return only non-zero weights, keyed by the lowercased token as produced by
          the configured finance-aware tokenizer. ``4,521.3``, ``10-K`` and ``$``
          are handled deliberately, not shredded by a default analyzer, because a
          mangled number is a missed table row.
        * The document encoder and the query encoder must share one tokenizer and
          one vocabulary, or scores are meaningless.
        * Expose ``model_id`` for the audit record, as with :class:`Embedder`.

    Failure modes:
        * :class:`~domain.errors.EmbedderError` - provider error or
          oversize input.
        * Must not raise on text it cannot tokenize; an empty encoding is a valid
          result and simply will not match.

    Determinism: deterministic for a given model id and tokenizer version. Record
    the tokenizer version alongside the model id; changing the analyzer silently
    reweights the whole index.
    """

    name: str
    model_id: str
    tokenizer_version: str

    async def encode_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        """Encode passages for indexing, preserving order.

        Args:
            texts: contextualised chunk text (prefix included).

        Returns:
            One sparse vector per input, in the same order.

        Raises:
            EmbedderError: on provider failure or oversize input.
        """
        ...

    async def encode_query(self, text: str) -> SparseVector:
        """Encode a single query with the same tokenizer as the documents.

        Args:
            text: the retrieval query text.

        Returns:
            A sparse vector of non-zero term weights.

        Raises:
            EmbedderError: on provider failure or oversize input.
        """
        ...
