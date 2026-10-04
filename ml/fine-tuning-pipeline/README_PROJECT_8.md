# Project 7: Financial Statement Parsing & Domain-Adapted Small Language Model (SLM)

> An 8B model trained on synthetic financial documents that parses messy tables and invoices fully offline, within 8 GB of VRAM.

**Module:** `ml/fine-tuning-pipeline` | **Status:** Phase 4 | **Owner:** ML Engineering

---

## 1. Overview

An end-to-end pipeline that synthesizes non-standard financial tables, distorted invoices, and ledger records with ground-truth JSON, then fine-tunes a 7B-8B SLM to reconstruct table structure and extract key-value pairs. The final model is quantized for low-VRAM hardware and runs with **zero outbound network calls**.

## 2. Problem Statement & Product Value

**The problem.**

- Real-world invoices and statements come in endless templates with skewed layouts, merged cells, and inconsistent labels.
- Labeled real financial documents are scarce and sensitive, so training data is hard to obtain.
- Many finance and legal environments forbid sending documents to third-party APIs.
- Per-page API costs add up quickly for document-heavy back offices.

**The value.**

| Value driver | Outcome |
|---|---|
| Privacy | 100% on-premises, air-gapped operation |
| Cost | 100% reduction in third-party API token cost for processed pages |
| Accessibility | Runs in 8 GB VRAM or less on commodity hardware |
| Accuracy | At least 95% exact match on numerical fields from unseen templates |
| Structure | At least 99.0% syntactically valid JSON in zero-shot use |

## 3. Target Users & Use Cases

**Personas:** accounts-payable and finance-ops teams, accounting/audit firms, banks and insurers with data-residency rules, and ML teams building private document AI.

**Use cases**

1. **Invoice processing** with non-standard or distorted layouts.
2. **Air-gapped statement parsing** where documents may never leave the premises.
3. **Ledger and table reconstruction** from irregular financial tables.
4. **Edge deployment** on workstations or small servers.
5. **Synthetic data reuse** to bootstrap new document types without exposing real customer data.

## 4. Product Fit

- **Complements Project 3.** Project 3 handles entities in text; Project 7 handles layout-heavy tabular documents.
- **Privacy-first alternative** to API-based document AI, which matters in regulated and LATAM on-prem contexts.
- **Demonstrates a full SLM lifecycle:** synthetic data, fine-tuning, quantization, and offline deployment.

## 5. Architecture (High Level)

1. **Synthetic data generator** for tables, distorted invoices, and ledgers, each paired with ground-truth JSON.
2. **Instruction fine-tuning** of a 7B-8B base.
3. **Quantization** to 4-bit/8-bit GGUF/AWQ.
4. **Offline inference runtime** with outbound network blocked.
5. **Evaluation** on held-out, unseen templates.

## 6. Functional Requirements

- **FR-8.1 Synthetic Data Pipeline.** Generate non-standard financial tables, distorted invoices, and ledger records with ground-truth JSON.
- **FR-8.2 Instruction Fine-Tuning Engine.** Fine-tune a 7B-8B SLM for key-value extraction and tabular structure reconstruction.
- **FR-8.3 Quantized Local Export.** 4-bit/8-bit GGUF/AWQ optimized for low-VRAM deployment.
- **FR-8.4 Offline Air-Gapped Operation.** 100% local inference with zero outbound network calls during extraction runs.

## 7. Non-Functional Requirements

- **NFR-8.1 VRAM Efficiency.** Peak usage during batched local inference stays at or under 8 GB.
- **NFR-8.2 Structural Validity.** At least 99.0% syntactically valid JSON in zero-shot runs.
- **NFR-8.3 Field Matching Accuracy.** At least 95% exact match on numerical fields and line-item descriptions from unseen templates.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Structural JSON Accuracy | >= 99.0% valid JSON | Strict parser over all zero-shot outputs |
| Field Extraction Accuracy | >= 95% exact match (numerical fields) | Unseen invoice templates held out from training |
| VRAM Footprint | <= 8 GB peak | GPU memory monitoring during batched inference |
| API Cost Reduction | 100% for processed pages | Network-egress audit: zero outbound calls during runs |

## 9. Out of Scope & Risks

- **Out of scope:** OCR from raw scans (assumes text or layout input is available), handwriting recognition, multi-language support beyond training data.
- **Risk: synthetic-to-real gap.** Accuracy on synthetic templates may not transfer to real documents. *Mitigation:* include a small real, anonymized evaluation set, and report both numbers.
- **Risk: 8 GB limit** constrains batch size and context length. *Mitigation:* test the target quantization against realistic page sizes.
- **Risk: air-gap claim must be verifiable.** *Mitigation:* enforce with network policy, not just application code.
