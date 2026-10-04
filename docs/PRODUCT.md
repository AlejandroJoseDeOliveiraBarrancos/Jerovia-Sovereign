## Part 1: Platform Level (The Unified Product)

### 1. Platform Product Overview

**Platform Name:** *Jerovia-Sovereign*

**Product Positioning:** An **Enterprise-Grade GenAI Operating System for Financial Intelligence & Risk Automation**. It bridges non-deterministic Foundation Models with deterministic banking rules, low-latency infrastructure, and strict regulatory auditability.

### 2. Market Demand & Industry Pain Points

* **The "GenAI Reliability" Bottleneck:** Banks and fintechs cannot deploy standard commercial LLM wrappers because models hallucinate numbers, fail at exact financial math, and leak sensitive customer data.
* **Cost & Latency at Scale:** Sending millions of daily transaction categorization or parsing calls to proprietary APIs (GPT-4o, Claude 3.5 Sonnet) is economically unviable ($100k+/mo) and introduces $1\text{s}+$ latency.
* **Regulatory Compliance & Auditability:** Regulators (SEC, FINRA, FinCEN, GAFILAT) mandate complete audit trails for credit decisions, adverse action notices, and Suspicious Activity Reports (SARs). Black-box LLM decisions are illegal in regulated lending and compliance.

### 3. Core Platform Use Cases

1. **Automated Commercial Underwriting:** End-to-end evaluation of complex loan applications, parsing multi-page financial statements, calculating coverage ratios, and applying hard policy rules.
2. **Autonomous Fraud & AML Forensic Analysis:** Graph-based transaction monitoring, shell company mapping, news sentiment scanning, and auto-drafting audit-ready SARs.
3. **Institutional Compliance RAG:** Answering complex regulatory and legal queries across temporal rule sets with source citation down to the page and snippet.
4. **Local Financial Document Extraction:** Private, on-premise extraction of unstructured financial statements into typed JSON schemas using domain-adapted Small Language Models (SLMs).

### 4. Platform Architectural Specification

```
                          ┌─────────────────────────────────────────────────────────┐
                          │               Client Applications / APIs                │
                          └────────────────────────────┬────────────────────────────┘
                                                       │
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │               services/llm-gateway                      │
                          │   (vLLM, Redis Semantic Cache, OpenTelemetry Tracing)   │
                          └──────┬─────────────────────┬─────────────────────┬──────┘
                                 │                     │                     │
               ┌─────────────────┘                     │                     └─────────────────┐
               ▼                                       ▼                                       ▼
┌──────────────────────────────┐        ┌──────────────────────────────┐        ┌──────────────────────────────┐
│    apps/underwriting-agent   │        │     apps/forensic-copilot    │        │      services/rag-engine     │
│   (LangGraph State Machine)  │        │   (Multi-Agent Graph Swarm)  │        │ (Hybrid Parent-Child Search) │
└──────────────┬───────────────┘        └──────────────┬───────────────┘        └──────────────┬───────────────┘
               │                                       │                                       │
               └───────────────────────────────────────┼───────────────────────────────────────┘
                                                       │
                                                       ▼
                          ┌─────────────────────────────────────────────────────────┐
                          │               ml/fine-tuning-pipeline                   │
                          │     (Unsloth QLoRA, GGUF/AWQ Quantization, SLM Evals)   │
                          └─────────────────────────────────────────────────────────┘

```

### 5. Architectural Overview & Monorepo Layout

This repository houses **Jerovia Sovereign** (or **Aegis Ledger Systems**), an enterprise-grade GenAI platform for financial intelligence and risk automation. The monorepo separates stateful domain applications (`apps/`), shared retrieval and serving infrastructure (`services/`), and offline model post-training pipelines (`ml/`).

```
jerovia-ai/
├── apps/
│   ├── underwriting-agent/   # Projects 2 & 5: Credit Underwriting & Policy Verification
│   └── forensic-copilot/     # Project 8: Multi-Agent Fraud Investigation & Forensic Copilot
├── services/
│   ├── rag-engine/           # Projects 1 & 6: Deterministic Financial & Regulatory RAG Engine
│   └── llm-gateway/          # Project 4: Production LLMOps & Semantic Caching Proxy
└── ml/
    └── fine-tuning-pipeline/ # Projects 3 & 7: Financial NER, Intent & SLM Fine-Tuning Pipeline

```

---

## Part 2: Detailed Microservice Specifications

---

### Module 1: `services/rag-engine` (Projects 1 & 6)

#### 1. Product Concept & Market Demand

A high-precision, layout-aware Retrieval-Augmented Generation service designed specifically for financial disclosures, SEC filings, and regulatory rulebooks where standard dense vector search fails.

#### 2. Core Use Cases

* **Quantitative Document Extraction:** Extracting key financial metrics (Revenue, Operating Margin, Net Income, EBITDA) from 200-page 10-K/10-Q PDFs into validated JSON schemas.
* **Temporal Regulatory Search:** Querying legal frameworks (SEC, FINRA, FATF) where rules change over time, requiring metadata filtering by active rule dates.

