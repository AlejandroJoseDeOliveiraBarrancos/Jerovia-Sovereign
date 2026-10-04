# Credit Underwriting & Policy Verification Agent (`apps/underwriting-agent`)

## 1. Overview & Purpose

The `underwriting-agent` is a stateful microservice responsible for automating commercial credit risk analysis and loan application policy verification. By orchestrating a Directed Acyclic Graph (DAG) of specialized nodes, the application ingests multi-source financial packages, computes solvency metrics through sandboxed execution environments, evaluates bank risk guidelines, and produces fully cited adverse action or approval recommendations.

## 2. Functional Requirements (FRs)

### FR-1: Multi-Source Application Package Ingestion

* **FR-1.1:** The service shall ingest and normalize commercial loan application packages containing tax returns, bank statements, balance sheets, and personal financial statements up to 100 pages per package.
* **FR-1.2:** Unstructured financial figures shall be routed to `services/rag-engine` for layout-aware table extraction before entering the agent state machine.

### FR-2: Stateful DAG Orchestration & Agent Architecture

* **FR-2.1:** The agent pipeline shall be implemented as a stateful graph (using `LangGraph`) with discrete, deterministic node execution for:
1. `Document Ingestion & Validation Node`
2. `Financial Ratio Calculation Node`
3. `Policy Base Search Node`
4. `Policy Evaluation Node`
5. `Decision & Narrative Generation Node`


* **FR-2.2:** Graph state transitions must be immutable and inspectable at runtime.

### FR-3: Deterministic Financial Computations

* **FR-3.1:** All financial solvency metrics—including Debt Service Coverage Ratio (DSCR), Debt-to-Income (DTI), Leverage Ratios, and Liquidity Ratios—shall be calculated strictly via sandboxed Python tools.
* **FR-3.2:** LLM nodes are strictly prohibited from performing mental arithmetic or modifying tool-calculated numerical values.

### FR-4: Policy Base Vector Verification

* **FR-4.1:** The agent shall query bank underwriting guidelines via `services/rag-engine`, utilizing metadata filters for loan type, jurisdiction, and collateral class.
* **FR-4.2:** Applicants' calculated financial metrics shall be compared against vector-retrieved underwriting thresholds using deterministic validation logic.

### FR-5: Policy Guardrails & Absolute Hard Stops

* **FR-5.1:** Hard guardrail policies (enforced via `NeMo Guardrails` or `Guardrails AI`) shall intercept and override LLM generation to force an automatic rejection if hard limits are violated (e.g., DSCR $< 1.25$).
* **FR-5.2:** Guardrail triggers must immediately halt the DAG and log the exact policy violation trigger code.

### FR-6: Audit Trail & Adverse Action Generation

* **FR-6.1:** The system shall produce an immutable, time-stamped JSON audit trail detailing every tool invocation, raw payload, state transition, and policy match.
* **FR-6.2:** Rejection notices (Adverse Action) and approval recommendations must explicitly cite exact policy clause code references and paragraph snippets.

## 3. Non-Functional Requirements (NFRs)

### NFR-1: Performance & Latency

* **NFR-1.1:** Total execution runtime for evaluating a complete 100-page commercial application package shall be $\le 120\text{ seconds}$.
* **NFR-1.2:** Individual Python ratio calculation tool calls shall execute within $\le 50\text{ ms}$.

### NFR-2: Accuracy & Reliability

* **NFR-2.1 (False Approval Rate):** $0\%$ false approvals (zero loan packages approved that breach explicit policy limits).
* **NFR-2.2 (Math Error Rate):** $0\%$ calculation error rate across all solvency ratios.
* **NFR-2.3 (Workflow Completion):** $\ge 98\%$ successful DAG completion rate without state lockup or unhandled exceptions under normal operating conditions.
* **NFR-2.4 (Citation Accuracy):** $100\%$ match between generated adverse action reasons and actual policy code triggers.

### NFR-3: Operational & System Quality

* **NFR-3.1 (API Reliability):** $< 1\%$ failure rate across all internal and external service/model invocations.
* **NFR-3.2 (Auditability Index):** $100\%$ of underwriting decisions back-linked to precise tool call logs.

## 4. Tech Stack

* **Orchestration:** `LangGraph`, `Python 3.11+`
* **Guardrails:** `NeMo Guardrails` / `Guardrails AI`
* **Data Validation:** `Pydantic v2`
* **Execution Environment:** Dockerized Sandboxed Python Runtime
* **Upstream Dependencies:** `services/rag-engine`, `services/llm-gateway`

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