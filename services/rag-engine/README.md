# rag-engine

Deterministic financial-statement RAG and extraction pipeline: turns 10-K / 10-Q
filings into typed, provenance-backed JSON with no hallucinated numbers.

The design contract is [`docs/adr/0001-deterministic-envelope.md`](docs/adr/0001-deterministic-envelope.md):
the LLM is an untrusted parser inside a deterministic envelope, and the system
answers or refuses, never guesses.

## Layout

```
src/             source root (not a package): the layers below are top-level modules
  domain/        pure types and rules: no I/O, no framework imports
  ports/         Protocol interfaces the application depends on
  adapters/      concrete adapters; fakes/ holds deterministic test doubles
  app/           delivery layer (FastAPI composition root, jobs)
  observability/ structured JSON logging with run_id/doc_id correlation
  settings.py    typed configuration, pinned component versions, VERSION
tests/unit/      offline unit tests (no network, no Docker, no API key)
docs/adr/        decision records
```

Imports follow the source root, so a module reads `from domain.ids import ChunkId`
rather than a package-qualified path. `src` must therefore be on the import path:
`pythonpath = ["src", "."]` does that for pytest, `mypy_path = "src"` for mypy, and
the wheel build maps the same layout for installed use.

Dependencies point inward: `domain` imports nothing from `ports`, `adapters` or
`app`; `ports` never imports an adapter. This is enforced by a test
(`tests/unit/test_ports.py`), not just by convention, so the eval harness can swap
a parser or a store without touching the pipeline.

## Quickstart

```bash
make install            # create .venv and install runtime + dev dependencies
make check              # ruff lint, format check, mypy strict, pytest
make pre-commit         # install the git hooks for this service
make up                 # start Postgres + the app in Docker
```

`make check` is the same gate CI runs, so a green local run means a green pipeline.
With `uv` installed, the targets use `uv run` automatically; otherwise they use
`.venv/bin`.

## Configuration

Settings come from the environment with the `RAG_` prefix, or from `.env` (see
`.env.example`). Two categories matter:

* **Secrets** (`RAG_OPENAI_API_KEY`, `RAG_POSTGRES_DSN`, ...) are `SecretStr`:
  they never appear in `repr`, logs or audit records.
* **Pinned versions** (`RAG_LLM_MODEL_ID`, `RAG_PARSER_VERSION`,
  `RAG_CHUNKER_VERSION`, `RAG_PROMPT_VERSION`, `RAG_EMBEDDER_MODEL_ID`, ...)
  are part of the audit record. Outside `local` and `test`, an `unpinned` version
  is a startup failure, because a result nobody can reproduce is not an answer.

## Deterministic fakes

`adapters.fakes` ships with the package rather than living in the test
tree, so the eval harness and the tracer bullet can run the whole pipeline
offline:

| Fake | Stands in for | Deterministic because |
|---|---|---|
| `FakeLLMClient` | `LLMClient` | responses are scripted per prompt; nothing is invented |
| `FakeEmbedder` | `Embedder` | hashing with `hashlib`, stable across processes |
| `FakeSparseEncoder` | `SparseEncoder` | sub-linear term frequencies, no randomness |
| `FakeVectorStore` | `VectorStore` | exact scoring, RRF fusion, ties broken on chunk id |
| `FakeDocumentParser` | `DocumentParser` | returns registered fixtures, or parses text verbatim |

They honour their port's error contract: an empty token set raises instead of
returning a zero vector, an exhausted script raises instead of inventing an
answer, and a page-count mismatch is an error rather than a warning.

## Current state

Phase 1, E0 (foundations and contracts). In place: the hexagonal skeleton, ports
with documented contracts and failure modes, deterministic fakes, typed settings,
structured logging, ADR-001, CI and the local stack. Not yet built: the metric
ontology and period model (E1), the golden set and eval harness (E1), parsing
(E2), chunking (E3), indexing and retrieval (E4, E6), query understanding (E5),
extraction and validators (E8).

## Notes for contributors

* Money is `Decimal`, never `float`. Ratios and derived values are computed in
  code, never asked of the model.
* A `BUILD` ticket ships with its tests and its log lines.
* Changing any pinned version is a reviewable change; say so in the commit and in
  the ticket, because it invalidates stored vectors and golden-set results.