#### 3. Product Specifications & Tech Stack

* **Architecture:** Hybrid Vector Search (Qdrant Dense Embeddings + BM25 Sparse Search) merged via Reciprocal Rank Fusion (RRF).
* **Chunking Strategy:** Parent-Child indexing (child chunks indexed for vector matching; parent sections returned for LLM context window continuity).
* **Reranking & Schema Enforcement:** Cohere Rerank v3 cross-encoder step followed by `Instructor` + `Pydantic` validation loops for zero schema failures.
* **Evaluation Harness:** `Ragas` framework measuring *Context Precision* and *Faithfulness*.

---

### Module 2: `apps/underwriting-agent` (Projects 2 & 5)

#### 1. Product Concept & Market Demand

A stateful credit analysis DAG (Directed Acyclic Graph) that automates commercial underwriting while strictly preventing LLM math hallucinations and unauthorized credit score overrides.

#### 2. Core Use Cases

* **Commercial Credit Evaluation:** Ingesting loan packages (tax returns, bank statements), calculating key solvency ratios (DSCR, DTI, Leverage), and rendering approval recommendations.
* **Adverse Action Citation:** Automatically generating legally binding rejection notices mapped to explicit policy clause violations.

#### 3. Product Specifications & Tech Stack

* **Orchestration:** `LangGraph` state machine with discrete execution nodes (*Ingestion*, *Ratio Calculation*, *Policy Matching*, *Decision Draft*).
* **Tool Isolation:** Sandboxed Python code execution for financial ratio calculations (LLMs are forbidden from mental math).
* **Deterministic Guardrails:** `NeMo Guardrails` enforcing mandatory rejection thresholds (e.g., automatic denial if $\text{DSCR} < 1.25$).
* **Auditability:** Immutable structured logging of every tool invocation and intermediate state transition.

---

### Module 3: `apps/forensic-copilot` (Project 8)

#### 1. Product Concept & Market Demand

An autonomous forensic accounting swarm that investigates suspicious transactions across entity networks, saving compliance teams up to 70% of manual research time.

#### 2. Core Use Cases

* **Laundering Topology Mapping:** Uncovering hidden relationships between shell companies, shared bank accounts, and high-risk entities.
* **Automated SAR Generation:** Drafting standardized Suspicious Activity Report (SAR) narratives for regulatory filings.

#### 3. Product Specifications & Tech Stack

* **Agent Network:** Autonomous multi-agent swarm (*Data Retrieval Agent*, *Graph Analysis Agent*, *OSINT/News Agent*, *Report Drafting Agent*).
* **Graph Database Integration:** Direct `Neo4j` Cypher querying to analyze transactional graph topologies.
* **Human-in-the-Loop (HITL):** State machine pause controls requiring a compliance analyst's manual sign-off before freezing accounts or submitting SARs.

---

### Module 4: `services/llm-gateway` (Project 4)

#### 1. Product Concept & Market Demand

An enterprise-grade, high-throughput model serving gateway and semantic caching proxy designed to cut API token costs by 85%+ and reduce inference latency to sub-20ms levels.

#### 2. Core Use Cases

* **High-Frequency Transaction Categorization:** Real-time cleaning and categorization of raw credit card merchant strings.
* **Semantic Caching:** Intercepting semantically similar prompt payloads upstream before hitting GPU or commercial cloud endpoints.

#### 3. Product Specifications & Tech Stack

* **Serving Engine:** Local open-weights model serving via `vLLM` featuring continuous batching and PagedAttention.
* **Caching Layer:** `Redis` vector cache (`GPTCache`) performing cosine similarity matching on incoming payloads.
* **Telemetry & Observability:** `OpenTelemetry` tracing integrated with `Langfuse` / `Arize Phoenix` tracking latency distributions, token usage, and cache hit ratios.

---

### Module 5: `ml/fine-tuning-pipeline` (Projects 3 & 7)

#### 1. Product Concept & Market Demand

An automated post-training pipeline for fine-tuning, quantizing, and deploying domain-adapted Small Language Models (SLMs) for specialized financial tasks without external data leakage.

#### 2. Core Use Cases

* **Financial NER & Intent Recognition:** Tokenizing financial entities (ISINs, Tickers, Currencies) from unstructured market feeds.
* **Privacy-Preserving On-Premise Parsing:** Fine-tuning an 8B parameter model to extract structured data from invoices completely offline.

#### 3. Product Specifications & Tech Stack

* **Dataset Engineering:** Synthetic data generation pipeline producing $\ge 5,000$ instruction pairs.
* **Fine-Tuning Framework:** Parameter-Efficient Fine-Tuning (PEFT) using `Unsloth` / `QLoRA` (4-bit quantization) optimized for 8 GB VRAM GPUs.
* **Quantization & Deployment:** Quantizing fine-tuned weights to GGUF and AWQ formats for local edge execution via `vLLM` or `Ollama`.