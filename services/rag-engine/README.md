# Deterministic Financial & Regulatory RAG Engine (`services/rag-engine`)

## 1. Overview & Purpose

The `rag-engine` is a core microservice delivering layout-aware financial document parsing, multi-vector hybrid retrieval, and temporal regulatory search. It processes complex, multi-page SEC filings (10-K, 10-Q) and regulatory frameworks (SEC, FINRA, FATF/GAFILAT), extracting structured metrics into validated Pydantic models with cross-encoder reranking and temporal rule filtering.

## 2. Functional Requirements (FRs)

### FR-1: Layout-Aware Document Ingestion & OCR

* **FR-1.1:** Ingest unstructured multi-page financial PDFs (10-K, 10-Q, earnings reports, regulatory PDFs) up to 200 pages.
* **FR-1.2:** Parse complex tables into structured Markdown/HTML while preserving cell alignment, multi-column headers, and footnote associations without text truncations.

### FR-2: Hybrid Parent-Child Retrieval Pipeline

* **FR-2.1:** Maintain a hybrid vector index combining Dense Embeddings (Qdrant) and Sparse Search (BM25/SPLADE), merged via Reciprocal Rank Fusion (RRF).
* **FR-2.2:** Execute Parent-Child chunking: index granular child chunks (sentence/table row level) for precise vector matching while returning full parent chunks (section/page level) for LLM context continuity.
* **FR-2.3:** Integrate a post-retrieval cross-encoder re-ranking step (`Cohere Rerank v3`).

### FR-3: Temporal Regulatory Awareness

* **FR-3.1:** Index regulatory rulebooks with metadata fields for `Jurisdiction`, `Effective Date`, `Authority`, and `Topic Code`.
* **FR-3.2:** Support temporal metadata filters ensuring retrieval matches the active regulatory rule version corresponding to a specific transaction date.

### FR-4: Structured Output Validation & Schema Enforcement

* **FR-4.1:** Extract core financial metrics (Revenue, Operating Margin, Net Income, CapEx, EBITDA) into strongly typed Pydantic schemas.
* **FR-4.2:** Enforce automated retry loops (`Instructor` / `Pydantic`) to reject non-conforming model responses until output validates.
* **FR-4.3:** Output full source metadata (page number, source paragraph snippet, confidence score) for every extracted field.

## 3. Non-Functional Requirements (NFRs)

### NFR-1: Search Quality & Accuracy

* **NFR-1.1 (Context Precision):** $\ge 90\%$ on quantitative financial table lookups (@k=5) and $\ge 92\%$ on regulatory article retrieval (@k=3).
* **NFR-1.2 (Faithfulness / Hallucination Rate):** $\ge 0.95$ Ragas Faithfulness score; $0\%$ tolerance for hallucinated monetary values or misplaced decimals.
* **NFR-1.3 (Reranking Gain):** $\ge 25\%$ improvement in Mean Reciprocal Rank (MRR) after cross-encoder reranking over standard dense vector search.
* **NFR-1.4 (Schema Compliance):** $100\%$ valid JSON generation (0 runtime schema validation errors).

### NFR-2: Performance & Latency

* **NFR-2.1 (Extraction Latency):** $\le 3.5\text{ seconds}$ per extraction query for documents up to 50 pages.
* **NFR-2.2 (Search Latency):** $\le 2.0\text{ seconds}$ end-to-end for compliance search queries.

## 4. Tech Stack

* **Vector Store:** `Qdrant`
* **Sparse Index:** `BM25` / `FastEmbed`
* **Reranker:** `Cohere Rerank v3`
* **Validation:** `Instructor`, `Pydantic v2`
* **Eval Framework:** `Ragas`

---


## 1. Overview & Purpose

The `fine-tuning-pipeline` package houses the offline machine learning workflows for dataset synthesis, parameter-efficient fine-tuning (QLoRA), model quantization, and local edge deployment. It produces specialized Small Language Models (SLMs) for financial Named Entity Recognition (NER), intent classification, and privacy-preserving, on-premise table parsing.

## 2. Functional Requirements (FRs)

### FR-1: Synthetic Data Synthesis & Dataset Pipeline

* **FR-1.1:** Construct an instruction-tuning dataset ($\ge 5,000$ validated samples) containing raw transaction texts, SEC disclosures, and financial news tagged with entities (`Ticker`, `ISIN`, `Currency`, `Amount`, `Entity`, `Intent`).
* **FR-1.2:** Build a data generation pipeline producing synthetic distorted, non-standard financial tables, invoices, and ledger records paired with ground-truth target JSON extractions.

### FR-2: Parameter-Efficient Fine-Tuning (PEFT)

* **FR-2.1:** Fine-tune open-weights 7B–8B parameter models (Llama-3-8B, Qwen-2.5-7B) using QLoRA (4-bit quantization) with parameter updates restricted to adapter layers.
* **FR-2.2:** Utilize memory-optimized training frameworks (`Unsloth`) to allow full training loops to execute within local hardware limits ($\le 8\text{ GB}$ VRAM).

### FR-3: Model Quantization & Local Edge Export

* **FR-3.1:** Quantize fine-tuned adapter/merged weights to GGUF (4-bit/8-bit) and AWQ formats.
* **FR-3.2:** Export quantized weights directly into local serving engines (`vLLM`, `Ollama`) for 100% offline, privacy-preserving inference without external network dependencies.

### FR-4: Zero-Prompt Structure Compliance

* **FR-4.1:** The fine-tuned SLM must output raw, valid JSON entity structures directly without system prompt instruction bloat.

## 3. Non-Functional Requirements (NFRs)

### NFR-1: Model Performance & Accuracy

* **NFR-1.1 (Entity Extraction F1-Score):** $\ge 0.92$ on unseen financial test sets across Ticker, ISIN, Amount, and Currency tags.
* **NFR-1.2 (Structural JSON Accuracy):** $\ge 99.0\%$ valid JSON syntax output on zero-shot inference.
* **NFR-1.3 (Field Extraction Accuracy):** $\ge 95\%$ exact match rate on numerical fields and line-item descriptions from unseen invoice templates.
* **NFR-1.4 (Parsing Failures):** $< 0.5\%$ raw output JSON parse errors.

### NFR-2: Resource Efficiency & Economics

* **NFR-2.1 (VRAM Footprint):** $\le 8\text{ GB}$ VRAM consumption during peak batched local inference runs.
* **NFR-2.2 (Inference Cost Reduction):** $\ge 85\%$ cost reduction compared to frontier commercial APIs (GPT-4o / Claude 3.5 Sonnet) for NER tasks, reaching $100\%$ reduction for local statement parsing.

## 4. Tech Stack

* **Training Engine:** `Unsloth`, `PyTorch`, `Hugging Face PEFT / TRL`
* **Quantization Tools:** `llama.cpp` (GGUF), `AutoAWQ`
* **Dataset Management:** `Datasets`, `Pandas`
* **Evaluation:** `scikit-learn` (F1 metrics), `jsonschema` Validation