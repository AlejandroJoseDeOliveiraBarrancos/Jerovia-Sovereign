# Financial NER, Intent & SLM Fine-Tuning Pipeline (`ml/fine-tuning-pipeline`)

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