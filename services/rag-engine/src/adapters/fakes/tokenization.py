"""Finance-aware tokenizer shared by the fake embedder and sparse encoder.

The analyzer is deliberately explicit about the tokens that break financial
retrieval: numbers keep their digits (thousands separators removed so ``"1,250"``
and ``"1250"`` match), hyphenated identifiers stay whole (``"10-k"``, ``"10-q"``),
and currency symbols are dropped rather than shredded into punctuation.

This mirrors what a real adapter must do; the version string is exposed through
the ports so a tokenizer change reweights the whole index and shows up in the
audit record.
"""

import re
from typing import Final

TOKENIZER_VERSION: Final = "fake-finance-v1"

#: Ordered alternatives: alphanumeric codes ("7A", "10b5-1"), numbers with
#: optional thousands separators, decimals and hyphenated suffixes ("10-k",
#: "4,521.3"), then words including hyphenated ones ("year-to-date").
_TOKEN: Final = re.compile(
    r"\d+[a-z][a-z0-9-]*|\d[\d,]*(?:\.\d+)?(?:[-/][a-z0-9]+)*|[a-z]+(?:-[a-z0-9]+)*"
)
_WHITESPACE: Final = re.compile(r"\s+")


def tokenize(text: str) -> tuple[str, ...]:
    """Return the ordered tokens of ``text`` for the fake retrievers.

    Args:
        text: raw chunk or query text, contextualised or not.

    Returns:
        Tokens in order of appearance, lowercased, with numeric separators
        removed. An empty tuple means the text carried no indexable token.
    """
    normalized = _WHITESPACE.sub(" ", text).lower()
    return tuple(token.replace(",", "") for token in _TOKEN.findall(normalized))
