# ADR-001: What "deterministic" means for this service

- **Status:** Accepted
- **Date:** 2026-10-04
- **Ticket:** E0-07
- **Deciders:** AI Engineering
- **Supersedes:** nothing

## Context

The service extracts five financial metrics (Revenue, Operating Margin, Net Income,
CapEx, EBITDA) from 10-K and 10-Q filings into typed JSON. The acceptance criteria
demand **0% tolerance for hallucinated monetary values**, 100% schema compliance and
per-value provenance.

An LLM is not a function. At temperature 0 it still returns a *sample*: outputs vary
across runs, prompt-builder versions, and library upgrades. A pipeline that forwards
model output unchanged is therefore not a system anyone can put in front of a credit
committee, no matter how good the prompt is.

End-to-end correctness is roughly multiplicative. With four stages at 97% each,
P(correct) ≈ 0.97⁴ ≈ 88.5%. Near-100% therefore requires each stage near 100% *or*
a downstream stage that catches upstream errors. That is the entire justification for
a validating envelope.

## Decision

**"Deterministic" describes the system's guarantees, not the model's behaviour.**
The model is a probabilistic component wrapped in a deterministic envelope built from
typed schemas, pure validators, provenance checks and fail-closed behaviour.

### 1. The model is an untrusted parser

Model output is handled exactly like unvalidated user input. It may report only what
a source page literally prints, together with a verbatim quote:

- `printed_value` is the string **as printed** (`"(10,959)"`), never a normalised
  number. Normalisation into `Decimal` happens in code (`parse_printed_value`), so the
  digits are checkable against the source.
- Evidence (`page`, `quote`, `table_id`) is emitted **before** the value, because a
  model generates left to right: a value that follows a quote is conditioned on text
  rather than on a guess.
- The model never computes. Operating margin, derived EBITDA and the YTD subtraction
  for a single quarter are computed in code from extracted inputs.

### 2. Determinism of the parts we own

| Stage | Guarantee | Enforced by |
|---|---|---|
| Parsing | same bytes + same `parser_version` → same document | versioned Silver layer, parse QA, cross-footing |
| Chunking | same parse output + same `chunker_version` → same chunk ids | structural chunking, stable ordering |
| Indexing | idempotent per `(doc_id, model ids)` | upsert keyed by chunk id, identity in the collection |
| Retrieval | same index + same query → same ranking and order | deterministic tie-breaks, no ANN drift beyond recorded settings |
| Normalisation | pure function of `(printed_value, scale)` | `Decimal`, property-based tests |
| Validation | pure function of `(extraction, context)` | `Validator` port, no I/O and no model calls |
| Audit | append-only, replayable | `AuditStore`, record carries everything needed to re-run |

The only stage allowed to vary is the model call. Everything else is versioned so a
variation can be attributed rather than guessed at.

### 3. Fail closed

Absence is a first-class, valid output. `status` is `found | not_found | ambiguous`,
value fields are optional, and a non-`found` result must carry a `reason`. When
validation cannot establish a value, the service returns a **typed refusal**, never
its best guess. Exhausting the retry cap fails explicitly rather than passing a
partially verified answer downstream.

`A null with a reason beats a plausible number.` A refusal costs a reviewer seconds;
a confident wrong number costs trust in every number the system produces.

### 4. Pinned versions are configuration

Model id, parser version, chunker version, prompt version and tokenizer version are
typed settings stamped into every audit record. Outside `local` and `test`, an
`unpinned` version is a **startup failure**. Changing a pin is a deliberate,
reviewable change that invalidates affected indexes and golden-set results.

### 5. Grounding is checked, not trusted

A hallucinated number cannot survive quote containment: if `normalize(quote)` is not
a substring of the retrieved context, or `printed_value` does not appear inside the
quote, the candidate is rejected. This converts "hallucination" from an unmeasurable
fuzzy risk into a detectable, countable event with a taxonomy code. Residual risk
(a *real* number cited from the wrong column or period) is handled by page, scale and
period-consistency checks, which is why the table IR keeps column header paths.

### 6. "Confidence" means something or it is not shipped

RRF scores and model self-reports are **not** confidence. Confidence is a composite
of measurable signals (validators passed, retriever agreement, self-consistency,
cross-footing satisfied) exposed as raw signals plus a calibrated label. Uncalibrated
numbers must not be presented to a caller; calibration is E7 work.

### 7. Errors are typed and named

Every port failure is a typed exception; every detected defect is a `Violation` with
a stable code from the error taxonomy (`QUOTE_NOT_FOUND`, `PARSE_ERROR`,
`RETRIEVAL_MISS`, ...). Codes are part of the eval report contract, so the failure
histogram can direct the next unit of work.

### 8. Measurement before optimisation

No change ships without a before/after on a fixed query set, changing one variable at
a time. "0% tolerance" is reported as an engineering stance plus a measured upper
bound (rule of three), never as an unqualified claim.

## Consequences

**Positive**

- A wrong number cannot pass silently: it must defeat every layer, and the layers are
  independent (parse, retrieve, extract, validate).
- Results are replayable and auditable, which is the bar for regulated use.
- Components stay swappable, so parser and retriever bake-offs are an adapter plus an
  eval run rather than a rewrite.
- Refusals are actionable: a typed refusal with a reason is a bug report, a wrong
  number is a loss of trust.

**Negative / accepted costs**

- Recall is sacrificed on purpose: strict grounding rejects some correct answers whose
  quote formatting differs from the source. We accept false refusals over false accepts.
- Retry loops threaten the 3.5 s latency budget, so retries are capped and a rising
  retry rate is treated as an upstream bug signal, not as normal operation.
- Pinned versions add friction: upgrading a model or a parser requires re-indexing and
  re-running the golden set.
- Every port needs typed contracts and fakes; that is real E0 work, not overhead.

## Explicit non-goals

- **Not** making the model deterministic. Temperature 0 is a mitigation, not a
  guarantee, and no provider offers one.
- **Not** claiming a measured 0% error rate. We report an engineering stance plus a
  statistical upper bound over a named query set.
- **Not** LLM-as-judge scoring for numeric accuracy. Exact-match comparison is used
  instead; a judge is fooled by the same plausibility that fools the generator.
- **Not** OCR or scanned-filing support in v1, cross-company benchmarking, or
  forecasting.
- **Not** auto-repair of malformed output. A retry with the validator's message may
  fix it; code silently patching a value may not.
- **Not** presenting RRF or similarity scores as confidence.
- **Not** horizontal scaling of ingestion or multi-region writes in Phase 1.
- **Not** self-training or fine-tuning; that is Project 3.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Trust the model with a strong prompt | Optimises fluency, not numerical fidelity; failure is invisible. |
| Constrained decoding only | Guarantees JSON *shape*, does nothing for whether the numbers are right. |
| Post-hoc verification by a second LLM call | Same hallucination surface, no independent signal, adds latency. |
| Deterministic template parsing for statements | Highest fidelity where it applies, but does not cover notes, MD&A and non-GAAP disclosures. It stays a candidate for the E2 parse QA path. |
| Returning `None` for every low-confidence case | Equivalent to refusing always; destroys the measurable middle. |
| Model router choosing parser and store at runtime | Adds a non-deterministic decision to a system whose value is predictability. |

## Consequences for review

Any change that weakens a validator, adds a "best effort" path, or unpins a component
version must state, in the pull request, which clause of this ADR it relaxes and why.
