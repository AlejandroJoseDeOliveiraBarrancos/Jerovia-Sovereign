# Project 3: Fine-Tuned Llama 3 for Financial NER & Intent Recognition

> A QLoRA-tuned 7-8B model that emits clean JSON entities and intents directly, with no long prompts and a fraction of frontier-API cost.

**Module:** `ml/fine-tuning-pipeline` | **Status:** Phase 2 | **Owner:** ML Engineering

---

## 1. Overview

A post-training pipeline that fine-tunes Llama-3-8B or Qwen-2.5-7B with QLoRA to extract financial entities (`Ticker`, `ISIN`, `Currency`, `Amount`, `Entity`) and classify `Intent` from transaction strings, SEC disclosures, and financial news. The result is a compact model that outputs valid JSON directly, without prompt scaffolding, and runs on commodity GPUs.

## 2. Problem Statement & Product Value

**The problem.**

- Frontier models can do this task, but each call carries a long instruction prompt, per-token cost, and network latency.
- Prompted extraction is brittle; JSON formatting failures at scale break pipelines.
- High-volume, narrow tasks (entity extraction, intent routing) don't need a general-purpose giant model.
- Some data can't leave the organization's infrastructure.

**The value.**

| Value driver | Outcome |
|---|---|
| Cost | At least 85% lower cost per 1M tokens vs. commercial APIs |
| Speed | At least 80 tokens/s on consumer/cloud GPU hardware |
| Reliability | Under 0.5% JSON parse failures on unseen queries |
| Quality | At least 0.92 F1 on Ticker, ISIN, Amount, Currency |
| Simplicity | No lengthy system prompt required; the behavior lives in the weights |

## 3. Target Users & Use Cases

**Personas:** ML/AI engineers, fintech data teams, trading/research tooling teams, and platform teams who need cheap structured extraction at volume.

**Use cases**

1. **Transaction enrichment.** Normalize raw bank strings into entities and intents.
2. **News and disclosure parsing.** Tag tickers, ISINs, amounts, and currencies from filings and headlines.
3. **Intent routing.** Classify what a message or transaction represents, for downstream systems.
4. **High-volume batch extraction** where per-call API cost is prohibitive.
5. **Serving model** behind the LLM gateway (Project 4).

## 4. Product Fit

- **Core "post-training" proof point:** dataset engineering, QLoRA, evaluation, quantization, and deployment.
- **Strong fit for AI/LLM engineering roles:** it shows the full path from data to served model, not just API usage.
- **Feeds Project 4** as a cost-efficient model for the gateway.

## 5. Architecture (High Level)

1. **Dataset engineering:** at least 5,000 validated instruction pairs.
2. **QLoRA training:** 4-bit quantized base, adapter layers only (Unsloth-compatible).
3. **Evaluation:** F1 on unseen test sets plus parse-failure rate.
4. **Merge and quantize:** GGUF and AWQ exports.
5. **Serve:** via vLLM or Ollama.

## 6. Functional Requirements

- **FR-7.1 Instruction Dataset Engineering.** At least 5,000 validated pairs of transaction strings, SEC disclosures, and financial news tagged with `Ticker`, `ISIN`, `Currency`, `Amount`, `Entity`, `Intent`.
- **FR-7.2 QLoRA Fine-Tuning.** 4-bit quantization; update adapter layers exclusively.
- **FR-7.3 Quantization & Deployment.** Merge adapters; export GGUF and AWQ; package for vLLM or Ollama.
- **FR-7.4 Zero-Prompt Output Compliance.** Output valid JSON directly, without lengthy system prompts or wrapper instructions.

## 7. Non-Functional Requirements

- **NFR-7.1 Inference Speed.** At least 80 tokens/s on RTX 4090 / A10G / RTX 5060 Ti class hardware.
- **NFR-7.2 Cost Efficiency.** At least 85% token-cost reduction vs. commercial frontier APIs.
- **NFR-7.3 Output Schema Reliability.** Under 0.5% parse failures on unseen evaluation queries.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Entity Extraction F1 | >= 0.92 (Ticker, ISIN, Amount, Currency) | Held-out test set, never seen in training |
| Inference Speed | >= 80 tokens/s | Benchmark on target GPU with the quantized model |
| Cost Efficiency | >= 85% reduction per 1M tokens | Self-hosted cost model vs. current API pricing at equal volume |
| Schema Parse Failure | < 0.5% | Raw output parsed with a strict JSON schema validator |

## 9. Out of Scope & Risks

- **Out of scope:** general-purpose chat, multilingual support beyond the training data, real-time learning.
- **Risk: dataset leakage** inflates F1. *Mitigation:* deduplicate and split by source before training.
- **Risk: label noise.** *Mitigation:* validation pass and spot audits of the dataset.
- **Risk: cost comparison is sensitive to GPU utilization and API pricing.** *Mitigation:* document assumptions, and re-run against current pricing.
- **Risk: quantization degrades accuracy.** *Mitigation:* evaluate each exported format separately, not just the base adapter.
