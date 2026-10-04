# Project 1: Deterministic Financial Statement RAG & Extraction Pipeline

> A retrieval and extraction engine that turns 10-K / 10-Q filings into typed, provenance-backed JSON, with no hallucinated numbers.

**Module:** `services/rag-engine` | **Status:** Phase 1 | **Owner:** AI Engineering

---

## 1. Overview

This service ingests long, table-heavy financial filings (up to 200 pages) and extracts key metrics (Revenue, Operating Margin, Net Income, CapEx, EBITDA) into strongly typed JSON. Every value carries its source page, the exact supporting paragraph, and a retrieval confidence score.

It is a **deterministic-first** system. The LLM locates and structures information, but it is never trusted to invent, round, or "fix" a number. Anything that fails validation is retried or rejected, never silently passed through.

## 2. Problem Statement & Product Value

**The problem.** Analysts spend hours copying figures from filings into models. Generic RAG pipelines are a poor fit for this work because:

- Standard PDF parsers flatten multi-column tables, so "FY2024" values get attached to the wrong row.
- A single misplaced decimal (`1,250.0` vs `125.0`) can invalidate an entire valuation.
- Free-text answers cannot feed downstream systems like models, dashboards, or covenant monitors.
- Without provenance, nobody can audit a number, so nobody trusts it.

**The value.**

| Value driver | Outcome |
|---|---|
| Time savings | Minutes instead of hours per filing for first-pass extraction |
| Trust | Every number links back to a page and a verbatim snippet |
| Integration | Typed JSON drops straight into spreadsheets, databases, and agents (Projects 2 and 5) |
| Risk reduction | Failed validations surface as explicit errors, not wrong answers |

## 3. Target Users & Use Cases

**Personas:** equity research analysts, credit analysts, FP&A teams, fintech data engineers, and downstream agents that need a reliable "financial facts" tool.

**Use cases**

1. **Earnings-season batch extraction.** Pull the same five metrics from 300 filings overnight into a normalized table.
2. **Analyst Q&A with evidence.** "What was CapEx in Q3 and where does it say so?" Returns the value plus page and snippet.
3. **Feeding the underwriting agent.** Project 2 calls this service as its trusted source of borrower financials.
4. **Audit and review.** A reviewer clicks any extracted value and jumps to the source passage.
5. **Period-over-period comparison.** Consistent schema across filings enables trend analysis without manual cleanup.

## 4. Product Fit

- **Reusable foundation.** This is the base retrieval layer for the rest of the portfolio. Project 6 extends it with re-ranking and temporal filters, and Projects 2 and 5 consume its output.
- **Differentiator.** Most RAG demos optimize for fluent answers. This one optimizes for numerical fidelity and auditability, which is what regulated finance buys.
- **Fit with enterprise needs.** Provenance, schema guarantees, and deterministic failure handling align with model-risk and audit expectations.

## 5. Architecture (High Level)

1. **Parse:** PDF to aligned Markdown/HTML, preserving table structure and footnotes.
2. **Index:** parent chunks (section/page) for context, child chunks (sentence/table row) for matching.
3. **Retrieve:** dense embeddings and BM25/SPLADE in parallel, merged with Reciprocal Rank Fusion.
4. **Assemble:** child hits expand to their parent chunk for LLM context.
5. **Extract:** `Instructor` plus Pydantic schema, with an automated retry loop.
6. **Attach provenance:** page, snippet, and confidence score on every field.

## 6. Functional Requirements

- **FR-1.1 Document Ingestion & Parsing.** Ingest PDFs up to 200 pages; parse nested tables, multi-column headers, and footnotes into aligned Markdown/HTML with no text truncation. *Why: table fidelity is the root cause of most numeric errors.*
- **FR-1.2 Parent-Child Indexing.** Index child chunks for precise vector matching and return parent chunks for LLM context. *Why: precision at match time, completeness at read time.*
- **FR-1.3 Hybrid Retrieval.** Run dense and sparse retrieval simultaneously and merge with RRF. *Why: exact terms like "CapEx" and "EBITDA" favor sparse; paraphrases favor dense.*
- **FR-1.4 Schema Enforcement & Retry Loop.** Extract metrics into a Pydantic schema via `Instructor`; incomplete or non-conforming outputs trigger automated retries.
- **FR-1.5 Provenance Metadata.** Attach source page, exact paragraph snippet, and retrieval confidence to every extracted metric.

## 7. Non-Functional Requirements

- **NFR-1.1 Reliability.** Zero schema validation errors may survive the retry loop.
- **NFR-1.2 Determinism.** Exact fidelity to source values: no decimal shifts, no rounded estimations.
- **NFR-1.3 Latency.** End-to-end extraction query takes 3.5 s or less for documents up to 50 pages.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Context Precision (@k=5) | >= 90% on quantitative table lookups | Labeled table-lookup set; relevant chunk in top 5 |
| Schema Compliance | 100% valid JSON, 0 runtime validation errors | Pydantic validation across full eval run |
| Numerical Accuracy | 0% tolerance for wrong values or decimals | Exact-match comparison vs. hand-verified ground truth |
| Query Latency | <= 3.5 s per query | p95 over benchmark documents (<= 50 pages) |

## 9. Out of Scope & Risks

- **Out of scope:** scanned/OCR-only filings (v1), cross-company benchmarking, forecasting.
- **Risk: scanned or malformed PDFs** may break table parsing. *Mitigation:* parser quality gate that flags low-confidence pages for review instead of guessing.
- **Risk: latency vs. retries.** Retry loops can threaten the 3.5 s budget. *Mitigation:* cap retries and fail explicitly past the cap.
- **Risk: "0% tolerance" is a strong claim.** *Mitigation:* validate against a fixed golden set and report the set size with the result.

# Claude Guidance

# Class: Preparing for Phase 1, Project 1 (Deterministic Financial Statement RAG and Extraction Pipeline)

This class covers the theory and the thought process, then gives you a framework for breaking the work into tasks.

---

## Part 0: What you are actually building

The spec calls it a "RAG pipeline", but that label hides the real problem. Project 1 is an **information extraction system with a retrieval front-end and a verification back-end**, where the cost of a wrong answer is a wrong number in a financial context. The KPIs say so directly: 0% tolerance for hallucinated monetary values, 100% schema compliance, and full traceability.

Most RAG tutorials teach a "chat with your PDF" system where a fuzzy, plausible answer is fine. You are building the opposite. The system must be **correct, or it must visibly refuse**. That one sentence drives almost every design decision below.

Here is the pipeline. Every later section zooms into one stage:

```
PDF ─► [1 Parse] ─► [2 Chunk + enrich] ─► [3 Index] ─┐
                                                      │ (offline, once per document)
──────────────────────────────────────────────────────┘
Query ─► [4 Understand query] ─► [5 Hybrid retrieve + RRF] ─► [6 Parent assembly]
      ─► [7 LLM extraction → Pydantic] ─► [8 Deterministic validation] ─► [9 Audit record] ─► JSON
```

### Where you start from

From the profile in your document, you already own a lot of what this project needs.

| You already have | Why it matters here |
|---|---|
| Medallion-style document extraction pipelines (Marea) | Ingestion maps almost 1:1 to Bronze/Silver/Gold |
| Pub/Sub + Outbox, async pipelines | Ingestion is an event-driven, idempotent, multi-stage job |
| Clean/Hexagonal Architecture | Every component here (parser, embedder, vector store, LLM) must be swappable, because you will experiment constantly |
| 1,300+ tests (unit/functional/E2E) | Evaluation harnesses are tests with statistics attached |
| Python, Postgres, Redis, Docker, GCP | The whole serving and infra side is familiar territory |
| OpenAI API experience | You know the call. You have not yet had to make it reliable |

Your real gaps are mostly conceptual, not engineering gaps:

1. **Information retrieval theory** (BM25, embeddings, ANN indexes, rank fusion, retrieval metrics).
2. **PDF internals and table structure recognition.**
3. **Financial statements and accounting as a domain.** You cannot validate numbers you cannot read.
4. **LLM reliability engineering**: constrained decoding, validation loops, grounding.
5. **Evaluation methodology.** This is the biggest gap and the biggest lever. Most people building these systems fail here, not on the model side.
6. **FastAPI/async idioms** (the spec's reference stack). This is a small gap since you know Django/Flask and Pydantic is the common ground.

The rest of this class is organized to close those gaps in the order the project needs them.

---

## Part 1: The mindset shift (read this twice)

### 1.1 Probabilistic component inside a deterministic envelope

In your normal backend work, a function with the same input returns the same output, and bugs are logic errors. An LLM is a function that returns a *sample from a distribution*. Even at temperature 0 you do not get a hard guarantee of identical outputs across runs, hardware, or model version updates.

So "deterministic" in this project's title does **not** mean "the LLM becomes deterministic". It means **the system's output is deterministic in its guarantees**. You achieve that by wrapping the probabilistic component in layers that constrain, check, and reject:

```
        ┌───────────────────────────────────────────┐
        │  Deterministic envelope (your code)       │
        │   • typed schemas                         │
        │   • validators / invariants               │
        │   • provenance checks                     │
        │   • fail-closed behavior                  │
        │      ┌─────────────────────────────┐      │
        │      │  Probabilistic core (LLM)   │      │
        │      └─────────────────────────────┘      │
        └───────────────────────────────────────────┘
```

**Heuristic 1: The LLM is an untrusted parser, not a source of truth.** Treat its output like user input from the internet. You would never trust unvalidated user input, so do not trust unvalidated model output.

### 1.2 Generation is cheap, verification is the product

The model producing a number is the easy part. The valuable engineering is proving the number is right. Every metric the system returns should survive a chain of checks:

- Does the quoted snippet actually exist in the source page?
- Does the number appear inside that snippet, character for character?
- Do units and scale make sense?
- Does the period match what was asked?
- Do accounting identities hold, where applicable?

**Heuristic 2: Design the verifier first, then the generator.** If you cannot say how you would detect a wrong answer, you cannot claim 0% tolerance.

### 1.3 Fail closed

When the system is not sure, it must return a **typed refusal** (`status: not_found` or `ambiguous`, with a reason), not its best guess. A refusal costs a human a few seconds. A confident wrong number costs trust.

**Heuristic 3: A `null` with a reason beats a plausible number.** Design your schema so that refusing is a first-class, valid output. If a field is required and non-nullable, you are *forcing* the model to hallucinate when the answer is not in the context.

### 1.4 Errors multiply across stages

End-to-end correctness is approximately a product:

```
P(correct) ≈ P(parse ok) × P(retrieve ok | parse ok) × P(extract ok | retrieve ok) × P(normalize ok)
```

If each of four stages is "pretty good" at 97%, you get 0.97⁴ ≈ 88.5%. A KPI of near-100% therefore requires each stage to be near-100% *or* a downstream stage that catches upstream errors. This is why validators and cross-checks exist: they convert a multiplicative error chain into something closer to "an error must slip past *every* layer".

It also gives you your debugging method: **never evaluate only the end result.** Evaluate each stage in isolation (Part 8).

### 1.5 The two kinds of "valid"

This distinction will save you from a classic trap:

- **Syntactic validity**: the output is parseable JSON matching the schema. Modern providers offer schema-constrained decoding that can make this essentially 100%.
- **Semantic validity**: the numbers are *correct*. Schema enforcement does **nothing** for this.

Your KPI "100% valid JSON, 0 runtime validation errors" is a syntactic target. Your KPI "0% tolerance for hallucinated values" is a semantic target. They need completely different mechanisms. Do not confuse the two, and do not let a green schema check make you feel the numbers are safe.

---

## Part 2: The domain you must learn: financial statements

You cannot build an extractor for documents you cannot read. Invest real time here. It is the cheapest high-impact learning in the project.

### 2.1 The documents

- **10-K**: annual report filed with the SEC. Key sections: *Item 1* (Business), *Item 1A* (Risk Factors), *Item 7* (MD&A: management's narrative explanation of results), *Item 8* (Financial Statements and Supplementary Data, including the notes). Often 100 to 300 pages.
- **10-Q**: quarterly report, shorter. Financial statements are in Part I, Item 1, and MD&A in Item 2. Quarterly statements are unaudited and condensed.
- **Earnings releases / earnings decks**: not SEC-form-standardized. They often contain the *non-GAAP* metrics (adjusted EBITDA and similar).

### 2.2 The three statements and where your metrics live

| Statement | What it shows | Your metrics |
|---|---|---|
| **Income statement** (statement of operations) | Performance over a *period* | Revenue, Operating income (→ Operating Margin), Net income |
| **Balance sheet** | Position at a *point in time* | (none directly, but needed for context and checks) |
| **Cash flow statement** | Cash movements over a period (operating / investing / financing) | Capital Expenditures (usually in *investing*, e.g., "purchases of property and equipment"), D&A (an add-back in operating) |

### 2.3 Metric definitions and why each is a design problem

This is where "extract the five metrics" turns out to be five different problems.

- **Revenue.** Appears under many labels: "Net sales", "Total revenues", "Net revenues", "Revenues". Companies also show *segment* and *geographic* revenue, so "revenue" can match many lines. You need a policy: *consolidated total revenue for the requested period*.
- **Operating Margin.** This is a **ratio**, not a reported line: `operating income / revenue`. Almost nobody prints it in the statements. The extractor should pull the two inputs and **compute the ratio in code**. Never ask the LLM to divide.
- **Net Income.** "Net income" vs "Net income attributable to [Company]" vs "Net income attributable to common shareholders" differ when there are non-controlling interests or preferred dividends. Pick one definition and document it.
- **Capital Expenditures.** Not a line on the income statement. Typically found as "Purchases of property, plant and equipment" or "Capital expenditures" in the cash flow statement. It is usually shown as a *negative* number (cash outflow). Your sign convention must be explicit. Some companies also split out "capitalized software" or "intangible assets", so what counts as capex is a definitional choice.
- **EBITDA.** The hardest. It is a **non-GAAP** metric and is generally *not in the financial statements at all*. Two valid approaches, which must be separate, labeled outputs:
  1. **Reported**: the company discloses "Adjusted EBITDA" with a reconciliation (usually MD&A or an earnings release). Extract it and label it `reported_non_gaap`.
  2. **Derived**: `Operating income + Depreciation & Amortization`, where D&A comes from the cash flow statement. Compute it in code, label it `derived`, and list the inputs.

  Decide which the project supports, and write it down. A system that silently mixes the two will produce "wrong" numbers that are each defensible.

### 2.4 The reading traps (the catalog of ways your numbers go wrong)

Memorize these. They are the real adversaries of your 0% tolerance KPI.

1. **Scale/units.** Statements say "(in millions, except per share data)" or "(in thousands)" in a header, often *once per table, not per number*. A parser that drops the header turns 4,521 *million* into 4,521. This is the classic misplaced-magnitude error.
2. **Parentheses mean negative.** `(1,234)` is −1,234. An em dash `—` usually means zero or not applicable, not missing data.
3. **Multiple period columns.** A 10-K income statement typically shows three fiscal years side by side. A 10-Q shows "Three Months Ended" *and* "Nine Months Ended", current and prior year, so four numeric columns. Picking the wrong column is silent and common.
4. **Cash-flow statements in a 10-Q are year-to-date (cumulative).** The Q3 filing shows nine months of capex, not three. A quarterly value requires a subtraction (9M minus 6M). This is an excellent example of a *derived* value that needs explicit logic and an audit trail.
5. **Fiscal vs calendar year.** "Fiscal 2024" may end in September 2024 (or in early 2024 for some retailers). The user's question and the document's labeling can disagree.
6. **Restatements.** Prior-period numbers in a newer filing may differ from the older filing. Which one is "right" depends on the question. Record the filing the number came from.
7. **Footnote markers glued to numbers.** `1,234(1)` or `1,234¹`. A naive parser reads 12,341 or 1,2341.
8. **Same label, different meaning.** "Revenue" in the segment note, in MD&A prose, and in the income statement may all differ in scope.
9. **Tables that span pages** with repeated or missing headers.
10. **MD&A prose vs statement tables.** Prose rounds ("revenue grew to $4.5 billion"), while the table is exact. Prefer the table for numeric values. Use prose only as a corroborating signal.

### 2.5 Accounting identities: your free, deterministic validators

Financial statements obey arithmetic relationships. These give you **verification without any ground-truth labels**:

- `Assets = Liabilities + Equity`
- `Gross profit = Revenue − Cost of revenue`
- `Operating income = Gross profit − Operating expenses` (structure varies)
- Subtotals sum to totals (**cross-footing**): the line items of a table add up to the printed total.
- Net change in cash on the cash flow statement ties to the balance sheet cash change.

**Heuristic 4: When you can exploit a domain invariant, do it.** Cross-footing is a powerful parser-quality check. If a parsed table's line items do not sum to its parsed total, you have *detected a parse error without a human*. That turns a silent failure into a flag.

### 2.6 XBRL: your secret weapon for ground truth

Since 2009 (and with inline XBRL now standard), SEC filings carry machine-readable tags. Each reported fact has a concept (for example `us-gaap:Revenues`, `OperatingIncomeLoss`, `NetIncomeLoss`, `PaymentsToAcquirePropertyPlantAndEquipment`), a period, a unit, and a value. The SEC publishes this data through structured APIs and downloadable datasets.

Why this matters to you:

- **It is how you build the golden dataset cheaply.** You can generate the expected value for a (company, period, metric) query from structured data and then spot-verify by hand, instead of labeling hundreds of numbers manually.
- **It gives you canonical concept IDs** for your metric ontology (label synonyms → one concept).
- Caveat: companies use custom tags, and "Revenue" has several standard tag variants. Always spot-check.

Also note the spec's input is PDFs, so the pipeline must work *without* XBRL. XBRL is your **evaluation oracle**, not your pipeline's data source.

---

## Part 3: Document ingestion and table parsing

### 3.1 What a PDF actually is

A PDF is not a document with structure. It is a **set of drawing instructions**: "place glyph X at coordinates (x, y) in font F". There are no paragraphs, no tables, no reading order, only positioned characters and lines. A "table" is something you *infer* from alignment and rule lines.

Consequences:

- **Native-text PDFs** (generated from software) have extractable characters with exact coordinates. Tools: PyMuPDF, pdfplumber, pdfminer.
- **Scanned PDFs** are images. You need OCR first. Tools: Tesseract, PaddleOCR, docTR, or cloud services.
- **Hybrid PDFs** (the realistic case): some pages native, some scanned, some with embedded images of tables.
- **Reading order** across multi-column layouts is not given. It must be reconstructed.

### 3.2 The tooling landscape (conceptual tiers)

1. **Raw text extractors** (PyMuPDF, pdfplumber): fast, precise coordinates, no table understanding beyond heuristics. Good foundation and fallback.
2. **Layout-aware document parsers** (Docling from IBM, Marker, Unstructured, LlamaParse): detect layout regions (heading, paragraph, table, figure), run table-structure recognition, and output Markdown/HTML/JSON. This is where you will probably start.
3. **Cloud document AI** (Google Document AI, Azure Document Intelligence, AWS Textract): strong table and form extraction; per-page cost; data leaves your environment. You are on GCP, so Document AI is a natural comparison.
4. **Vision-language models** reading page images: flexible and often surprisingly good at messy tables, but slower, costlier, and *capable of hallucinating digits*, which is the exact failure you cannot afford. Use them as a fallback or cross-check, never as an unverified primary source for numbers.

**Heuristic 5: Never choose a parser from a blog post. Choose it by running two or three on *your* documents and diffing the table outputs against a handful of hand-verified tables.** Parser quality is document-dependent, and you now have a way to measure it (cross-footing plus golden tables).

### 3.3 Table structure recognition: why it is hard

Financial tables have:

- **Multi-level column headers** (e.g., "Year Ended December 31" spanning "2025 | 2024 | 2023").
- **Merged cells and indentation as hierarchy** ("Operating expenses:" followed by indented children).
- **Right-aligned numbers with dot leaders** and **currency symbols in separate columns**.
- **Footnote markers**, subtotals, double-underline totals.

Your acceptance criterion says: *preserve cell alignment, multi-column headers, and footnote associations without truncation.* That implies an **output format decision**:

- **Markdown tables** cannot express `colspan`/`rowspan`. They flatten multi-level headers lossily.
- **HTML tables** can. Use HTML as the canonical form for complex tables, and derive a Markdown or text view for embedding and prompting when helpful.
- Even better is a **structured intermediate representation** (JSON: cells with row/col index, span, text, bbox, plus a `footnotes` list), from which you render whatever view you need. This is your "Silver" layer.

### 3.4 Provenance must be captured at parse time

The acceptance criteria require page number, source snippet, and a confidence score per metric. You cannot add provenance later. If your parser throws away page numbers and bounding boxes, the audit trail is unrecoverable. So every parsed element should carry: `doc_id`, `page`, `bbox`, `element_type`, `parser_version`. Treat provenance as a first-class column from day one.

### 3.5 Medallion mapping (you already know this pattern)

- **Bronze**: raw PDF bytes + checksum + metadata (immutable).
- **Silver**: parsed, structured elements (pages, headings, paragraphs, tables as cell grids, bboxes, footnote links), versioned by parser version.
- **Gold**: enriched and chunked records, embedded and indexed, ready to query.

Why this matters: when you improve the parser, you re-run Bronze→Silver→Gold *without* re-uploading. When something breaks, you can inspect each layer. Idempotent stage boundaries (same input + same version → same output) are what let you re-run safely, the same instinct as your Outbox work.

### 3.6 Parse quality assurance

Build a parse QA step that runs before indexing:

1. **Cross-footing check** on parsed numeric tables (flag mismatches).
2. **Scale detection check**: every numeric table must have an associated unit/scale, or be flagged.
3. **Page coverage**: page count in equals pages parsed out; no empty pages where text is expected.
4. **Digit-level sanity**: compare numbers from the native text layer vs the table parser for the same region. A mismatch means one of them is wrong.
5. **Table continuity**: detect tables continuing across pages and stitch them.

**Heuristic 6: Parsing is the stage most likely to silently destroy accuracy, and the one least instrumented in most projects.** Budget real time here. A perfect retriever on a corrupted table still returns the wrong number.

---

## Part 4: Chunking, embeddings, and hybrid retrieval

### 4.1 Why we retrieve at all

A 200-page 10-K can run into hundreds of thousands of tokens. Even with long-context models, stuffing it all in a prompt is slow (your latency KPI is 3.5s), expensive, and less accurate, since models tend to use information in the middle of a long context less reliably (the "lost in the middle" finding). Retrieval narrows the search to the few passages that matter. The price you pay is that **retrieval becomes a new failure point**: if the right passage is not retrieved, the model cannot answer correctly no matter how good it is.

### 4.2 Dense retrieval: how embeddings work (and fail)

An embedding model maps text to a vector so that *semantically similar* texts land near each other. Similarity is usually cosine similarity between vectors. This is a **bi-encoder**: query and passages are embedded independently, so passage vectors can be precomputed and indexed. That is what makes it fast.

Strengths: handles paraphrase and synonyms ("net sales" ≈ "revenue"), and works on natural-language questions.

**Critical weakness for your project: embeddings are poor at exact numbers and rare identifiers.** To an embedding model, `4,521` and `4,512` are nearly the same, and a row about "capital expenditures" and one about "capitalized software costs" are close neighbors. Dense retrieval answers "what is this about?", not "does this contain exactly this token?".

### 4.3 Approximate nearest neighbor search (ANN)

Exact nearest-neighbor search compares the query to every vector. At scale you use ANN indexes, most commonly **HNSW** (a layered proximity graph). Key knobs: `M` (graph connectivity), `ef_construction` (build quality), `ef_search` (query-time recall vs latency tradeoff). Important perspective for *your* scale: a single filing is maybe a few thousand chunks, and a corpus of dozens of filings is tens of thousands. At this scale, **ANN tuning is not your bottleneck**. Do not over-engineer infrastructure before measuring.

### 4.4 Sparse retrieval: BM25 (learn the formula once)

BM25 scores a document D for query Q by summing over query terms:

```
score(D,Q) = Σ_q IDF(q) · [ f(q,D)·(k1+1) ] / [ f(q,D) + k1·(1 − b + b·|D|/avgdl) ]
```

Intuition for each piece:

- `f(q,D)`: how many times the term appears (term frequency), with **diminishing returns** (controlled by `k1`; the 10th mention matters far less than the 1st).
- `IDF(q)`: rare terms count more. "Capex" is more informative than "the".
- `|D|/avgdl` with `b`: **length normalization**, so long chunks are not unfairly favored.

BM25 is exact-lexical: it excels at line-item names, tickers, "Item 7A", and precise terms. It fails on vocabulary mismatch ("capital expenditures" vs "purchases of property and equipment"). **Tokenization matters for finance**: make sure numbers like `4,521.3` and tokens like `10-K` or `$` are handled deliberately rather than shredded by a default analyzer.

**SPLADE** (named in your spec) is a *learned* sparse model: a transformer produces a sparse weighted bag of terms *including expansions* (it can add "revenue" to a chunk that says "net sales"). It combines BM25's exactness with some semantic reach, at the cost of model inference at index time.

### 4.5 Hybrid search and Reciprocal Rank Fusion (RRF)

Dense and sparse fail in *different* ways, so combining them is strictly more robust than either alone. The problem: their raw scores live on different scales (cosine in [−1,1], BM25 unbounded), so you cannot just add them without fragile calibration.

**RRF** sidesteps this by using only *ranks*:

```
RRF(d) = Σ over each ranked list r of  1 / (k + rank_r(d))      # k ≈ 60 is the standard default
```

```python
from collections import defaultdict


def rrf(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores = defaultdict(float)
    for ranking in ranked_lists:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

Documents that appear high in *both* lists win. RRF is simple, robust, and has almost no tuning, which is why it is the default. Know its limits: it discards score magnitude, so a very confident match in one list is not rewarded beyond its rank. Also, **the RRF score is not a calibrated confidence**. Do not present it as "retrieval confidence" without further thought (see Part 7).

### 4.6 Parent-child chunking (the spec's other core concept)

The tension: **small chunks retrieve precisely, but big chunks give the LLM enough context to interpret what it retrieved.** Parent-child (a.k.a. small-to-big) resolves it:

- **Index children** (a table row, a sentence) for precise matching.
- **Return parents** (the whole table, the section, or the page) to the LLM.
- Multiple children matching the same parent are **deduplicated into one parent** (with the best child's score).

For financial documents, define the hierarchy by *document structure*, not by character count:

```
Document → Item/Section → Page/Subsection → Table | Paragraph
                                            └─ Table → Row (child)
```

**Never use fixed-size character chunking on tables.** It will cut a table mid-row and separate numbers from their headers. Chunk by structure: a table is atomic as a parent; paragraphs are split on sentence boundaries.

### 4.7 Contextualize every child chunk

A table row `Purchases of property and equipment | (10,959) | (11,085) | (10,708)` is nearly meaningless in isolation. Which company? Which statement? Which years? In which unit? Before embedding and BM25-indexing a child, **prepend its context**:

```
[Company X | 10-K | FY2024 | Consolidated Statements of Cash Flows | in millions USD | columns: FY2024, FY2023, FY2022]
Investing activities — Purchases of property and equipment: (10,959) | (11,085) | (10,708)
```

This is the same principle as published "contextual retrieval" techniques (prepend chunk-specific context before indexing). For tables, the context is *deterministic*: you assemble it from your Silver layer (title, units, flattened headers) with no LLM needed. Prefer deterministic enrichment over LLM-generated enrichment whenever possible. It is cheaper, repeatable, and cannot hallucinate.

### 4.8 Metadata filtering: the highest-ROI retrieval trick

Every chunk carries metadata: `company`, `ticker`, `filing_type`, `fiscal_year`, `period_end`, `statement_type`, `page`, `element_type`, `doc_id`. If the user asks about a specific company and fiscal year, **filter to those chunks before** similarity search. You eliminate whole categories of wrong answers (right metric, wrong year or company) at near-zero cost.

This implies a **query understanding step**: parse the incoming query into `{company, period, metric, ...}` (often a small structured-extraction call, or rules plus a lookup table). Heuristic: **narrow the search space with structure before you search with semantics.**

### 4.9 Metric ontology and synonym handling

Maintain a small, hand-curated mapping per metric: canonical id → label synonyms → typical statement → typical sign convention → XBRL concepts. For example, `capex` → {"capital expenditures", "purchases of property and equipment", "additions to property, plant and equipment", ...} → cash-flow/investing → outflow (negative). Use it to expand the BM25 query and to steer retrieval toward the right statement type. It is a boring dictionary, and it is one of the most effective accuracy levers in the pipeline.

### 4.10 Choosing the vector store (a decision, not a tutorial)

Constraints: hybrid dense+sparse, metadata filtering, parent/child linkage, ease of running locally and on GCP.

- **Qdrant**: supports dense and sparse vectors in one collection plus fusion (including RRF) at query time, and rich payload filtering. A natural fit for the spec.
- **Postgres + pgvector**: you know Postgres, and it keeps everything in one store. Native full-text search is *not* BM25, so you would need an extension or an external BM25 piece, or do the sparse side in application code.
- **OpenSearch/Elasticsearch**: BM25 is native; dense via kNN. Heavier to operate.

Put the choice behind a `VectorStore` port (Hexagonal) and decide with a measured spike (Part 9). Do not agonize in advance.

---

## Part 5: Structured extraction and validation

### 5.1 The pattern

1. Build the prompt from the **assembled parent chunks** plus the **metric definition** (from your ontology).
2. Ask the model to fill a **Pydantic schema** via a library like **Instructor** (it patches the LLM client, accepts a `response_model`, validates the response, and on failure **re-asks the model with the validation error message** up to `max_retries`).
3. Run **semantic validators** (Pydantic validators + your own post-checks).
4. If everything passes, return. If retries are exhausted, **fail closed** with a typed refusal.

### 5.2 Schema design is the core intellectual work

Principles:

1. **Let the model say "I can't find it."** Include `status: found | not_found | ambiguous` and make value fields optional. A schema that cannot express absence manufactures hallucinations.
2. **Use `Decimal`, never `float`.** Floats cannot exactly represent many decimal values. Money requires exactness.
3. **Have the model return the number *as printed*** (`"(1,234.5)"`) plus `scale` and `currency`, and let **your code** parse it into a `Decimal`. This removes parsing and arithmetic from the model and creates a verifiable string you can match against the source.
4. **Put evidence fields before value fields.** LLMs generate left to right. If the model must first emit the quote and page, the value that follows is conditioned on actual text, not on a guess.
5. **Include provenance in the schema**: `page`, verbatim `quote`, `table_id`. These map directly to the Auditability AC.
6. **Never let the model compute.** Operating margin and derived EBITDA are computed in code from extracted components.

A sketch:

```python
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, field_validator, model_validator


class Status(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class Scale(str, Enum):
    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


class Evidence(BaseModel):
    page: int
    table_id: str | None = None
    quote: str  # verbatim from the source, must contain the printed number


class MetricExtraction(BaseModel):
    metric: str  # canonical id from your ontology
    status: Status
    evidence: Evidence | None = None  # emitted BEFORE the value
    printed_value: str | None = None  # exactly as in the document, e.g. "(1,234.5)"
    scale: Scale | None = None
    currency: str | None = None
    period_label: str | None = None  # e.g. "Fiscal year ended Sep 28, 2024"
    reason: str | None = None  # required when not FOUND

    @model_validator(mode="after")
    def found_requires_evidence(self):
        if self.status == Status.FOUND and not (
            self.evidence and self.printed_value and self.scale
        ):
            raise ValueError("FOUND requires evidence, printed_value and scale")
        if self.status != Status.FOUND and not self.reason:
            raise ValueError("Non-FOUND results must explain why")
        return self
```

Note what is *not* here: the normalized `Decimal` value. That is computed by a deterministic function from `printed_value` + `scale`. The validators that need context (does the quote actually appear in the retrieved text?) run as a second layer, because they require the retrieved chunks, not just the model output.

### 5.3 The grounding validator (your main weapon against hallucination)

After the model responds, deterministically check:

1. **Quote containment**: `normalize(quote)` is a substring of `normalize(retrieved_parent_text)` (normalize whitespace and unicode).
2. **Number containment**: `printed_value` appears in `quote`.
3. **Page consistency**: `evidence.page` matches the page of the chunk the quote came from.
4. **Scale consistency**: the scale equals what the Silver layer recorded for that table.
5. **Period consistency**: the column the number came from corresponds to the requested period (requires your table IR to keep column header paths).
6. **Sign convention**: apply the metric's convention (e.g., capex outflows reported negative, so you may report the absolute magnitude, stated explicitly).
7. **Plausibility checks** (soft): the value is within a sane relative range vs. other known figures from the same filing (e.g., net income ≤ revenue except in odd cases, margin between −100% and 100%).

If any check fails, feed the specific failure back into the retry (Instructor does this for Pydantic errors; you can raise validation errors from your own checks to reuse the same loop). If it still fails, fail closed.

**Heuristic 7: A hallucinated number that cannot be found in the source text cannot pass quote containment.** This converts "hallucination" from an unmeasurable fuzzy risk into a *detectable, countable event*. The remaining risk is the model quoting a *real* number from the *wrong* place (wrong column, wrong table, wrong period). That is why checks 3 to 5 exist, and why your table IR must retain header paths.

### 5.4 Constrained decoding vs retry loops

Provider-level structured outputs (schema-constrained decoding) guarantee the JSON *shape*. Retry loops with validation feedback handle *semantic* rules the schema cannot express. Use both: constrain the shape cheaply, retry on semantic failures. Caps matter: set a maximum retry count (2 or 3), because each retry multiplies latency (your 3.5s budget) and cost, and a retry that keeps failing usually signals a retrieval or parsing bug, not a prompting bug. **Log every retry**; a rising retry rate is a leading indicator of degraded upstream stages.

### 5.5 Prompting heuristics for extraction

- Give the model the **metric definition and tie-breaking rules** (consolidated, not segment; the requested period column; the statement type).
- Tell it explicitly that **absence is acceptable** and show the refusal format.
- Pass context with **clear delimiters and identifiers** (page, table id) so it can cite them.
- Keep context **tight**: fewer, better parents beat many mediocre ones.
- Temperature 0, pinned model version, and the prompt under version control (hash it into the audit record).

---

## Part 6: Query understanding and the end-to-end flow (worked example)

Take the query: *"What were the capital expenditures for fiscal 2024?"* on a filing of a company whose fiscal year ends in late September. Walk the pipeline and ask at each stage, **"what could go wrong?"**. This habit is called a **pre-mortem**.

1. **Query understanding**: metric=`capex`; period="fiscal 2024". *Risk*: ambiguity (which company/filing? fiscal vs calendar?). Resolve using the filing metadata (`fiscal_year`, `period_end`).
2. **Metadata filter**: restrict to this `doc_id` and likely statement types (cash flow, plus the notes). *Risk*: a wrong filter that excludes the right page → recall loss. Keep the filter permissive where unsure.
3. **Hybrid retrieval over children**: BM25 matches "purchases of property and equipment" thanks to synonym expansion; dense matches semantically. RRF fuses. *Risk*: the "capital expenditures" phrase appears in MD&A *prose* about future plans and outranks the cash flow table. Mitigation: steer by statement type / prefer table elements for numeric metrics.
4. **Parent assembly**: dedupe children → parents (the cash flow table page). *Risk*: the table spans two pages and the relevant row is on the second page. The parent definition should be the *whole stitched table*.
5. **Extraction**: LLM fills the schema with `printed_value="(10,959)"`, `scale=millions`, `period_label="Fiscal 2024"`, evidence quote. *Risk*: picks the 2023 column.
6. **Validation**: quote ∈ parent? number ∈ quote? column header path matches fiscal 2024? scale matches table header? *Risk*: a parse error already put the wrong header over this column, so the validators agree with a corrupted structure. This is why parse QA (cross-footing, digit comparison) exists upstream.
7. **Deterministic normalization**: `Decimal("-10959") × 10^6`, then convention-adjusted. *Risk*: sign or scale mistake; this is a pure function, so test it exhaustively (property-based tests with Hypothesis are perfect here).
8. **Audit record**: persist everything (doc version, parser version, chunk ids, ranks, scores, prompt hash, model id, raw response, validation results, retry count).

The point of the exercise: **every stage has a named failure mode and a named countermeasure.** That is what "designing the solution" means for a reliability-critical system.

---

## Part 7: Auditability and "confidence"

The AC asks for "retrieval confidence score" per metric. Think carefully about what that can honestly mean.

- The RRF score is a *rank-derived relevance signal*, not a probability of correctness.
- A model's self-reported confidence ("I'm 95% sure") is poorly calibrated. Do not rely on it.
- A more honest approach is a **composite, evidence-based confidence** built from signals you can measure:
  - Did all deterministic validators pass? (hard gate)
  - Did the dense and sparse rankers *both* surface the supporting child in their top N? (retrieval agreement)
  - Did a second independent extraction (different prompt, model, or retrieval) agree? (self-consistency)
  - Was the cross-footing check satisfied for the source table? (parse integrity)
  - Did the number also appear in corroborating text (MD&A prose rounding to it)?

Expose both the **raw signals** and a derived label (`high / medium / low`). Then **calibrate** against your golden set: among outputs labeled "high", what fraction were actually correct? If "high" is not ≥ your target, your thresholds are wrong. A confidence number you have not calibrated is decoration.

For audit storage: write append-only records, keyed by `run_id`, including enough to **replay** the result (document and parser version, chunk ids, prompt hash, model id and params, raw model output). Immutability and reproducibility are the point.

---

## Part 8: Evaluation (the most important part of the project)

Many people build RAG systems and cannot tell you whether a change made them better. You will not be one of them.

### 8.1 Retrieval metrics

- **Precision@k**: fraction of the top-k results that are relevant.
- **Recall@k / Hit rate@k**: whether at least one relevant item appears in the top-k.
- **MRR** (Mean Reciprocal Rank): average of `1/rank` of the first relevant result.
- **nDCG**: rewards putting highly relevant items higher, supports graded relevance.
- **Ragas "context precision"**: a rank-aware measure (like average precision over the retrieved contexts), a *different* thing from plain precision@k.

**An important catch in your own KPI:** "Context Precision @k=5 ≥ 90%". If a lookup question has exactly *one* relevant chunk, plain precision@5 is capped at 20% (1 relevant of 5). So the KPI only makes sense if (a) relevance is defined at the **parent** level where several children map to the same relevant parent, or (b) you mean a rank-weighted context-precision metric, or (c) there are several relevant contexts per query. Write the **measurement protocol** *before* you build: exactly which metric, at what level (child/parent), over which query set. KPIs without protocols are not measurable.

### 8.2 Generation and end-to-end metrics

For numeric extraction, use **deterministic exact-match**, not an LLM judge: `normalize(predicted) == normalize(gold)` for the value, scale, and period. LLM-as-judge faithfulness scoring (as in Ragas) is useful for narrative answers (Project 6), but it is the wrong tool when you demand 0% tolerance on digits. A judge can be fooled by the same plausibility that fools the generator.

Track separately:

- **Value accuracy** (exact match after normalization)
- **Refusal behavior**: precision/recall of `not_found` (did it refuse when the answer truly is absent? did it refuse when the answer was present?)
- **Schema compliance rate** and **retry rate**
- **Grounding pass rate**
- **Latency percentiles** (p50, p95; averages hide tails)

### 8.3 The golden dataset

Construction recipe:

1. Select 10 to 20 filings with **diversity**: different industries, fiscal year ends, formatting styles, a restatement, a company with segment-heavy reporting, one scanned or low-quality PDF, one 10-Q.
2. Generate candidate gold values from XBRL (Part 2.6), then **manually verify** a sample against the PDF (and any value that looks suspicious).
3. Create queries (company × period × metric) including **hard cases**: parentheses negatives, thousand vs million scales, cumulative YTD cash-flow items in 10-Qs, label variants, metrics not present (to test refusal).
4. Tag each query with **slice attributes** (document, table type, scale, difficulty) so you can analyze by slice.
5. **Split**: a dev set you iterate against and a held-out test set you touch rarely. Otherwise you overfit to your own examples and your reported accuracy is fiction.

### 8.4 Stage-wise evaluation with "oracle" inputs

This is your core debugging method, and your answer to "where is the error?":

- Feed the **gold parsed table** directly to extraction → measures extraction + validators in isolation.
- Feed **gold relevant chunks** to the LLM → measures the model/prompt alone.
- Run retrieval and check whether the gold parent is in the top-k → measures retrieval alone (given a parse).
- Compare parser output to hand-verified tables → measures the parser alone.

Build an **error taxonomy** and tag every failure: `PARSE_ERROR`, `RETRIEVAL_MISS`, `RANKING_MISS`, `WRONG_CONTEXT_SELECTED`, `EXTRACTION_ERROR`, `NORMALIZATION_ERROR`, `FALSE_REFUSAL`, `FALSE_ACCEPT`. After each eval run, you get a histogram of failure types. **That histogram tells you what to work on next.** Without it you are guessing.

### 8.5 Statistical honesty

- With a small query set, a measured 100% does not prove 0% error. By the "rule of three", if you observe **zero** errors in *n* independent trials, the 95% upper bound on the true error rate is about **3/n**. With 100 clean queries, you can only claim "error rate likely below ~3%", not "0%".
- Therefore "0% tolerance" is best understood as an **engineering stance** (design so any residual error is caught by validators or turned into a refusal) plus a **measured upper bound** that tightens as your test set grows. State it that way.
- Run enough samples that differences between variants are not noise. Change **one variable at a time** (chunking, embedding model, fusion params, prompt) and record before/after on the same fixed set.
- Mind **nondeterminism**: run LLM evals more than once and look at variance.

### 8.6 Make the harness part of CI

You wrote 1,300+ tests; apply the same discipline here. Unit tests for the normalizer and validators (property-based), snapshot tests for parsed tables, and an **eval job** that runs on every meaningful change and fails the build if a tracked metric regresses beyond a threshold. This is how a prototype becomes a system.

---

## Part 9: Latency and systems design

### 9.1 Read the KPI precisely

"≤ 3.5 seconds per extraction query for documents up to 50 pages." Decide and write down:

- **Ingestion is offline.** Parsing, enrichment, embedding, and indexing do *not* count against query latency. That is why you precompute everything.
- Is "a query" **one metric** or **all five**? Both are defensible; the architecture differs (one call with a five-field schema vs five parallel calls).

### 9.2 Latency budget (a thinking tool)

Allocate your 3.5s *before* optimizing:

| Step | Rough share |
|---|---|
| Query understanding (rules, or a tiny call) | tens of ms |
| Embed query | ~50 to 200 ms |
| Hybrid search + fusion + filter | ~10 to 100 ms |
| Parent assembly | few ms |
| **LLM call (input tokens, output tokens)** | **~1 to 2.5 s, dominating** |
| Validators + normalization | few ms |
| One retry (if it happens) | *doubles the LLM cost* |

The LLM call dominates, so the optimization levers are: **fewer and shorter context tokens** (retrieve less, but better), a **smaller/faster model** (validated by your eval set), **short structured outputs** (generation time scales with output tokens, so keep the schema compact; quote snippets, not paragraphs), **parallelizing independent metric calls**, and **caching** (embedding cache, query-result cache, provider prompt caching for the stable prefix). Measure with traces. Do not guess.

### 9.3 Architecture and tests

Apply the Hexagonal structure you already use:

- **Ports** (interfaces): `DocumentParser`, `Chunker`, `Embedder`, `SparseEncoder`, `VectorStore`, `LLMClient`, `Validator`, `AuditStore`, `Evaluator`.
- **Adapters**: Docling/PyMuPDF parser, OpenAI/Anthropic LLM client, Qdrant store, and so on.
- **Domain core**: the financial metric ontology, normalizers, validators, and the pipeline orchestration, with no framework imports.

Why this matters more than usual: your highest-value activity will be **swapping components and measuring** (parser A vs B, embedding X vs Y, store 1 vs 2). Hexagonal turns each experiment into one adapter plus one eval run. Keep **fakes** for LLM and embedder in tests so the suite is fast and deterministic.

Serving: the spec references FastAPI; its async model and native Pydantic v2 integration fit well. Ingestion runs as an async job (queue + workers, idempotent stages, status tracking), the same shape as your Pub/Sub work. Containerize, add health checks, and instrument from day one (structured logs with a `run_id` on every line; tracing hooks you can later feed into Project 4's Langfuse/OpenTelemetry stack).

---

## Part 10: The decomposition framework

This is the framework you asked for, to understand difficulty and turn it into distributable tasks. It has three tools. Use them in order.

### Tool 1: The Stage × Error-Type grid

List the pipeline stages across the top and the *kinds of failure* down the side. It makes sure you plan for the failure modes, not just the happy path.

| Stage → / Failure ↓ | Parse | Chunk/Index | Retrieve | Extract | Validate/Normalize | Serve |
|---|---|---|---|---|---|---|
| **Silent wrong data** | wrong scale, merged cell | header lost from row | wrong period surfaced | wrong column picked | sign/scale bug | stale index |
| **Missing data** | dropped page/table | table split | recall miss | false refusal | over-strict validator | timeout |
| **Cost/latency** | slow OCR | oversized chunks | heavy rerank | long context, retries | n/a | cold start |
| **Unobservable** | no provenance | no lineage | no scores logged | raw output not stored | no failure reasons | no traces |

Every empty cell is a task you have not thought about. Fill the grid, then turn each filled cell into either a test, a validator, a log line, or a design decision.

### Tool 2: The Difficulty Profile (score each work package on four axes, 1 to 5)

Difficulty is not one number. A task can be easy to code and brutal to verify. Score each package on:

- **U: Uncertainty** (do I know *how* to do it? Is the approach unknown?)
- **C: Coupling** (how many other parts depend on this interface or output format?)
- **V: Verification gap** (how hard is it to *know* it is correct? 5 = no obvious test or metric)
- **D: Data/domain dependency** (how much does it depend on real documents or finance knowledge?)

Then the **profile determines the task type and how to treat it**:

| Profile | Meaning | Treatment |
|---|---|---|
| **U ≥ 4** | Approach unknown | **Spike**: time-boxed (e.g., 4 to 6 deep hours), output is a *decision and a measurement*, not production code |
| **V ≥ 4** | Hard to verify | **Build the measurement first** (fixtures, oracle, metric) before the implementation |
| **C ≥ 4** | Many dependents | **Freeze the contract first** (typed interface + sample payloads), then parallelize both sides |
| **D ≥ 4** | Domain-heavy | **Study + annotate real examples first**, then code; schedule it earlier |
| all ≤ 2 | Plain engineering | Just build, test, and move on |

A useful ordering rule is to **do the high-V and high-U items early**. They are where the schedule surprises live, and the risk of discovering late that the parser cannot handle your documents is exactly the kind of mistake that sinks projects.

### Tool 3: Tracer bullet first, then deepen (the delivery pattern)

Build a **walking skeleton**: one small PDF → crude parse → naive chunks → dense-only retrieval → LLM → Pydantic → JSON with a page number, with an eval script that scores it, all running end-to-end. It will be *bad*. That is the point. Now every improvement is a measured delta against a working baseline, instead of an integration nightmare at the end. Deepen the stages in order of the error histogram (Part 8.4), not in order of what feels interesting.

### The work packages for Project 1

Estimates are in **deep-work hours** (your own tracked average is about 3.5 to 3.7 deep hours per day, so use that to convert). They are rough and should be refined after the spikes.

| WP | Scope | U | C | V | D | Est. | Notes |
|---|---|---|---|---|---|---|---|
| **WP0** | Decisions + skeleton: metric definitions (ADRs), repo with ports/adapters, CI, config | 1 | 4 | 1 | 3 | 6 h | Freeze the **metric contract** (definitions, period rules, sign, EBITDA policy) |
| **WP1** | Golden dataset + eval harness v0 (XBRL-seeded, hand-verified, slices, metrics) | 3 | 5 | 4 | 5 | 14 h | **Build before the pipeline.** Everything is judged by this |
| **WP2** | Ingestion/parsing: Bronze→Silver, table IR with header paths + footnotes, parse QA (cross-footing, scale) | 5 | 5 | 4 | 4 | 24 h | Highest risk. Start with a parser bake-off spike |
| **WP3** | Chunking + deterministic contextual enrichment, parent/child model, metadata | 3 | 4 | 3 | 3 | 12 h | Depends on the Silver IR contract |
| **WP4** | Indexing + hybrid retrieval + RRF + metadata filters (+ store spike) | 3 | 3 | 3 | 2 | 14 h | Measure dense-only vs BM25-only vs hybrid |
| **WP5** | Query understanding: entity/period/metric parsing, synonym ontology, routing | 3 | 3 | 3 | 4 | 8 h | Mostly rules + a curated dictionary |
| **WP6** | Extraction: schema, prompts, Instructor loop, grounding validators, normalizer, fail-closed | 4 | 3 | 4 | 4 | 18 h | Normalizer = pure functions → property tests |
| **WP7** | Provenance, composite confidence, immutable audit records | 3 | 2 | 4 | 2 | 8 h | Calibrate confidence against the golden set |
| **WP8** | API/serving, async ingestion jobs, caching, latency budget, observability hooks | 2 | 2 | 2 | 1 | 10 h | Familiar territory for you |
| **WP9** | Evaluation campaigns + hardening on 200-page docs, error-histogram-driven fixes | 3 | 2 | 3 | 4 | 20 h | Loops until KPIs or documented limits |

Total is about 134 deep hours. At your tracked average of ~3.5 deep hours per day, that is roughly 38 focused days. If you give this a fraction of your deep-work time, scale accordingly.

### Dependencies and what can run in parallel

```
WP0 ──► WP1 (eval) ─────────────────────────────────────────┐
  │                                                         │
  ├──► WP2 (parse) ──► WP3 (chunk) ──► WP4 (index/retrieve) ─┤
  │                                                         ├─► WP9 (campaigns)
  ├──► WP5 (query understanding) ──────────────────────────┤
  │                                                         │
  └──► WP6 (extraction; develop against gold chunks) ──► WP7 ┘
                              WP8 (serving) can start after M0
```

The key parallelization trick is **contract-first development**. If you freeze the Silver table IR schema and the Gold chunk schema early, then **WP6 (extraction) can be developed against hand-made gold chunks while WP2 (parsing) is still unfinished**. Likewise, WP1's harness can evaluate the extractor in "oracle mode" before retrieval exists. The same contracts let you distribute work across days, collaborators, or AI coding assistants without them blocking each other. Each task you hand off should be written as:

```
Task: <name>
Goal: <one sentence>
Contract: input type → output type (link to schema + 2 sample payloads)
Definition of Done: <metric + threshold on a named fixture set>
Fixtures: <which documents / which golden queries>
Out of scope: <what NOT to do>
Time-box: <deep hours>; Spike? <yes/no, and what decision it must produce>
```

### Milestones with exit criteria

- **M0, Walking skeleton**: one small 10-Q end-to-end, baseline eval score recorded.
- **M1, Measurement online**: golden set (~20 filings' worth of queries, seeded from XBRL) plus harness plus slice reports in CI.
- **M2, Trustworthy parse**: table IR with header paths, footnotes, scale; cross-footing passes on the target tables; parser chosen by bake-off.
- **M3, Retrieval proven**: hybrid + parent-child + filters beat dense-only on your metric by a *measured* margin.
- **M4, Verified extraction**: grounding validators + fail-closed; schema compliance and zero un-grounded values on the dev set.
- **M5, Production shape**: audit trail, calibrated confidence, latency within budget at p95 on ≤50 pages, 200-page ingestion stable, held-out test evaluation.

---

## Part 11: The design heuristics (a cheat sheet to internalize)

1. **The LLM is an untrusted parser.** Verify everything it says.
2. **Push determinism downward.** If code can compute, normalize, or look up something, never ask the model.
3. **Make illegal states unrepresentable.** Use types (`Decimal`, enums), required evidence, and a refusal status so wrong shapes cannot exist.
4. **Fail closed.** A typed refusal beats a plausible guess.
5. **Metadata before semantics.** Filter by company and period before you embed anything.
6. **Index small, return big.** Child precision, parent context.
7. **Contextualize deterministically.** Prepend headers, units, and period to every row before indexing.
8. **Provenance at birth.** Page and bbox captured at parse time, or lost forever.
9. **Measure before you optimize.** No change without a before/after on a fixed set.
10. **One variable at a time.** Otherwise you learn nothing.
11. **Evaluate stages in isolation with oracle inputs.** Find *where* it breaks, not just *that* it breaks.
12. **Tag every error with a taxonomy.** The histogram is your roadmap.
13. **Prefer exact-match to LLM judges for numbers.**
14. **Exploit domain invariants** (cross-footing, accounting identities) as free validators.
15. **Do not trust unmeasured confidence.** Calibrate or discard.
16. **Define every KPI's measurement protocol up front.** Otherwise it is a slogan.
17. **Build the simplest thing that works, then let the error histogram guide complexity.** Add reranking, query rewriting, or fancier parsers only when the data says retrieval or parsing is the bottleneck.
18. **Log at every boundary** with a `run_id` so any answer can be replayed.

### Common anti-patterns (what experienced people see go wrong)

- Fixed-size character chunking applied to tables.
- Embedding table rows *without* their headers, units, and period.
- Dropping footnotes or the "(in millions)" header during parsing.
- Using `float` for money.
- Letting the model do the arithmetic (margins, EBITDA, YTD subtraction).
- Trusting the model's own "confidence".
- Tuning on the same queries you report results on.
- Letting retries hide an upstream bug (rising retry rate = something upstream is broken).
- Making all schema fields required so the model must invent values.
- Mixing "reported non-GAAP" and "derived" EBITDA under one field name.
- Optimizing ANN settings for a corpus of a few thousand vectors.
- Declaring "0% error" after 20 clean test queries.

---

## Part 12: A study sequence before and during the build

Do these as small, time-boxed labs (a few hours each). They build intuition faster than reading.

1. **Read real filings.** Take two 10-Ks and one 10-Q from different industries. Locate the three statements, the unit headers, the footnotes, and the capex row. Hand-compute operating margin. Find a cumulative YTD cash-flow line in the 10-Q. (4 to 6 h)
2. **BM25 from scratch** on a small corpus of table rows; then compare to a library. Observe where it fails on synonyms and where it beats dense on exact terms. (3 h)
3. **Dense retrieval + the number problem**: embed rows with numbers and watch near-identical numbers retrieve each other. This builds a lasting intuition. (3 h)
4. **Implement RRF** and compare dense-only, BM25-only, and fused rankings on 15 queries with mrr and hit@k. (3 h)
5. **Parser bake-off spike**: run two or three parsers on the same 10 pages (including a multi-column-header table and a page-spanning table). Score by cross-footing and hand verification. (6 h)
6. **Instructor + Pydantic**: build the `MetricExtraction` schema, add the grounding validator, deliberately feed it a context where the answer is absent, and verify it refuses instead of hallucinating. (4 h)
7. **Mini eval harness**: 20 queries from XBRL gold, exact-match scoring, error taxonomy tagging, a slice report. (4 h)
8. **Latency profiling**: put timers around every stage on the skeleton and look at the real budget. (2 h)

---

## Part 13: Books and further reading

### Core (in rough priority order for this project)

1. **AI Engineering**, Chip Huyen (O'Reilly). Evaluation, RAG, prompt and system design for foundation-model applications. The best single book for the *engineering* side of what you want to become.
2. **Introduction to Information Retrieval**, Manning, Raghavan, Schütze (free online). The canonical text for BM25, indexing, evaluation metrics (precision/recall, MAP, nDCG). Read the chapters on scoring, evaluation, and probabilistic IR.
3. **Architecture Patterns with Python**, Harry Percival & Bob Gregory. Ports/adapters, repository and unit-of-work patterns, event-driven design. It matches your Hexagonal instincts and Python stack.
4. **Hands-On Large Language Models**, Jay Alammar & Maarten Grootendorst (O'Reilly). Embeddings, semantic search, RAG, with practical code.
5. **Designing Machine Learning Systems**, Chip Huyen. Data pipelines, evaluation, monitoring, and iteration, the production mindset around ML components.
6. **AI-Powered Search**, Trey Grainger, Doug Turnbull, Max Irwin (Manning). Modern hybrid and learned retrieval, relevance engineering.
7. **Relevant Search**, Doug Turnbull & John Berryman (Manning). How to *reason about* and debug search relevance, which is exactly the skill you need for retrieval tuning.

### Finance domain (choose one beginner and one deeper)

- **Financial Statements: A Step-by-Step Guide to Understanding and Creating Financial Reports**, Thomas Ittelson. The gentlest and most practical introduction to the three statements.
- **Financial Intelligence**, Karen Berman & Joe Knight. Intuition for what the numbers mean and where they can mislead.
- **The Interpretation of Financial Statements**, Benjamin Graham & Spencer Meredith. Short classic.
- **Financial Shenanigans**, Howard Schilit. Teaches how reported numbers get distorted, which sharpens your sense for ambiguity, restatements, and non-GAAP traps.

### Foundations for later phases (start skimming now)

- **Speech and Language Processing**, Jurafsky & Martin (free online draft). Reference for retrieval, transformers, and evaluation.
- **Natural Language Processing with Transformers**, Tunstall, von Werra, Wolf. Practical transformer usage.
- **Build a Large Language Model (From Scratch)**, Sebastian Raschka. Valuable for your Phase 4 (fine-tuning) goals.
- **Designing Data-Intensive Applications**, Martin Kleppmann. You may already know it; reread the indexing, encoding, and pipeline chapters through the lens of this project.

### Papers, benchmarks, and docs worth reading (short, high value)

- Cormack, Clarke & Büttcher, *Reciprocal Rank Fusion* (2009). Two pages that explain your fusion step.
- Liu et al., *Lost in the Middle* (2023). Why long contexts are not a substitute for retrieval.
- Anthropic's write-up on **Contextual Retrieval** (2024). Prepending chunk context before indexing.
- The **Ragas** paper and documentation. Know what its metrics measure and where they do not apply.
- **FinanceBench** (benchmark of questions over public-company filings). Shows how naive RAG pipelines struggle on this exact kind of task, a useful reality check and a source of example questions.
- Datasets such as **FinQA** and **TAT-QA** for numerical reasoning over financial tables. Read to understand failure modes, even if you do not use them.
- Documentation of **Docling**, **Instructor**, and **Qdrant's hybrid search** guides. You will be using them, so read the docs before the tutorials.
- Hamel Husain's writing on **evals** for LLM products. Practical error analysis, which maps directly to your error-taxonomy approach.


# Plan and tasks backlog: complete ticket breakdown

**Sizes (ceilings, not targets):** `S` is at most 1.5 h and `M` is at most 3 h. Anything bigger has already been split.

**Ticket types:**
- `STUDY`: learn something, with a written artifact as output.
- `DECISION`: write an ADR or contract that unblocks others.
- `SPIKE`: a time-boxed experiment whose output is a measured decision, not production code.
- `POC`: a thin end-to-end proof on real data that a risky idea works.
- `BUILD`, `TEST`, `DOC`: as named.

**Working rules:**
- Every `BUILD` ticket ships with its tests and log lines.
- Every `SPIKE` ends with numbers and a one-paragraph ADR.
- From E4 onward, run the eval after each merge so regressions show up immediately.

---

## E0: Foundations & contracts
*Needs: nothing. Gate: `make check` is green in CI and the ports and fakes exist.*

- **E0-01** `BUILD` `S`: Create the repository with a Hexagonal layout (domain, ports, adapters, app), ruff, mypy, pytest and pre-commit so that `make check` passes on the empty project.
- **E0-02** `BUILD` `S`: Add a GitHub Actions workflow that runs lint, type-check and unit tests on every push.
- **E0-03** `BUILD` `M`: Define the port interfaces (DocumentParser, Chunker, Embedder, SparseEncoder, VectorStore, LLMClient, Validator, AuditStore) as typed Protocols whose docstrings state each contract and failure mode.
- **E0-04** `BUILD` `M`: Implement deterministic in-memory fakes for LLMClient, Embedder and VectorStore so the whole pipeline can be tested offline.
- **E0-05** `BUILD` `S`: Add a typed settings module (pydantic-settings) holding secrets and the pinned model, parser, chunker and prompt versions.
- **E0-06** `BUILD` `S`: Add structured JSON logging that stamps every line with `run_id` and `doc_id` through a context variable.
- **E0-07** `DECISION` `S`: Write ADR-001 defining what "deterministic" means for this project (validated envelope, fail-closed, pinned versions) and listing explicit non-goals.
- **E0-08** `BUILD` `S`: Add a docker-compose file that starts Postgres and the app with one command, leaving a slot for the vector store chosen in E6.

---

## E1: Domain knowledge & metric contract
*Needs: nothing (runs parallel to E0). Gate: Metric Contract v1 and the KPI Measurement Protocol are written and the ontology module is merged.*

- **E1-01** `STUDY` `M`: Read two 10-Ks and one 10-Q from different industries and annotate where the five metrics, unit headers and footnotes appear.
- **E1-02** `STUDY` `S`: Hand-compute operating margin for one filing and derive a single quarter's capex from the year-to-date cash-flow figures in a 10-Q.
- **E1-03** `STUDY` `S`: Pull one company's facts from the SEC structured-data API and map five XBRL concepts to the statement lines you annotated.
- **E1-04** `DECISION` `M`: Write Metric Contract v1 specifying, per metric, label synonyms, source statement, period rule, sign convention, scale handling and XBRL concept IDs.
- **E1-05** `DECISION` `S`: Decide and document the EBITDA policy (reported non-GAAP, derived, or both as separately labelled outputs) with formulas and required inputs.
- **E1-06** `DECISION` `S`: Decide and document the exact definitions of capital expenditures and net income (included lines, "attributable to" variant, sign).
- **E1-07** `DECISION` `M`: Write the period model (fiscal vs calendar, three-month vs nine-month, YTD handling, restatement policy) with ten worked examples.
- **E1-08** `BUILD` `M`: Encode Metric Contract v1 as a versioned, typed ontology module with a loader and unit tests.
- **E1-09** `DECISION` `M`: Write the KPI Measurement Protocol defining, per KPI, the metric, level (child or parent), query set, sample size and pass threshold, including how precision@5 is defined when only one relevant parent exists.

---

## E2: Golden dataset & evaluation harness
*Needs: E1-04, E1-07, E1-09. Gate (M1): golden set locked, harness reports metrics, slices and error tags, and CI fails on regression.*

**Order tip:** do the "v0 subset" (E2-01, 02, 03, 04, 09, 11, 12, 14) before E3, and the rest in parallel with E4.

- **E2-01** `DECISION` `S`: Select 15 filings (10-K and 10-Q mix) spanning industries, fiscal year-ends, layouts, one restatement and one low-quality scan, and record why each was chosen.
- **E2-02** `BUILD` `S`: Download the selected filings into a versioned data directory with a checksum manifest.
- **E2-03** `BUILD` `M`: Write a script that pulls XBRL facts for the selected filings and emits candidate gold values per filing, metric and period.
- **E2-04** `BUILD` `M`: Hand-verify candidate gold values for filings 1 to 5 against the PDFs, recording the page and printed text for each value.
- **E2-05** `BUILD` `M`: Hand-verify candidate gold values for filings 6 to 10 the same way.
- **E2-06** `BUILD` `M`: Hand-verify candidate gold values for filings 11 to 15 the same way.
- **E2-07** `BUILD` `S`: Add derived gold values (operating margin, derived EBITDA, YTD-to-quarter capex) computed from verified components with the formula recorded.
- **E2-08** `BUILD` `M`: Author refusal queries per filing (metric absent, wrong period, wrong company) with the expected `not_found` outcome.
- **E2-09** `BUILD` `S`: Define the golden-query JSONL schema with slice tags (document, table type, scale, period type, difficulty) and a validator script.
- **E2-10** `BUILD` `M`: Generate the full query set (at least 150, including paraphrased variants), split it into dev and held-out test, and lock the test split by checksum.
- **E2-11** `BUILD` `M`: Implement the numeric normalizer (printed text, scale and sign to Decimal) as pure functions with Hypothesis property tests.
- **E2-12** `BUILD` `S`: Implement the exact-match scorer comparing predicted and gold value, scale, period and status.
- **E2-13** `BUILD` `M`: Implement retrieval metrics (hit@k, parent-level precision@k, MRR, nDCG) over a generic ranked-list interface.
- **E2-14** `BUILD` `M`: Implement the eval runner that executes any pipeline on a query split and writes a results file stamped with config hash and git SHA.
- **E2-15** `BUILD` `M`: Implement slice reports and the error-taxonomy tagger (PARSE, RETRIEVAL_MISS, RANKING_MISS, WRONG_CONTEXT, EXTRACTION, NORMALIZATION, FALSE_REFUSAL, FALSE_ACCEPT).
- **E2-16** `BUILD` `M`: Implement oracle modes (gold parse, gold chunks) so each stage can be evaluated in isolation.
- **E2-17** `BUILD` `S`: Add bootstrap confidence intervals and rule-of-three upper bounds to every eval report.
- **E2-18** `BUILD` `S`: Add a CI eval job that compares results to a stored baseline and fails on regressions beyond a threshold.
- **E2-19** `TEST` `S`: Unit-test the scorer and metrics against hand-built toy cases with known answers.

---

## E3: Walking skeleton (tracer bullet)
*Needs: E0, E2 v0 subset. Gate (M0): one small 10-Q runs end-to-end and baseline-0 is stored.*

- **E3-01** `BUILD` `S`: Implement a naive PyMuPDF adapter that returns per-page text with page numbers.
- **E3-02** `BUILD` `S`: Implement a naive fixed-size chunker adapter that keeps page metadata.
- **E3-03** `BUILD` `M`: Implement the embedder adapter and an in-memory dense index so retrieval works end-to-end without extra infrastructure.
- **E3-04** `BUILD` `M`: Implement the Instructor-based LLM adapter with a minimal metric schema at temperature 0.
- **E3-05** `BUILD` `M`: Wire ingest and query orchestration behind a CLI command that emits JSON.
- **E3-06** `TEST` `M`: Run the skeleton on one small 10-Q through the eval runner and store the result as baseline-0.
- **E3-07** `DOC` `S`: Write down the five most frequent failures in baseline-0 as the seed of the error histogram.

---

## E4: Ingestion & parsing (Bronze → Silver)
*Needs: E0, E2 v0. This is your highest-risk epic, so do the contract, bake-off and POC (E4-01 to E4-11) first. Gate (M2): the chosen parser passes cross-footing on the target tables and the parse-quality report is published.*

- **E4-01** `DECISION` `M`: Define the Silver table IR (cells with row, column, span, header path, bbox, footnote links, scale, caption) as a JSON schema with three hand-written examples.
- **E4-02** `BUILD` `S`: Implement Pydantic models and schema validation for Silver elements (page, heading, paragraph, table).
- **E4-03** `BUILD` `S`: Implement the immutable Bronze store (raw PDF, SHA-256, metadata) behind an adapter.
- **E4-04** `SPIKE` `M`: Assemble a 10-page parser test pack (multi-level header table, page-spanning table, footnote-heavy table, scanned page, two-column MD&A) with hand-made expected output.
- **E4-05** `SPIKE` `M`: Run Docling on the test pack and score table cell accuracy and cross-footing pass rate.
- **E4-06** `SPIKE` `M`: Run a second layout-aware parser (Marker, Unstructured or LlamaParse) on the pack with the same scoring.
- **E4-07** `SPIKE` `M`: Prototype a PyMuPDF/pdfplumber word-position table reconstruction on the pack with the same scoring.
- **E4-08** `SPIKE` `S` *(optional)*: Run Google Document AI on the pack and record accuracy, cost per page and data-egress implications.
- **E4-09** `DECISION` `S`: Write the ADR choosing the primary and fallback parser from the bake-off scores.
- **E4-10** `BUILD` `M`: Implement the primary parser adapter that outputs Silver IR with page, bbox, element type and `parser_version`.
- **E4-11** `POC` `M`: Prove that one real multi-year income statement survives parse, IR and cross-footing with correct header paths and scale.
- **E4-12** `BUILD` `M`: Implement page-type classification (native, scanned, mixed) and per-page routing.
- **E4-13** `BUILD` `M` *(optional, only if the golden set contains scans)*: Implement the OCR adapter for scanned pages, capturing bbox and confidence.
- **E4-14** `BUILD` `M`: Reconstruct the section hierarchy (Item and subsection headings) for 10-K and 10-Q structure.
- **E4-15** `BUILD` `M`: Flatten multi-level column headers into a header path per cell.
- **E4-16** `BUILD` `S`: Detect unit and scale statements ("in millions, except per share") and attach them to the right tables.
- **E4-17** `BUILD` `M`: Detect footnote markers, strip them from numeric text and link footnote text to cells.
- **E4-18** `BUILD` `M`: Clean numeric cells (parentheses negatives, dashes as zero, split currency symbols, thousand separators) while preserving the original printed text.
- **E4-19** `BUILD` `M`: Stitch page-spanning tables, including header carry-over detection.
- **E4-20** `BUILD` `S`: Capture row hierarchy from indentation and parent rows such as "Operating expenses:".
- **E4-21** `BUILD` `S`: Classify each table by statement type (income, balance, cash flow, notes, other).
- **E4-22** `BUILD` `M`: Implement the cross-footing checker that flags tables whose line items do not sum to printed totals.
- **E4-23** `BUILD` `M`: Implement the digit-level comparison between the native text layer and parsed table cells per region.
- **E4-24** `BUILD` `S`: Implement coverage checks (page count, empty pages, missing scale) that emit structured warnings.
- **E4-25** `BUILD` `S`: Implement the versioned, idempotent Silver store.
- **E4-26** `BUILD` `M`: Implement the async ingestion job (queue, worker, stage status, idempotent retry) from Bronze to Silver.
- **E4-27** `TEST` `M`: Add snapshot tests for the parser pack and a regression test for each footnote, scale and negative-number case.
- **E4-28** `TEST` `S`: Parse all golden filings and publish a parse-quality report (cross-footing pass rate, scale coverage, warnings) by slice.
- **E4-29** `BUILD` `M`: Parallelize page-level parsing with per-page caching so a 200-page filing ingests within a stated time budget.

---

## E5: Chunking & enrichment (Silver → Gold)
*Needs: E4-01, E4-02. Develop against hand-made Silver examples until E4 is done. Gate: parent-child chunks with context prefixes exist for all golden filings and the property tests pass.*

- **E5-01** `BUILD` `S`: Define the Gold chunk schema (child and parent ids, parent type, raw and enriched text, metadata, provenance) with examples.
- **E5-02** `BUILD` `M`: Extract document-level metadata (company, ticker, filing type, fiscal year, period end) from the filing cover page.
- **E5-03** `BUILD` `M`: Build structure-aware parents (tables atomic, sections or pages for prose).
- **E5-04** `BUILD` `M`: Build table-row children that carry full flattened header paths.
- **E5-05** `BUILD` `S`: Generate the deterministic context prefix (company, filing, period, statement, unit, column headers) for every child.
- **E5-06** `POC` `M`: Prove in a notebook that, on one cash-flow table, a row child is retrieved with its header context and returns the whole table as its parent.
- **E5-07** `BUILD` `S`: Build paragraph and sentence children with sentence-boundary splitting and size limits.
- **E5-08** `BUILD` `S`: Add a parent size guard that splits oversized tables into sub-parents while repeating headers.
- **E5-09** `BUILD` `S`: Implement child-to-parent linkage and a deduplication utility that collapses multiple child hits into one parent, keeping the best score.
- **E5-10** `BUILD` `S`: Annotate every golden query's evidence page and table with the resulting parent IDs so parent-level metrics work.
- **E5-11** `TEST` `M`: Add property tests asserting every child has a parent, parent text contains the child's source, and no row lacks header context.
- **E5-12** `SPIKE` `M`: Compare child serializations for embedding (pipe-delimited, natural-language sentence per row, key-value) on retrieval metrics.
- **E5-13** `BUILD` `S`: Implement the versioned Gold store.
- **E5-14** `TEST` `S`: Run chunking on all golden filings and report chunk counts, size distribution and context-prefix coverage.

---

## E6: Indexing & hybrid retrieval
*Needs: E5-01, E2 harness. Gate (M3): hybrid + filters beats dense-only on your protocol's metrics by a recorded margin.*

- **E6-01** `SPIKE` `M`: Load 5k chunks into Qdrant, pgvector and optionally OpenSearch, and compare hybrid-query support, filter speed and operational effort.
- **E6-02** `DECISION` `S`: Write the ADR choosing the vector store from the spike evidence.
- **E6-03** `BUILD` `M`: Implement the VectorStore adapter (collection schema with dense vector, sparse vector, payload metadata and filter indexes).
- **E6-04** `SPIKE` `M`: Compare three embedding models (hosted, small open-weights, larger) on dense-only hit@k and MRR over the dev set.
- **E6-05** `BUILD` `S`: Implement the Embedder adapter with batching, retries and a cache keyed by text hash and model.
- **E6-06** `BUILD` `M`: Implement the BM25 sparse path with a tokenizer that preserves numbers, tickers and hyphenated terms.
- **E6-07** `POC` `M`: Prove in a notebook that dense plus BM25 fused with RRF returns the correct capex row for five hand-picked queries on one filing.
- **E6-08** `SPIKE` `M` *(optional)*: Test SPLADE against BM25 on the dev set, measuring gain versus indexing cost.
- **E6-09** `BUILD` `M`: Implement the idempotent indexing job (Gold to dense and sparse upserts keyed by chunk id and versions).
- **E6-10** `BUILD` `S`: Implement metadata pre-filters (`doc_id`, `fiscal_year`, `filing_type`, `statement_type`, `element_type`).
- **E6-11** `BUILD` `S`: Implement production RRF with configurable k and per-ranker weights, tested against hand-computed rankings.
- **E6-12** `BUILD` `M`: Implement the hybrid retrieval service that returns ranked children with per-ranker ranks and scores.
- **E6-13** `BUILD` `S`: Implement parent assembly (dedupe, order, token budget) on top of retrieval results.
- **E6-14** `BUILD` `S`: Implement ontology-based synonym expansion and statement-type steering for the sparse query.
- **E6-15** `TEST` `M`: Run the ablation (dense, BM25, hybrid, hybrid with filters, with expansion) and report hit@k, parent precision@k and MRR.
- **E6-16** `SPIKE` `M`: Tune k, ranker weights and candidate depth on the dev set only, recording the chosen values with their evidence.
- **E6-17** `SPIKE` `S` *(optional)*: Measure the gain of a cross-encoder reranker on top-N candidates to inform Project 6.
- **E6-18** `TEST` `M`: Inspect every dev-set retrieval miss, tag its root cause and convert recurring causes into backlog tickets.

---

## E7: Query understanding
*Needs: E1-08, E6-10. Gate: the query parser reaches your target accuracy on the golden queries, including messy paraphrases.*

- **E7-01** `BUILD` `S`: Define the typed Query model (company, period, metric list, intent) and its parsing contract.
- **E7-02** `BUILD` `S`: Implement the company and filing resolver that maps names and tickers to indexed `doc_id`s.
- **E7-03** `BUILD` `M`: Implement the period resolver that converts phrases like "fiscal 2024", "Q3" and "nine months" into period end and duration using each filing's fiscal calendar.
- **E7-04** `BUILD` `S`: Implement the rule-based metric detector using the ontology with synonym and fuzzy matching.
- **E7-05** `SPIKE` `M`: Compare an Instructor-based LLM query parser with the rules on accuracy and latency over the golden queries.
- **E7-06** `DECISION` `S`: Choose rules, LLM or rules-with-LLM-fallback and record it in an ADR.
- **E7-07** `BUILD` `S`: Return typed clarification or refusal results for ambiguous queries (several matching filings, missing period) instead of guessing.
- **E7-08** `BUILD` `M`: Implement routing between direct lookup, derived metrics (margin, EBITDA, YTD quarter) and refusal.
- **E7-09** `TEST` `S`: Evaluate query-parsing accuracy on the golden set, including messy paraphrases.

---

## E8: Extraction, schema & validation
*Needs: E0-04, E2-11, E5-01. E8-01 to E8-03 can start early against hand-made context. Gate (M4): oracle-mode extraction is correct or refuses on the dev set, with zero ungrounded values.*

- **E8-01** `BUILD` `S`: Implement the Pydantic MetricExtraction, Evidence and Period schemas with evidence-before-value ordering and found / not_found / ambiguous status.
- **E8-02** `BUILD` `S`: Implement the model-level validator rules (FOUND requires evidence, non-FOUND requires a reason) with unit tests.
- **E8-03** `POC` `M`: Prove on one real context that the grounding check rejects a deliberately hallucinated number and accepts the true one.
- **E8-04** `BUILD` `M`: Write the v1 extraction prompt template (metric definition injection, absence allowed, delimiters with page and table ids), versioned and hashed.
- **E8-05** `BUILD` `M`: Implement the context formatter that renders parent chunks with ids under a token budget.
- **E8-06** `SPIKE` `M`: Compare table renderings in the prompt (Markdown, HTML, key-value rows) on extraction accuracy over gold chunks.
- **E8-07** `BUILD` `M`: Implement the extraction service using Instructor with schema-constrained output, temperature 0, a pinned model and a capped `max_retries`.
- **E8-08** `BUILD` `S`: Implement the production grounding validator checking that the quote appears in the retrieved parent text after unicode and whitespace normalization.
- **E8-09** `BUILD` `S`: Implement the validator checking that `printed_value` appears in the quote and round-trips through the normalizer.
- **E8-10** `BUILD` `S`: Implement the validator checking that page and table id match the source chunk.
- **E8-11** `BUILD` `S`: Implement the validator checking that the claimed scale matches the Silver table scale.
- **E8-12** `BUILD` `M`: Implement the validator checking that the value sits under the requested period column using cell header paths.
- **E8-13** `BUILD` `S`: Implement sign-convention and unit normalization to canonical Decimal per the Metric Contract.
- **E8-14** `BUILD` `S`: Implement soft plausibility checks (magnitude versus revenue, margin range) that produce warnings, not failures.
- **E8-15** `BUILD` `M`: Implement the retry loop that feeds failed-validator messages back to the model and logs each retry with its reason.
- **E8-16** `BUILD` `S`: Implement the typed fail-closed result path (`not_found` or `ambiguous` with a reason) used when retries are exhausted.
- **E8-17** `BUILD` `M`: Implement deterministic derived-metric calculators (operating margin, derived EBITDA, YTD-to-quarter) with input lineage.
- **E8-18** `BUILD` `M`: Implement the reported non-GAAP EBITDA path that retrieves the reconciliation table and labels the result as reported.
- **E8-19** `BUILD` `S`: Implement multi-metric orchestration (five parallel single-metric calls or one combined call) behind a flag.
- **E8-20** `SPIKE` `M`: Compare parallel per-metric calls against a single five-field call on accuracy and latency.
- **E8-21** `TEST` `M`: Run oracle-mode evaluation (gold chunks) and report extraction accuracy, grounding pass rate and retry rate.
- **E8-22** `TEST` `M`: Write adversarial tests (answer absent, wrong-year column, scale trap, footnote-glued number, conflicting duplicates) that must end in a correct answer or a refusal.
- **E8-23** `SPIKE` `M`: Compare a small fast model against a frontier model on accuracy, latency and cost over the dev set.
- **E8-24** `BUILD` `M` *(optional)*: Implement an independent second-opinion extraction (different prompt or model) to produce a self-consistency signal.
- **E8-25** `TEST` `S`: Add Hypothesis property tests for the normalizer and validators.

---

## E9: Provenance, confidence & audit
*Needs: E8-07, E6-12. E9-01 and E9-08 are contracts, so do them early. Gate: 100% of golden responses carry full provenance and a resolvable audit record, and confidence is calibrated.*

- **E9-01** `BUILD` `S`: Define the audit record schema (run_id, doc/parser/chunker versions, retrieved ids with per-ranker ranks and scores, prompt hash, model and params, raw response, validator results, retries, final output).
- **E9-02** `BUILD` `M`: Implement the append-only Postgres AuditStore with insert-only permissions and a content hash per record.
- **E9-03** `BUILD` `S`: Resolve provenance for every metric to page, bbox and source snippet.
- **E9-04** `BUILD` `M`: Implement the confidence signal collector (validators passed, ranker agreement, parse integrity, second-opinion agreement, corroborating prose).
- **E9-05** `BUILD` `S`: Implement the composite confidence label (high, medium, low) and its rule set.
- **E9-06** `TEST` `M`: Run a calibration study comparing labels to actual correctness on the dev set, adjust thresholds and publish a reliability table.
- **E9-07** `BUILD` `M`: Implement a replay tool that re-runs a query from its audit record and diffs the outputs.
- **E9-08** `BUILD` `S`: Define the final response JSON contract (normalized value, printed value, scale, currency, period, status, evidence, confidence, `audit_id`).
- **E9-09** `TEST` `S`: Add an audit-completeness test that every golden response has all required fields and a resolvable audit record.

---

## E10: Serving, latency & observability
*Needs: E8 core, E9-08. Gate: p95 latency is within 3.5 s on filings up to 50 pages and staging is deployed with a passing smoke test.*

- **E10-01** `BUILD` `M`: Implement the FastAPI app with endpoints to ingest a document, poll its status and request an extraction.
- **E10-02** `BUILD` `M`: Implement ingestion job handling with status polling and idempotency keys.
- **E10-03** `BUILD` `S`: Define request, response and error models with generated OpenAPI docs.
- **E10-04** `BUILD` `S`: Add per-stage timing spans to the query path.
- **E10-05** `BUILD` `S`: Add a latency report test showing p50 and p95 per stage against the 3.5 s budget on filings up to 50 pages.
- **E10-06** `SPIKE` `M`: Profile the query path and choose the top latency levers (input tokens, output tokens, embedding, search).
- **E10-07** `BUILD` `M`: Add embedding, retrieval-result and provider prompt caches with hit-rate metrics.
- **E10-08** `BUILD` `S`: Shrink output tokens through a compact schema and quote-length cap, and measure the latency effect.
- **E10-09** `BUILD` `M`: Add async fan-out of metric calls with connection pooling and a timeout-and-fallback policy.
- **E10-10** `BUILD` `S`: Add health and readiness endpoints, structured error handling and basic rate limiting.
- **E10-11** `BUILD` `M`: Containerize the service and deploy it to Cloud Run staging with a smoke test.
- **E10-12** `BUILD` `M` *(optional)*: Add OpenTelemetry tracing keyed by `run_id` (and Langfuse if desired) so it can be reused in Project 4.
- **E10-13** `BUILD` `S` *(optional)*: Record per-query token and embedding cost in the audit record and metrics.

---

## E11: Hardening, scale & final evaluation
*Needs: E8, E9, E10. Gate (M5): held-out results are recorded with intervals, failure modes are documented, and every found bug is a regression test.*

- **E11-01** `TEST` `M`: Ingest the 200-page filings end-to-end and record parse time, failures and memory use.
- **E11-02** `TEST` `M`: Run the full dev-set evaluation and write the error-taxonomy histogram with a ranked top-10 fix list.
- **E11-03 to E11-08** `BUILD` `M` ×6 *(reserved)*: Each ticket takes the next-highest error class from the latest histogram, fixes it, adds a regression test and re-runs the eval.
- **E11-09** `TEST` `M`: Run chaos tests (LLM timeout, malformed response, vector store down, empty retrieval) and verify every case fails closed.
- **E11-10** `TEST` `M`: Load-test the query endpoint at increasing concurrency and record latency percentiles and error rates.
- **E11-11** `TEST` `S`: Run the held-out test split once and record the final KPI results.
- **E11-12** `DOC` `M`: Write the KPI results report with per-slice breakdown, confidence intervals and honest limitations.
- **E11-13** `TEST` `S`: Freeze every bug found and fixed as a permanent regression test.
- **E11-14** `BUILD` `S`: Add a nightly CI eval with trend tracking.

---

## E12: Documentation & portfolio packaging
*Needs: E11-11. Gate: someone else can read, run and judge the project in 30 minutes.*

- **E12-01** `DOC` `S`: Write the README with an architecture diagram, quickstart and the results table.
- **E12-02** `DOC` `S`: Compile the ADR index and write a one-page "why determinism" design rationale.
- **E12-03** `DOC` `S`: Write the evaluation methodology doc (golden set construction, metrics, error taxonomy, statistics).
- **E12-04** `BUILD` `M`: Build a demo notebook or script showing a successful extraction with provenance, a refusal and a caught hallucination.
- **E12-05** `DOC` `M` *(optional)*: Publish a technical write-up of lessons learned, aimed at AI Engineer hiring managers.
- **E12-06** `DOC` `S`: Write the handoff note listing reusable components and open items for Project 6 (reranking, temporal filtering, Ragas).

---

## Execution order, milestones and totals

| Wave | Epics / tickets | Milestone |
|---|---|---|
| A | E0, E1, then E2 v0 subset | none |
| B | E3 | **M0**: walking skeleton and baseline-0 |
| C | Rest of E2, plus E4-01 to E4-11 and E8-01 to E8-03 in parallel | **M1**: measurement online |
| D | Rest of E4, then E5 | **M2**: trustworthy parse and Gold chunks |
| E | E6, E7 | **M3**: retrieval proven by ablation |
| F | Rest of E8, then E9 | **M4**: verified, grounded extraction |
| G | E10, E11, E12 | **M5**: production shape and held-out results |

The parallelism comes from contracts. Once E4-01 (Silver IR), E5-01 (Gold chunk) and E9-01 / E9-08 (audit and response) are frozen, you can build E8 against hand-made chunks while E4 is still unfinished.

| Epic | Tickets | Ceiling hours |
|---|---|---|
| E0 Foundations | 8 | 15 |
| E1 Domain & contract | 9 | 21 |
| E2 Golden set & harness | 19 | 45 |
| E3 Walking skeleton | 7 | 16.5 |
| E4 Parsing | 29 | 72 |
| E5 Chunking | 14 | 30 |
| E6 Retrieval | 18 | 43.5 |
| E7 Query understanding | 9 | 18 |
| E8 Extraction | 25 | 58.5 |
| E9 Audit & confidence | 9 | 19.5 |
| E10 Serving | 13 | 30 |
| E11 Hardening | 14 | 37.5 |
| E12 Docs | 6 | 12 |
| **Total** | **180** | **≈ 420** |

**How to read the totals:**
- **Ceiling vs. expected:** The ceiling assumes every ticket uses its full size. Realistically, expect about 70% of that, so around 290 deep hours, or roughly 80 to 85 deep days at your tracked average.
- **Optional tickets:** There are eight of them (E4-08, E4-13, E6-08, E6-17, E8-24, E10-12, E10-13, E12-05), worth about 20 ceiling hours. Skipping them is safe for the KPIs.
- **Why this is higher than my earlier estimate:** My earlier 134-hour figure was top-down. Writing individual tickets exposed the tests, spikes, calibration and documentation work that top-down estimates tend to hide. Plan with this bottom-up number.
- **Reserved tickets:** E11-03 to E11-08 are placeholders on purpose. You cannot know your top error classes until the E11-02 histogram exists, so write those six tickets then.
