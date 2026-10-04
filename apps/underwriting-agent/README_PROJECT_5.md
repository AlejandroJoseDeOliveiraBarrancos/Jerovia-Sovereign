# Project 8: Multi-Agent Fraud Investigation & Forensic Accounting Copilot

> A swarm of specialized agents that traces suspicious money flows through a graph database and drafts evidence-linked SARs, with a human officer approving every consequential action.

**Module:** `apps/forensic-copilot` | **Status:** Phase 4 | **Owner:** AI Engineering

---

## 1. Overview

The copilot investigates flagged accounts by coordinating four specialized agents (*Data Retrieval*, *Graph Analysis*, *OSINT/News*, *Report Drafting*) over a shared state graph. It queries Neo4j for entity relationships, shell-company networks, shared accounts, and circular flows, then drafts a FinCEN-style Suspicious Activity Report in which every claim links to a concrete transaction ID or OSINT source.

## 2. Problem Statement & Product Value

**The problem.**

- Financial-crime analysts lose most of their time gathering context across systems, not making judgments.
- Laundering patterns (structuring, layering, round-tripping) are *topological*; they hide in relationships, not single transactions.
- Alert queues are dominated by false positives, which wastes scarce investigator time.
- A SAR with unsupported claims is a regulatory and legal liability.

**The value.**

| Value driver | Outcome |
|---|---|
| Efficiency | At least 70% reduction in manual research time per flagged account |
| Detection | At least 90% recall on benchmark synthetic laundering scenarios |
| Alert quality | At least 30% fewer non-actionable alerts reaching investigators |
| Defensibility | 100% of SAR facts are grounded in verified records |

## 3. Target Users & Use Cases

**Personas:** AML/financial-crime investigators, compliance officers, forensic accountants, and fraud operations leads.

**Use cases**

1. **Shell-company network discovery.** Trace shared directors, addresses, and bank accounts across entities.
2. **Circular-flow / round-tripping detection.** Find funds returning to origin via intermediaries.
3. **Structuring detection.** Surface repeated sub-threshold deposits across related accounts.
4. **Adverse-media enrichment.** Pull OSINT/news context on counterparties.
5. **SAR drafting.** Produce a narrative with transaction-ID citations for officer review.
6. **Controlled enforcement.** Pause for human authorization before any account freeze or final submission.

## 4. Product Fit

- **Capstone project.** It integrates graph analysis, multi-agent orchestration, HITL control, and regulatory grounding (drawing on Project 6 for regulatory citations).
- **Shows responsible autonomy:** agents do the legwork, humans hold the authority.
- **Natural story for AML vendors and bank financial-crime teams.**

## 5. Architecture (High Level)

1. **Orchestrator** coordinating four agents over a shared state graph.
2. **Data Retrieval Agent** pulls account and transaction records.
3. **Graph Analysis Agent** runs Cypher queries on Neo4j.
4. **OSINT/News Agent** gathers external intelligence with source tracking.
5. **Report Drafting Agent** assembles the SAR with per-claim citations.
6. **HITL gates** pause execution for officer approval.

## 6. Functional Requirements

- **FR-5.1 Multi-Agent Collaboration Network.** Orchestrate *Data Retrieval*, *Graph Analysis*, *OSINT/News*, *Report Drafting* over a shared state graph.
- **FR-5.2 Graph Topology Querying.** Cypher queries on Neo4j for entity relationships, shell networks, shared accounts, and circular loops.
- **FR-5.3 SAR Draft Generation.** Narrative drafts following FinCEN structural guidelines, linking each claim to concrete transaction IDs.
- **FR-5.4 HITL Interruption.** Pause at approval gates; require officer authorization before account freezes or final SAR submission.

## 7. Non-Functional Requirements

- **NFR-5.1 Citation Grounding.** 100% of factual assertions link to verified transaction logs or OSINT sources.
- **NFR-5.2 Pattern Recall.** Identify benchmark synthetic laundering patterns (structuring, layering, round-tripping).
- **NFR-5.3 Operational Efficiency.** Reduce analyst manual research effort by 70% or more.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Fraud Pattern Recall | >= 90% on synthetic scenarios | Seeded laundering scenarios with known ground truth |
| Investigation Time Reduction | >= 70% | Timed comparison: baseline manual workflow vs. copilot-assisted |
| Citation Grounding | 100% of SAR facts linked | Automated check that each claim resolves to a transaction ID or OSINT source |
| False Positive Reduction | >= 30% drop in non-actionable alerts | Alert outcomes before vs. after copilot triage on the same alert set |

## 9. Out of Scope & Risks

- **Out of scope:** autonomous account freezes or SAR filing (always human-gated), real customer data in the demo environment.
- **Risk: ungrounded OSINT.** *Mitigation:* store source URLs and retrieval timestamps, and reject uncited claims.
- **Risk: prompt injection via scraped web content.** *Mitigation:* treat external content strictly as data.
- **Risk: privacy and tipping-off concerns.** *Mitigation:* synthetic data only, strict access controls, no automated customer-facing actions.
- **Risk: synthetic benchmarks overstate real-world recall.** *Mitigation:* state this limitation alongside reported results.