# Multi-Agent Fraud Investigation & Forensic Accounting Copilot (`apps/forensic-copilot`)

## 1. Overview & Purpose

The `forensic-copilot` is an autonomous multi-agent swarm engineered for financial crime investigation, anti-money laundering (AML) detection, and forensic accounting. Operating over a shared state graph, the swarm queries transactional graph databases, analyzes shell company network topologies, ingests external news feeds, and drafts compliance-ready Suspicious Activity Reports (SARs) with human-in-the-loop checkpoints.

## 2. Functional Requirements (FRs)

### FR-1: Autonomous Swarm Network Architecture

* **FR-1.1:** The system shall deploy four specialized agent roles operating over a shared state graph:
1. `Data Retrieval Agent`: Fetches raw transactional and ledger data.
2. `Graph Analysis Agent`: Analyzes relationship networks and transactional topologies.
3. `OSINT & News Agent`: Queries OSINT tools and news feeds for adverse media.
4. `Report Drafting Agent`: Synthesizes findings into regulatory narrative structures.


* **FR-1.2:** Agents shall autonomously pass tasks and state updates back and forth based on intermediate reasoning output.

### FR-2: Graph Database Integration & Network Analysis

* **FR-2.1:** The system shall interface with a Neo4j Graph Database to execute Cypher queries that trace entity relationships, shell company networks, shared bank accounts, and high-risk routing paths.
* **FR-2.2:** The `Graph Analysis Agent` shall identify money-laundering patterns including structuring, layering, round-tripping, and rapid velocity movement.

### FR-3: Suspicious Activity Report (SAR) Generation

* **FR-3.1:** The `Report Drafting Agent` shall automatically generate standardized SAR narrative drafts adhering to FinCEN/GAFILAT regulatory structures.
* **FR-3.2:** Every assertion, entity mention, and transaction reference in the narrative must cite explicit Transaction IDs, Account IDs, or OSINT source URLs.

### FR-4: Human-in-the-Loop (HITL) Interruption Points

* **FR-4.1:** The workflow engine shall enforce deterministic execution state pauses before executing high-impact actions (e.g., submitting a final SAR or recommending account freezes).
* **FR-4.2:** Human compliance officers must be provided an interactive interface to approve, edit, or reject the agent's proposed actions before the graph resumes execution.

## 3. Non-Functional Requirements (NFRs)

### NFR-1: Detection & Efficiency Performance

* **NFR-1.1 (Fraud Pattern Recall):** $\ge 90\%$ detection rate on synthetic benchmark laundering scenarios (structuring, layering, round-tripping).
* **NFR-1.2 (Efficiency Gain):** $\ge 70\%$ reduction in manual research time per flagged account compared to manual compliance workflows.
* **NFR-1.3 (False Positive Reduction):** $\ge 30\%$ reduction in non-actionable compliance alerts escalated to human investigators.

### NFR-2: Grounding & Auditability

* **NFR-2.1 (Citation Grounding):** $100\%$ of facts mentioned in generated SAR narratives must link directly to verified Transaction IDs or external OSINT sources.
* **NFR-2.2 (Traceability):** Full agent-to-agent message history and graph queries must be logged for regulatory examination.

## 4. Tech Stack

* **Agent Framework:** `LangGraph` / `CrewAI`
* **Graph Database:** `Neo4j` (Cypher Query Engine)
* **API Framework:** `FastAPI`
* **External Integration:** OSINT Web Search APIs, Sanctions List APIs
* **Upstream Dependencies:** `services/llm-gateway`

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
