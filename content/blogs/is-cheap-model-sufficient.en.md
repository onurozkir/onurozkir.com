---
title: '"The Cheap Model Solves 70%." How Do We Tell the Other 30% Apart?'
date: "2026-10-26T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/en/ai-native-swe/is-cheap-model-sufficient/"
series: "ai-native-swe"
translationKey: "is-cheap-model-sufficient"
description: "Balancing cost and quality with LLM routing: pre-router, quality gate, shadow evaluation, and rollback strategy under a 1.5-second deadline."
summary: "Having a cheap model match the expensive model on 70% of requests does not mean we can safely offload 70% of traffic. In this thought experiment, I explore using a pre-router to divert difficult documents upfront, validating outputs with deterministic and semantic quality gates, catching silent regressions with shadow sampling, and building a segment-level rollback strategy. The goal is not the cheapest inference, but the lowest total cost per successfully resolved task within a critical error budget."
tags: ["AI Native SWE", "AI", "LLM", "LLM Routing", "AI Reliability", "Model Evaluation", "Cost Optimization"]
image: "/images/is-cheap-model-sufficient.png"
imageAlt: "LLM routing flow diagram showing decision paths between cheap and expensive models."
toc: true
summaryForLLM: true
mathjax: false
---

*Managing quality, latency, and silent errors while cutting costs with LLM routing.*

Making an LLM system more economical does not always require downgrading to a cheaper model. Often, the real savings come from **correctly determining which request should go to which model**.

In this article, we explore another question-and-answer scenario. As in the previous [article on golden datasets and canary evaluations](/en/ai-native-swe/designing-golden-dataset-for-llms/), the system described here is not a real production incident, but a thought experiment designed to illuminate engineering decisions.

> Demo : https://github.com/onurozkir/assured-route

The prompt:

> You run a document classification and field extraction service. Think of it as a RAG or decision-making model.
> The system handles **4 million requests a month**. Currently, it uses a single high-capability model, resulting in a monthly model bill of **$60,000**.
>
> You evaluate a cheaper model. In offline testing, the cheap model yields the **same output as the expensive model on about 70% of requests**; on the remaining 30%, it produces inferior results.
>
> Management suggests: **“Call the cheap model first. If the output is poor, fall back to the expensive model.”**
>
> But how do we detect poor output at runtime? Calling both models on every request defeats the cost savings. While errors in some fields are tolerable, mistakes in fields like `total_amount`, `date`, or `party_name` can disrupt financial workflows. Moreover, the end-to-end latency budget is strictly **1.5 seconds**. For quality tracking, we currently rely only on manual sampling.
>
> **How do we prove quality is preserved while costs fall? How do we detect system degradation and roll back safely?**

