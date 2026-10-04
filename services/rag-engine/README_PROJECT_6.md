# Project 6: Multi-Asset Compliance & Regulatory RAG Engine

> Time-aware regulatory retrieval with cross-encoder re-ranking, so every answer cites rules that were actually in force on the date that matters.

**Module:** `services/rag-engine` | **Status:** Phase 1 | **Owner:** AI Engineering

---

## 1. Overview

This engine indexes regulatory frameworks (SEC, FINRA, FATF/GAFILAT) and answers compliance questions with **explicit article and clause citations**. Its defining capability is temporal awareness: given a transaction date, it only considers provisions that were active and not superseded on that date.

## 2. Problem Statement & Product Value

**The problem.** Compliance is inherently historical and jurisdictional:

- "Was this transaction compliant?" depends on which rule version applied *then*, not today.
- Regulations are amended, superseded, and layered across jurisdictions and authorities.
- Plain vector search retrieves semantically similar text regardless of whether it was in force.
- LLMs happily invent plausible-sounding article numbers, and a fabricated citation in a compliance context is worse than no answer.

**The value.**

| Value driver | Outcome |
|---|---|
| Correctness over time | Answers reflect the regulatory state at the transaction date |
| Citation integrity | Article numbers and clauses are retrieved, never invented |
| Retrieval quality | Re-ranking measurably improves ranking over plain vector search |
| Regression safety | A golden dataset catches quality drops when models or corpora change |

## 3. Target Users & Use Cases

**Personas:** compliance officers, AML/KYC analysts, legal operations, internal audit, and the Forensic Copilot (Project 8) as an automated consumer.

**Use cases**

1. **Historical compliance check.** "Under what rules should this March 2022 cross-border transfer have been reviewed?"
2. **Jurisdiction comparison.** Compare SEC vs. FATF/GAFILAT treatment of the same activity.
3. **Policy gap analysis.** Find which provisions apply to a product launching under a given jurisdiction and date.
4. **Citation-backed SAR support.** Supply regulatory references for narrative reports in Project 8.
5. **Regression monitoring.** Re-run the golden dataset after every embedding, reranker, or corpus change.

## 4. Product Fit

- **Extends Project 1's retrieval stack** with metadata filtering and cross-encoder re-ranking, showing maturity beyond baseline RAG.
- **Fits LATAM and global compliance contexts** by covering GAFILAT alongside US authorities.
- **Strong evaluation story.** The regression suite and measured MRR gain give concrete evidence of engineering rigor.

## 5. Architecture (High Level)

1. **Ingest and tag** documents with `Jurisdiction`, `Effective_Date`, `Authority`, `Topic`.
2. **Filter** candidates by target transaction date (exclude inactive or superseded provisions).
3. **Retrieve** with parent-child dense vector search.
4. **Re-rank** with Cohere Rerank v3.
5. **Assemble context and generate** with enforced citation mapping.
6. **Evaluate** continuously against a golden compliance dataset.

## 6. Functional Requirements

- **FR-2.1 Corpus Ingestion & Metadata Tagging.** Index regulations with `Jurisdiction`, `Effective_Date`, `Authority`, and `Topic`.
- **FR-2.2 Temporal Awareness Filtering.** Accept a historical transaction date and exclude provisions inactive or superseded at that date.
- **FR-2.3 Cross-Encoder Re-Ranking.** Re-rank parent-child dense candidates with Cohere Rerank v3 before context assembly.
- **FR-2.4 Regression Evaluation Suite.** Automated tests for retrieval quality and answer faithfulness against a golden compliance dataset.

## 7. Non-Functional Requirements

- **NFR-2.1 Citation Fidelity.** Every answer maps to explicit, non-invented article numbers and clauses.
- **NFR-2.2 Retrieval Precision.** Re-ranking yields at least a 25% MRR improvement over standard vector search.
- **NFR-2.3 Latency.** End-to-end generation completes in 2.0 s or less.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Context Precision (@k=3) | >= 92% | Golden dataset; relevant article in top 3 |
| Faithfulness (Ragas) | >= 0.95 | Ragas faithfulness; manual spot-check of citations |
| Reranking Gain | >= 25% MRR improvement | MRR with vs. without re-ranking, same queries |
| End-to-End Latency | <= 2.0 s | p95 across golden set |

## 9. Out of Scope & Risks

- **Out of scope:** legal advice, automated regulatory change monitoring, non-English corpora beyond those loaded.
- **Risk: wrong `Effective_Date` metadata** silently breaks temporal filtering. *Mitigation:* metadata validation at ingestion and sampled human review.
- **Risk: latency budget.** Re-ranking adds a network hop. *Mitigation:* limit candidate count before re-ranking.
- **Risk: golden set bias.** *Mitigation:* cover multiple jurisdictions, date ranges, and superseded-rule cases.
