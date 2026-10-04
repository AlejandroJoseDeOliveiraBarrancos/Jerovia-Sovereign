# Project 4: Production LLMOps & Semantic Caching for Transaction Intelligence

> A high-throughput gateway that serves transaction classification from open-weights models, short-circuits repeat traffic with a semantic cache, and exposes full observability.

**Module:** `services/llm-gateway` | **Status:** Phase 3 | **Owner:** AI Engineering / Platform

---

## 1. Overview

A model-serving gateway for transaction classification. Incoming transaction strings first hit a Redis-backed semantic cache; misses go to open-weights models hosted on vLLM. Every request emits OpenTelemetry traces so cost, latency, and cache behavior are visible, and fallback routing keeps the service up when a model endpoint fails.

## 2. Problem Statement & Product Value

**The problem.**

- Transaction streams are repetitive ("UBER *TRIP 8841", "UBER *TRIP 2207"), so paying full inference cost every time is wasteful.
- Frontier-API costs and latency scale linearly with traffic.
- Without tracing, teams can't explain cost spikes, quality drops, or latency tail behavior.
- A single model endpoint is a single point of failure.

**The value.**

| Value driver | Outcome |
|---|---|
| Cost | At least 40% of requests served from cache without model inference |
| Latency | Cache hits in 20 ms or less; cold inference in 250 ms or less |
| Reliability | 99.9% availability under 100 req/s simulated load |
| Visibility | Token usage, latency, hit/miss status, and vector distance per request |

## 3. Target Users & Use Cases

**Personas:** platform and ML engineers, fintech product teams doing transaction enrichment, and finance operations teams categorizing high volumes of transactions.

**Use cases**

1. **Real-time transaction categorization** for banking and expense apps.
2. **Cost reduction** on repetitive merchant strings via semantic matching, not just exact match.
3. **Load absorption** during peaks (payday, month-end) with rate limiting and fallback.
4. **Cache tuning.** Use hit/miss and vector-distance telemetry to set the similarity threshold.
5. **Serving backend** for the fine-tuned models from Projects 3 and 7.

## 4. Product Fit

- **The LLMOps piece of the portfolio:** serving, caching, observability, and resilience.
- **Natural deployment target** for the quantized models produced in `ml/fine-tuning-pipeline`.
- **Cost/latency/availability numbers** give a concrete platform-engineering story.

## 5. Architecture (High Level)

1. **API layer** with rate-limiting middleware and health checks.
2. **Semantic cache** (Redis + GPTCache) with a cosine-similarity threshold.
3. **vLLM inference** (PagedAttention, continuous batching).
4. **Fallback router** to secondary endpoints on model failure.
5. **Telemetry:** OpenTelemetry traces to Langfuse / Arize Phoenix.
6. **Containerization** with health checks.

## 6. Functional Requirements

- **FR-6.1 vLLM High-Throughput Serving.** Host open-weights classification models with PagedAttention and continuous batching.
- **FR-6.2 Upstream Semantic Vector Cache.** Return cached responses above a set cosine-similarity threshold.
- **FR-6.3 OpenTelemetry Observability.** Emit traces capturing token usage, latency distributions, cache hit/miss, and vector distance.
- **FR-6.4 Containerized Fallback & Rate Limiting.** Health checks, rate-limit middleware, and fallback routing to secondary endpoints.

## 7. Non-Functional Requirements

- **NFR-6.1 Cache Hit Latency.** 20 ms or less.
- **NFR-6.2 Cold Inference Latency.** 250 ms or less through vLLM.
- **NFR-6.3 Availability & Scalability.** 99.9% availability under simulated load up to 100 req/s.

## 8. Acceptance Criteria & KPIs

| KPI | Target | How it's measured |
|---|---|---|
| Cache Latency (Hit) | <= 20 ms | p95 on hit-only traffic |
| Cache Hit Rate | >= 40% | Hits / total on representative transaction stream |
| Inference Latency (Miss) | <= 250 ms | p95 on cold requests |
| Availability | 99.9% at 100 req/s | Load test (e.g., k6/Locust) including injected model failures |

## 9. Out of Scope & Risks

- **Out of scope:** model training (see `ml/fine-tuning-pipeline`), multi-region deployment, billing/chargeback.
- **Risk: false cache hits** return a wrong category for a similar-looking but different transaction. *Mitigation:* tune the threshold using a labeled set, and track cache-served accuracy as a separate metric.
- **Risk: hit-rate depends on traffic realism.** *Mitigation:* document the dataset used for the 40% claim.
- **Risk: GPU capacity limits** the 250 ms target. *Mitigation:* batching configuration and a fallback endpoint.