Where did this question come from? Naturally, [LiteLLM](https://www.litellm.ai/). But of course, LiteLLM isn't everything. Thinking through what LiteLLM and RouteLLM do and how they work leads to an interesting question: Can we layer a **Quality Decision Layer** on top?

The most obvious answer is: run the cheap model first, and if confidence is low, escalate to the expensive one. Yet this proposal leaves two unanswered questions: **Does confidence measure correctness?** And **will there be enough time left to call the expensive model?**

The challenge is not simply writing a *model router*. The task is balancing the cost of model failure, the probability of catching an error, and the remaining execution time inside a single unified system.

## 1. 70% Agreement Is Not 70% Accuracy

Our starting data point is that the cheap model produces the **same result** as the expensive model on 70% of requests. This does not mean the cheap model is 70% accurate.

- On a document where both models agree, both could be wrong.
- On a document where they disagree, the cheap model might be right and the expensive model wrong.
- The fact that the expensive model is more capable does not automatically make it *ground truth*.

This distinction is crucial: if we train a router exclusively on examples where the two models disagree, we effectively teach it that “differing from the expensive model” is synonymous with an error.

We first need to measure three distinct dimensions:

| Measurement | Question Answered |
| --- | --- |
| **Model agreement** | How often do the cheap and expensive models produce the same result? |
| **Ground-truth accuracy** | How close is each model to independently verified truth? |
| **Critical field error** | Does the error occur in a business-critical field? |

This is why the **golden dataset** approach discussed previously remains a foundational requirement here as well. I would build a stratified evaluation set across document types, OCR quality, templates, languages, critical fields, and difficulty tiers, using human-verified amounts, dates, and party details as ground truth.

Furthermore, not all errors deserve the same severity score.

A misclassified `tag` might route a document to the wrong queue, easily fixed with reclassification. A corrupted `grand_total` fed into an ERP or payment pipeline can become a far more expensive operational disaster.

> **Guiding Principle:** The router must account not only for the probability of an incorrect answer, but for the *business impact of that error*.

## 2. How Do We Know the Cheap Model’s Output Is Sufficient?

I would not rely on a single confidence threshold. Instead, I would design a **Quality Gate** where outputs pass through multiple independent verification layers.

### First layer: Schema and type validation

Are all expected JSON keys present? Are dates in a valid format? Is the amount numeric? Are required fields populated? Do tax IDs or IBANs satisfy checksum constraints?

These checks are fast and essential. But a value like `12500.00` that belongs to an entirely different document is still a valid JSON number.

**Valid schema does not imply correct content.**

### Second layer: Deterministic business rules and grounding

For instance, on an invoice:

```text
Subtotal + Taxes - Discounts ≈ Grand Total
```

We can verify this arithmetic consistency with currency handling, rounding tolerances, and document-specific exemptions.

We also verify that the extracted value actually exists in the source text:

```json
{
  "field": "invoice_total",
  "value": 12800.00,
  "currency": "TRY",
  "evidence": {
    "page": 1,
    "text": "GENEL TOPLAM: 12.800,00 TL"
  }
}
```

There is an important nuance here: the model generating an `evidence` field is not sufficient proof. We must independently verify that this snippet exists in the OCR output on the specified page and matches the extracted field.

For example, a document might state both `Subtotal: $10,000` and `Grand Total: $12,800`. The presence of an amount in the text does not prove that the right amount was picked. The same caveat applies to buyer and vendor names.

Due to OCR noise, exact string matching might reject valid extractions. Normalization and calibrated fuzzy matching can help, though fuzzy matching also carries the risk of matching the wrong field.

### Third layer: Field-level uncertainty signals

If token log-probabilities from the cheap model are available, they provide valuable signals. In particular, the token probabilities forming critical values like `amount`, `date`, and `party_name` are often more informative than a generic overall confidence score.

However, an important distinction is required:

- `P(token)` is a probability between 0 and 1.
- `log P(token)` is zero or negative.
- A long company name might appear artificially risky because of a single rare sub-word token.
- Models can hallucinate incorrect answers with high confidence.

Therefore, a naive threshold like `min token probability > 0.90` should not serve directly as a production gate. Instead, token-level signals, string lengths, OCR quality scores, source alignment, and rule validation outcomes should feed into a **calibrated error predictor** as features.

This approach avoids treating the model's self-reported confidence as the final judge. The reliability of the error predictor is itself evaluated against the golden dataset.

### Fourth layer: Selective verifier

Some errors cannot be caught with arithmetic or schemas—especially **semantic role assignment**.

Suppose we correctly extract two company names from a contract, but which is the provider and which is the client? Or between two dates, which is the invoice date and which is the due date?

Rather than calling another large LLM, we can deploy a **lightweight cross-encoder verifier**. Instead of ingesting the entire document, it receives only the relevant OCR snippet and the candidate extracted value, scoring whether the value matches the expected semantic role.

An 80M parameter model or an ONNX/TensorRT-optimized inference runtime is a strong candidate. However, claiming “runs in 20 ms” or “catches most critical errors” requires benchmarking on target hardware with real production data.

Moreover, the verifier can also fail. On novel templates or rare document formats, both the cheap model and the verifier might share the same failure mode.

### The cost of these verification signals

Here, we define a *positive decision* as “escalation required.”

| Check | Unnecessary Escalation Risk | Missed Error Risk |
| --- | --- | --- |
| Schema / types | Correct but malformed output escalates expensively | Invalid but well-formed JSON is accepted |
| Business rules / grounding | OCR noise causes valid fields to be rejected | Self-consistent but incorrect numbers pass |
| Token-level signals | Long or rare values trigger unnecessary suspicion | Confident hallucinations slip through |
| Cross-encoder verifier | Correct semantic roles might be rejected | Subtly ambiguous roles fool both models |

Unnecessary escalation incurs additional inference cost and latency. **A missed critical error writes corrupted data downstream.** These two costs are not symmetrical.

## 3. Deciding Before Inference: The Pre-Router

The fundamental flaw in management's “try cheap first, escalate if bad” suggestion is this: sending every request to the cheap model wastes both time and money on known hard cases.

Instead, we use *pre-routing*.

When a document arrives, a lightweight classifier runs over OCR text and metadata. LightGBM is a sensible candidate:

- OCR quality statistics
- Page count, character count, and table density
- Numerical complexity and multi-currency indicators
- Known vs. novel template and document type
- Downstream business cost of an error in this workflow
- Historical cheap-model error rate in this segment

This allows high-risk or inherently difficult documents to be routed **directly to the expensive model from the start**.

There is an alluring but dangerous assumption: “The cheap model fails on 30%; the router can catch two-thirds of those upfront, leaving only a 10% fallback rate.”

While a reasonable goal, we have no prior proof. Diverting 20% of traffic to catch 20% of errors requires **100% precision** on that bypass slice—an extremely aggressive expectation.

We should not treat a 20% bypass rate as an axiom. We must **evaluate pre-router precision, recall, latency, and cost curves** to select an empirically sound operating point.

Crucially: the pre-router must only use features **actually available before calling the cheap model**. A model trained on downstream signals will look great offline and fail completely in production.

## 4. Three Routes and a Safe Exit

I design the system around four possible outcomes:

| Route | When? | Decision |
| --- | --- | --- |
| **A — Cheap + Rules** | Known template, low risk, all deterministic checks pass | Accept output |
| **B — Cheap + Verifier** | Field exists in text, but semantic role or alignment is ambiguous | Selectively verify; escalate if needed |
| **C — Direct Expensive** | Pre-router flags high risk or difficult document | Bypass cheap model entirely |
| **D — Pending / Review** | Critical field remains uncertain or deadline is near | Do not write unverified output to business systems |

Simplified workflow:

```text
                  Incoming Document
                         |
                   OCR + Metadata
                         |
               Pre-Router (LightGBM)
                    /         \
              High Risk      Cheap-Eligible
                 |                 |
          Expensive Model     Cheap Model
                 |                 |
         Critical Validation   Schema + Rules
                 |                 |
                 |        Calibrated Risk Gate
                 |          /      |       \
                 |       Accept  Verify   Escalate
                 |          |      |         |
                 |          |  Cross-Encoder |
                 |          |      |         |
                 |          |   Accept /     |
                 |          |   Escalate     |
                 |          |      |         |
                 +----------+------+---------+
                            |
                   Deadline + Final Gate
                        /        \
               Validated Output   Pending / Review
                            |
                  Async Quality Monitoring
```

An `ACCEPT` decision is not granted merely because a model expresses confidence; it requires satisfying validation criteria proportional to the business risk.

Likewise, `PENDING / REVIEW` is not a design flaw. In critical workflows, acknowledging that certain requests cannot be resolved automatically is far safer than silently committing bad data.

## 5. Can Sequential Fallback Fit Within 1.5 Seconds?

Consider an illustrative latency breakdown:

| Stage | Sample Latency |
| --- | ---: |
| OCR / preprocessing | 150 ms |
| Cheap model | 450 ms |
| Expensive model | 950 ms |
| **Total** | **1550 ms** |

This budget excludes network transport, validation overhead, and service hops. A blanket “fall back on any suspicious output” strategy quickly violates a 1.5-second SLA.

The solution is not just picking a faster model—it is **changing what decisions are made and when**.

### Streaming early-exit

If we have control over token generation, we can instruct the cheap model to emit critical fields first in the JSON schema. This allows validation to begin on completed critical fields without waiting for the full response.

If the first critical field clearly contradicts the source text, we can abort the cheap model stream and trigger the expensive model early.

For this to yield real latency wins, three things must hold true:

1. Does the inference provider support streaming alongside token probabilities?
2. Do critical fields arrive early enough in a **complete and verifiable** state?
3. Does canceling an active stream actually reduce billed token and compute costs?

Without affirmative answers, an “early exit at 180 ms” remains an untested assumption.

### Deadline-aware escalation

We track elapsed time per request. When escalation is triggered, the decision depends not only on risk, but on the **remaining deadline**.

If sufficient time remains, we escalate synchronously. If the deadline has expired and critical fields remain unverified, the request is flagged for asynchronous processing or human review.

This reveals an important contractual distinction: **p95 latency ≤ 1.5s** does not mean 100% of requests finish in 1.5s. If 1.5 seconds is a strict *hard deadline*, timeout and pending behaviors must be explicitly defined in the API contract.

### What about speculative parallel execution (hedging)?

Invoking both models in parallel on all requests defeats the cost objective.

However, a highly targeted **hedging** strategy can help. If the cheap model exceeds expected response times for a document type and the deadline is approaching, the expensive model can be launched speculatively.

The trade-off is clear: hedging intentionally duplicates calls on tail requests. It should only be enabled if measured tail-latency benefits outweigh the additional inference cost. Furthermore, a faster response does not guarantee correctness; the final quality gate must still run.

> **Default Stance:** Accurate pre-routing first, followed by cheap validation. Streaming and hedging should be added as targeted optimizations once specific latency bottlenecks are measured.

## 6. How to Train a Calibrated Quality Gate

At what exact threshold should the Quality Gate decide to **Accept**, **Verify**, or **Escalate**?

A static rule like `confidence > 0.90` provides no measurable error budget.

Instead, we train an **error predictor** on the golden dataset. Inputs include OCR quality, document types, token signals, source alignment, and rule outputs. The target variable is an independently verified **field-level error**:

```text
P(invoice_total_wrong | document_features, model_output_signals)
P(seller_name_wrong | document_features, model_output_signals)
```

We evaluate probability calibration on a holdout set using Brier scores and reliability diagrams. While temperature scaling is common, it is not a silver bullet across all LLM architectures and task domains.

Next, we plot a **risk–coverage curve**:

- *Coverage:* What percentage of cheap model outputs are accepted without expensive escalation?
- *Selective risk:* What is the actual critical error rate among those accepted outputs?

For instance, 50% coverage might yield 0.05% error, 70% coverage might yield 0.15%, and 85% coverage might jump to 0.60%. These illustrative figures demonstrate the trade-off.

If business stakeholders agree to a 0.2% critical error budget, we operate at the maximum coverage level that statistically guarantees this threshold within defined confidence intervals.

Crucially, **“zero tolerance for amount errors”** should not be interpreted as an unrealistic promise that the model will never fail. It means establishing an operational policy that *no unverified critical data is written downstream*. The practical error budget is defined around that safeguard.

## 7. Detecting Silent Degradation in Production

Offline evaluation is only a baseline. Post-deployment changes in customer templates, scanner quality, traffic mix, or upstream provider model updates can silently degrade accuracy.

To guard against this, we deploy an **Async Evaluation Plane** decoupled from synchronous user response paths.

A sample of requests accepted by the cheap model is queued according to data privacy policies. These samples run through shadow calls against the expensive model, and a subset is routed to human annotators.

### Stratified shadow sampling

A starting sampling policy:

| Traffic Cohort | Sample Target | Objective |
| --- | ---: | --- |
| High-confidence accepted | 0.5% | Catch silent false negatives |
| Gray zone / verifier processed | 5% | Detect drift around the decision boundary |
| Novel or low-volume templates | 10% | Monitor unmapped distributions |

These sampling weights must be adjusted when computing global error rates to avoid over-weighting rare edge cases.

We track two primary signals:

**Critical Field Disagreement Rate (CFDR):** How frequently the cheap and expensive models diverge on critical fields.

**Human-validated Critical Error Rate:** The proportion of critical fields confirmed incorrect against ground truth.

CFDR provides high-volume, rapid drift detection. Human validation provides authoritative quality measurement. **Teacher disagreement is not ground truth**; both models can make the identical error.

### Actionable guardrails, not just dashboards

Alerting triggers should drive concrete mitigations:

| Signal | Trigger | Action |
| --- | --- | --- |
| CFDR | Significant rise above calibrated baseline | Increase sampling; inspect affected segment |
| Golden / human error rate | Statistically significant breach of error budget | Revert segment to expensive model |
| Escalation rate | Anomalous spike or drop relative to norm | Audit router, validator, and traffic mix |
| p95 / p99 latency | SLO breach or tail degradation | Inspect timeouts, provider capacity, routing |
| Verified critical data corruption | Single P0 event | Fail-closed incident response for affected workflow |

Thresholds must account for sample size. Concluding “quality dropped 200%” based on three errors in a low-volume slice is just as flawed as ignoring a statistically robust increase in high-volume traffic.

Maintaining a small **expensive-only control cohort** in production helps distinguish whether performance changes originate from the cheap model, routing logic, or shifts in the underlying documents themselves.

## 8. Unit Economics: Calculating the True Savings

Baseline metrics:

```text
Monthly requests:              4,000,000
Monthly expensive model bill:  $60,000
Average expensive call:        $0.015
```

Assume the cheap model costs **$0.0015** per call. The following routing distribution serves as an illustrative cost scenario:

| Final Path | Traffic Share |
| --- | ---: |
| Direct expensive model | 20% |
| Cheap + rules → accept | 55% |
| Cheap + verifier → accept | 15% |
| Cheap + verifier → expensive model | 5% |
| Cheap → early abort / escalation → expensive | 5% |
| **Total** | **100%** |

In this scenario:

- Cheap model is called on **80%** of traffic.
- Expensive model is called on **30%** of traffic (20% direct + 10% escalated).
- Verifier runs on **20%** of traffic.
- Dual-model calls occur on **10%** of requests; aborted streams must be billed according to actual token consumption.

Estimated monthly baseline inference:

| Item | Calculation | Cost |
| --- | --- | ---: |
| Cheap model | 3.2M × $0.0015 | **$4,800** |
| Expensive model | 1.2M × $0.015 | **$18,000** |
| **Baseline Inference Total** | | **$22,800** |

Adding 60,000 shadow calls adds roughly **$900**, while verifier and queue infrastructure adds an estimated **$300**.

Total estimated cost is **$24,000/month**, yielding approximately **$36,000 (60%) gross savings** on model inference and evaluation infrastructure.

However, this is strictly a *gross* figure. Human labeling, reprocessing, incident triage, differing token lengths, and downstream error remediation are not fully captured.

Consider the compounding risk:

If real critical errors increase by just **0.1 percentage point**, that equates to **4,000 additional corrupted documents** per month. If each incident carries a modest $10 operational resolution cost:

```text
4,000 errors × $10 = $40,000 / month
```

That alone wipes out the entire $36,000 inference savings.

In an executive review, the headline KPI should never simply be “we cut token spend by 60%.”

The primary north star is **Cost per Successfully Resolved Task (CPSRT)**.

We separately track **reprocessing rate**, **downstream error rate**, **cheap acceptance coverage**, and **critical field error rate**. Processing a single document three times does not count as three successful tasks.

> **Optimization Goal:** Not the cheapest inference, but the lowest total cost per successfully resolved task under latency and quality constraints.

## 9. Rollback Architecture: What Happens When Things Break?

A monitoring system that detects degradation without the ability to intervene is incomplete. Rollback mechanisms must be built into the runtime architecture.

I implement a three-tiered recovery strategy:

**1. Segment-level isolation.** If errors are confined to a newly introduced invoice layout, route only that segment directly to the expensive model while preserving cost savings across unaffected templates.

**2. Tighten the Quality Gate or pause cheap routing.** If uncertainty spikes on a specific field, tighten acceptance criteria based on measured error-coverage curves rather than arbitrary threshold adjustments.

**3. Full bypass.** Under systemic failure, route all eligible traffic directly to the expensive baseline. Note that the expensive model must remain subject to verification checks.

An operational hazard to anticipate: suddenly shifting 100% of traffic to an expensive tier provisioned for 30% can trigger upstream provider rate limits. Burst capacity and cost spikes must be planned, with optional throttling on non-critical batch jobs.

More critically: **A rollback does not undo bad data already committed downstream.**

Every request must log request IDs, document hashes, model/prompt/router versions, routing decisions, and validation outcomes. When an issue is identified, teams can identify impacted records, initiate reconciliation workflows, and rely on idempotent pipelines to prevent duplicate financial entries.

## 10. Phased Production Rollout

Deploying LightGBM pre-routers, calibrated gates, cross-encoders, streaming aborts, and shadow evaluators simultaneously makes root-cause analysis nearly impossible.

I recommend a phased deployment:

| Phase | Deliverable | Exit Criteria |
| --- | --- | --- |
| **P0 — Measurement baseline** | Golden dataset, field error definitions, validation checks, audit logging | Verifiable quality measurement in place |
| **P1 — Basic routing** | Pre-router + cheap model + rules + direct expensive bypass | Passes offline and shadow benchmarks |
| **P2 — Selective verification** | Cross-encoder and calibrated risk gate | Demonstrates meaningful coverage gains within error budget |
| **P3 — Latency optimization** | Streaming early-exit, deadline-aware fallback, targeted hedging | Measurable improvements in p95/p99 latency and total cost |
| **P4 — Controlled rollout** | Canary deployment, control cohort, automated guardrails and rollback | Production error rates remain within agreed thresholds |

Crucially, evaluate not just the cheap model, but the **performance of the router itself**:

- No pre-router vs. LightGBM pre-router
- Static confidence thresholds vs. calibrated risk estimation
- Deterministic gates vs. gates combined with cross-encoders
- Full inference vs. streaming early-exit
- Sequential fallback vs. deadline-aware fallback vs. hedging
- Shadow disagreement vs. human-verified ground-truth error

Every added layer must justify itself against **marginal quality gains, added latency, operational complexity, and compute costs**.

## 11. What to Tell the Tech Lead Today

Here is the pitch:

> “The fact that the cheap model matches the expensive model on 70% of offline requests does not mean we can safely offload 70% of traffic. We first need to measure whether those disagreements represent true errors, and which fields they impact, using a golden dataset.
>
> Next, we can introduce a pre-router to send difficult documents to the expensive model upfront, deterministic rules for easy outputs, a compact verifier for ambiguous semantics, and fail-closed protections on critical fields.
>
> Streaming early-exit can help contain latency, but we cannot commit to an SLA until we measure its actual impact. In production, shadow sampling and human validation will continuously track quality, with segment-level rollbacks ready if degradation occurs.
>
> Our objective is not to maximize cheap model utilization. It is to **lower total cost per successfully resolved task while staying strictly within our critical error budget**.”

This approach offers fewer sensational claims upfront, but it is vastly more defensible in production. It identifies testable assumptions, specifies what data would change our minds, and provides an actionable operational playbook when things fail.

## 12. Architectural Trade-offs

| Decision | Benefit | Cost |
| --- | --- | --- |
| LightGBM pre-router | Prevents redundant dual-model calls on hard inputs | Misclassification risk and model maintenance |
| Deterministic rules | Fast, explainable safety boundary | Can miss semantic nuances and document edge cases |
| Field-level calibrated risk | Converts confidence into actionable probability | Requires labeled data and continuous calibration |
| Selective cross-encoder | Catches role/alignment errors at low cost | Introduces additional model latency and operational overhead |
| Streaming early-exit | Accelerates fallbacks on obvious mismatches | API dependency and complexity in validating partial JSON |
| Hedging | Mitigates rare tail latency | Deliberate duplicate calls and increased capacity usage |
| Stratified shadow + human review | Simultaneously tracks silent drift and ground truth | Sampling overhead, human labor, statistical uncertainty |
| Fail-closed + rollback | Preserves critical data integrity | Pending workflows, reconciliation overhead, higher transient costs |

Ultimately, this is more than a simple *“small model vs. large model”* decision.

The core question is:

> **When can we trust a model’s output, when must we demand verification, when should we escalate to a stronger model, and when should we decline to automate?**

A system capable of answering that question through empirical evidence is far more valuable than a basic LLM router. It manages not just model routing, but **the boundary of autonomous responsibility in production**.

---

## Glossary

| Term | Brief explanation |
| --- | --- |
| **Model routing** | Dynamically selecting which model or verification path processes a request |
| **Agreement** | Frequency with which two models produce identical outputs; distinct from accuracy |
| **Pre-router** | Lightweight classifier run prior to primary inference to direct traffic |
| **Quality Gate** | Verification layer deciding to accept, verify, escalate, or hold an output |
| **Grounding** | Validating extracted values against direct evidence in the source document |
| **Logprob** | Logarithm of the model's assigned token probability |
| **Calibration** | Alignment between predicted confidence scores and observed empirical accuracy |
| **Cross-encoder** | Model scoring alignment by evaluating input text and candidate output jointly |
| **Selective prediction** | Strategy where a model refrains from answering when uncertainty is high |
| **Coverage** | Proportion of total tasks resolved automatically without expensive escalation |
| **Risk–coverage curve** | Trade-off curve showing error rate among accepted tasks as coverage increases |
| **Shadow evaluation** | Evaluating alternative models on live traffic without impacting user responses |
| **Hedging** | Speculatively launching duplicate calls to reduce tail latency |
| **Fail-closed** | Safely withholding unverified outputs rather than risk writing bad data |
| **CPSRT** | Cost per Successfully Resolved Task; total operational cost divided by successful outcomes |

## Further Reading

1. **Geifman & El-Yaniv (NeurIPS 2017)** — [*Selective Classification for Deep Neural Networks*](https://arxiv.org/abs/1705.08500). Analyzing the relationship between selective risk and coverage.
2. **Guo et al. (ICML 2017)** — [*On Calibration of Modern Neural Networks*](https://proceedings.mlr.press/v70/guo17a.html). Calibrating neural network confidence against empirical accuracy.
3. **Ong et al. (ICLR 2025)** — [*RouteLLM: Learning to Route LLMs from Preference Data*](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html). Learned routing between strong and economical LLMs.
4. **Chuang et al. (ICML 2025)** — [*Learning to Route LLMs with Confidence Tokens*](https://proceedings.mlr.press/v267/chuang25b.html). Using token confidence for routing and abstention decisions.
5. **Dean & Barroso (CACM 2013)** — [*The Tail at Scale*](https://research.google/pubs/the-tail-at-scale/). Foundational principles of tail latency management and hedged requests.

*Note: This article is a system design and thought experiment. Model pricing, traffic splits, latencies, verifier throughput, sampling rates, and cost calculations are illustrative assumptions and should not be interpreted as measured production benchmarks.*
