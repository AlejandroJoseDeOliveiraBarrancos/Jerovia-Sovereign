# Project 2: Multi-Agent Credit Underwriting & Risk Analysis Engine

> A stateful underwriting workflow where the LLM reasons and explains, but all math and policy decisions are executed by deterministic code.

**Module:** `apps/underwriting-agent` | **Status:** Phase 2 | **Owner:** AI Engineering

---

## 1. Overview

A LangGraph-based credit underwriting engine that moves each application through explicit stages (*Document Ingestion* -> *Ratio Calculation* -> *Policy Evaluation* -> *Decision Generation*). Financial ratios (DSCR, DTI, leverage) are computed only by sandboxed Python tools, and hard policy rules override any conflicting LLM output.

## 2. Problem Statement & Product Value

**The problem.**

- LLMs are unreliable at arithmetic, and a wrong DSCR is a wrong credit decision.
- Free-form agents can loop, stall, or skip steps, which is unacceptable in a regulated workflow.
- Credit decisions must be explainable: "why was this declined?" needs a traceable answer.
- Policy thresholds (e.g., DSCR < 1.25 means automatic rejection) cannot depend on model mood.

**The value.**

| Value driver | Outcome |
|---|---|
| Calculation integrity | 0% math error because the LLM never does arithmetic |
| Policy enforcement | Hard stops always win over LLM reasoning |
| Auditability | Every decision back-links to tool calls and state transitions |
| Operational stability | A DAG workflow with defined states avoids runaway agent behavior |

## 3. Target Users & Use Cases

**Personas:** credit analysts, underwriting managers, risk and model-governance teams, fintech lenders, and developers integrating underwriting as a service.

**Use cases**

1. **First-pass underwriting.** Produce ratios, policy results, and a draft decision for analyst review.
2. **Automatic hard-stop rejection.** Instantly reject packages that breach thresholds like DSCR < 1.25.
3. **Model-risk review.** A governance team replays any decision from its immutable audit log.
4. **Stress testing.** Run synthetic borrower sets to verify rule compliance before release.
5. **Upstream integration.** Consume Project 1's extracted financials as a trusted input.

## 4. Product Fit

- **Core agent pattern for the portfolio.** It demonstrates the "LLM as orchestrator, code as calculator" principle that regulated industries require.
- **Pairs with Project 5**, which adds multi-source package normalization and policy retrieval.
- **Enterprise-ready story.** Guardrails, sandboxing, and audit logs are the vocabulary of production AI in banking.

## 5. Architecture (High Level)

1. **LangGraph DAG** with discrete states and explicit transitions.
2. **Sandboxed Python tool layer** for DSCR, DTI, leverage ratios.
3. **Guardrails layer** (NeMo Guardrails or Guardrails AI) enforcing hard policy stops.
4. **Audit logger** writing immutable, structured events (tool params, API payloads, state transitions, rule triggers).

## 6. Functional Requirements

- **FR-3.1 Stateful DAG Workflow.** Route execution through *Document Ingestion* -> *Ratio Calculation* -> *Policy Evaluation* -> *Decision Generation*.
- **FR-3.2 Sandboxed Tool Execution.** DSCR, DTI, and leverage ratios are computed exclusively by sandboxed Python tools; direct LLM arithmetic is prohibited.
- **FR-3.3 Policy Guardrails Enforcement.** Hard policy stops via NeMo Guardrails or Guardrails AI (e.g., auto-reject if DSCR < 1.25).
- **FR-3.4 Immutable Audit Logging.** Log all tool parameters, API payloads, intermediate state transitions, and rule trigger events.

## 7. Non-Functional Requirements

- **NFR-3.1 Deterministic Policy Compliance.** Hard stops override any conflicting LLM output, without exception.
- **NFR-3.2 Calculation Precision.** Exactly 0% error across computed ratios.
- **NFR-3.3 Execution Stability.** No unhandled state lockups during workflow runs.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Rule Compliance Rate | 100% adherence to hard stops | Adversarial stress tests, including prompts that try to talk the model past a rule |
| Math Error Rate | 0% | Compare tool outputs against independently computed reference values |
| Workflow Completion Rate | >= 98% successful DAG runs | Batch of synthetic applications; count unhandled exceptions and lockups |
| Auditability Index | 100% of decisions back-linked to tool call logs | Automated check: each decision ID resolves to a complete log chain |

## 9. Out of Scope & Risks

- **Out of scope:** final lending authority (human sign-off remains), credit scoring model training, portfolio-level risk.
- **Risk: sandbox escape or tool misuse.** *Mitigation:* strict allow-list of tools and resource limits.
- **Risk: guardrail bypass via prompt injection in borrower documents.** *Mitigation:* treat document content as data, and run policy checks on structured values rather than prose.
- **Risk: log tampering.** *Mitigation:* append-only storage with integrity hashing.