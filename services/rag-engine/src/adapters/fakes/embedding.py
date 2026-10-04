"""Deterministic fakes for the ``Embedder`` and ``SparseEncoder`` ports.

The dense fake is a hashing bag-of-words projection: each token is hashed into a
fixed number of buckets with a stable sign, so similar texts land nearby and
deterministically. It is not a semantic model and does not pretend to be one; it
exists so the pipeline, the fusion step and the eval harness run offline.

The failure modes are the interesting part: an empty token set raises rather than
returning a zero vector, because a zero vector silently breaks cosine ranking and
would show up later as an unexplainable retrieval miss.
"""

import math
from collections import Counter
from collections.abc import Sequence
from hashlib import blake2b

from adapters.fakes.tokenization import TOKENIZER_VERSION, tokenize
from domain.errors import EmbedderError
from domain.retrieval import SparseVector, Vector

_DIGEST_BYTES = 8


def _bucket_and_sign(token: str, dimension: int) -> tuple[int, float]:
    """Map a token to a bucket index and a sign, stably across processes."""
    digest = blake2b(token.encode("utf-8"), digest_size=_DIGEST_BYTES).digest()
    value = int.from_bytes(digest, "big")
    return value % dimension, 1.0 if value >> (_DIGEST_BYTES * 8 - 1) & 1 else -1.0


class FakeEmbedder:
    """Hash-based, L2-normalised dense embedder.

    Attributes:
        name: adapter name recorded in the audit trail.
        dimension: width of the produced vectors.
        model_id: fake model identity; recorded so a stored vector is never
            attributed to a model that did not produce it.
    """

    name = "fake_embedder"

    def __init__(self, dimension: int = 64) -> None:
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self.dimension = dimension
        self.model_id = f"fake-hash-{dimension}d"
        self.calls: list[tuple[str, ...]] = []

    def embed(self, text: str) -> Vector:
        """Embed one string, raising on input with no indexable token.

        Args:
            text: text to embed.

        Returns:
            An L2-normalised vector of length ``dimension``.

        Raises:
            EmbedderError: if the text has no tokens.
        """
        tokens = tokenize(text)
        if not tokens:
            raise EmbedderError("cannot embed text with no indexable token")
        vector = [0.0] * self.dimension
        for token, count in Counter(tokens).items():
            index, sign = _bucket_and_sign(token, self.dimension)
            # Sub-linear term weighting: a token repeated ten times must not
            # dominate the vector ten times over.
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:  # pragma: no cover - only reachable on hash cancellation
            raise EmbedderError("degenerate embedding: every token cancelled out")
        return tuple(value / norm for value in vector)

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed passages in order.

        Args:
            texts: passages to embed.

        Returns:
            One vector per input, in the same order.

        Raises:
            EmbedderError: if ``texts`` is empty or any text has no token.
        """
        if not texts:
            raise EmbedderError("embed_documents requires at least one text")
        self.calls.append(tuple(texts))
        return [self.embed(text) for text in texts]

    async def embed_query(self, text: str) -> Vector:
        """Embed a query with the same model as the documents.

        Args:
            text: query text.

        Returns:
            One normalised vector.

        Raises:
            EmbedderError: if the text has no token.
        """
        return self.embed(text)


class FakeSparseEncoder:
    """Deterministic sparse encoder: term frequencies with sub-linear weighting.

    This is a stand-in for BM25 term weighting, not BM25: there is no corpus-level
    IDF, because the fake has no corpus. The store side scores with it anyway, and
    any evaluation of a real BM25 must be run against the real encoder, not this
    one.
    """

    name = "fake_sparse_encoder"

    def __init__(self, model_id: str = "fake-tf-v1") -> None:
        self.model_id = model_id
        self.tokenizer_version = TOKENIZER_VERSION
        self.calls: list[tuple[str, ...]] = []

    def encode(self, text: str) -> SparseVector:
        """Return non-zero term weights for ``text``.

        Args:
            text: text to encode.

        Returns:
            Mapping of token to ``1 + log(term_frequency)``; empty for text with
            no token, which is a valid result and simply will not match.
        """
        return {token: 1.0 + math.log(count) for token, count in Counter(tokenize(text)).items()}

    async def encode_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        """Encode passages in order.

        Args:
            texts: passages to encode.

        Returns:
            One sparse vector per input, in the same order.

        Raises:
            EmbedderError: if ``texts`` is empty.
        """
        if not texts:
            raise EmbedderError("encode_documents requires at least one text")
        self.calls.append(tuple(texts))
        return [self.encode(text) for text in texts]

    async def encode_query(self, text: str) -> SparseVector:
        """Encode a query with the same tokenizer as the documents.

        Args:
            text: query text.

        Returns:
            A sparse vector of non-zero weights.
        """
        return self.encode(text)
