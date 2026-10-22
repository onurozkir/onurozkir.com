---
title: '“Has Quality Declined?”: Designing Reliable LLM Evaluation from Golden Datasets to Canary Deployments'
date: "2026-10-22T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/en/ai-native-swe/designing-golden-dataset-for-llms/"
series: "ai-native-swe"
translationKey: "llm-golden-dataset"
description: "Design reliable LLM evaluation with a limited labeling budget: build a golden dataset, validate an LLM judge, and combine offline tests with canary evidence."
summary: "Does a lower acceptance rate mean the model has regressed, or has the ticket mix changed? This thought experiment explores building a PII-free golden dataset with six hours of human effort per week, validating an LLM judge, and combining offline evaluation with canary decisions. It examines what illustrative thresholds and limited evidence can actually tell us."
tags: ["AI Native SWE", "AI", "LLM", "LLM-as-a-Judge", "Golden Dataset", "AI Reliability", "LLM Evaluation", "Data Privacy"]
image: "/images/design-golden-set-for-llm.png"
imageAlt: "An evaluation pipeline linking a golden dataset, human annotation, an LLM judge, a canary experiment, and metric analysis to Rollback, Hold, and Expand decisions; labels are in Turkish."
toc: true
summaryForLLM: true
mathjax: false
---

*Separating a drop in acceptance rate from a genuine model regression, and making a defensible production decision with limited human effort.*

This article works through a question step by step. It is not an account of a production incident, but a thought experiment in which each answer raises another question. Here is the scenario:

> Your company’s support team uses an LLM to suggest replies to tickets. You are switching to a cheaper, faster, or internally trained model. The new model is already serving 5% of production traffic through a canary deployment. Your Tech Lead asks, “Has quality declined since the model change?” You have only two signals: the support agents’ acceptance/rejection rate and average response time. Acceptance has fallen from 61% to 58%, but the traffic mix has also changed: A new ticket category has been introduced.
>
> **Constraints:**
>
> - The labeling budget is six hours of human effort per week.
> - Real customers’ personally identifiable information (PII) cannot be used to create the golden dataset.
> - The golden dataset must support both offline CI evaluation and canary decisions.
>
> Design an evaluation system that can answer the question. What sources, sampling strategy, and dataset size would you use? Who labels the data, and how do you control labeling errors? How do you combine offline evaluation with canary acceptance rates? What threshold would justify saying “Quality has declined”? If you use an LLM judge, how do you validate its agreement with human labels? Explain the benefits and costs of your choices.

At first glance, the answer seems straightforward: Support agents’ acceptance rate has fallen from **61% to 58%**. That is a three-percentage-point drop. But **a new ticket category** appeared during the same period. All we have is acceptance/rejection behavior and average response time.

Our weekly human labeling budget is **six hours**. We cannot put real customers’ **PII** into the golden dataset, and the resulting set must be useful for both **offline CI** and **canary decisions**.

An engineer’s job here goes beyond building a dashboard. The real task is to define *how much trust each signal deserves* and *what evidence justifies a release decision*.

## 1. First question: Does acceptance rate measure quality?

Why might a support agent reject a suggestion?

- It is incorrect, incomplete, or inconsistent with company policy.
- It is correct, but the agent prefers a different tone.
- The ticket is complex and needs manual investigation.
- The agent has edited and used the suggestion rather than rejected it entirely.
- The suggestion was generated but never shown to the agent.

These are different events. **Acceptance rate** is a useful but incomplete *proxy metric*: It indicates how useful the model is within the workflow.

Average response time needs similar care. A faster response may improve the experience, but a careless answer can also be written quickly. We must also distinguish **model latency** from **the time an agent spends preparing a reply**.

The first goal is to separate three dimensions:

| Dimension | Main question | Example measurements |
|---|---|---|
| **Response quality** | Is the suggestion correct, safe, and usable? | Human labels, policy violations, critical errors |
| **Agent utility** | Does it make the agent’s job easier? | Acceptance, use after editing, reply preparation time |
| **System reliability** | Does the feature work properly in production? | Error rate, timeouts, p95 latency |

Reporting these separately is safer than hiding quality inside one composite score.

### How can the traffic mix mislead us?

Consider this **entirely illustrative** scenario:

| Ticket category | Previous traffic share | Current traffic share | Acceptance within category |
|---|---:|---:|---:|
| Easy requests | 55% | 40% | 70% |
| Difficult requests | 45% | 40% | 50% |
| New category | 0% | 20% | 50% |

The previous overall acceptance rate is:

> 0.55 × 0.70 + 0.45 × 0.50 = 0.61

The current overall acceptance rate is:

> 0.40 × 0.70 + 0.40 × 0.50 + 0.20 × 0.50 = 0.58

Acceptance falls from 61% to 58%, **without any change in the existing categories’ acceptance rates**. The traffic distribution alone can explain the difference.

This illustrates an essential principle:

> **An observed metric change is not, by itself, the causal effect of changing the model.**

## 2. The golden dataset: An exam paper for the model

A **golden dataset** is an expert-validated evaluation dataset with predefined test scenarios and expected behavior.

Imagine a teacher preparing an exam. They define the questions and answer key in advance, then compare students’ answers against that key. A golden dataset serves a similar purpose. For open-ended LLM responses, however, the goal is to describe *correct behavior*, not to require one memorized sentence.

For example, a synthetic customer message might be:

> “My product arrived damaged. How do I return it?”

**Expected behavior:** Refer to the applicable returns policy, request any missing information, and explain the correct next step.

**Critical error:** Promise a guaranteed refund without support from company policy.

Evaluating the old and new models on the same scenarios enables a **paired comparison**, even when real traffic changes.

### Where should the golden set come from?

Real customer PII cannot enter this golden set. I would use three sources:

1. **Approved, versioned references:** FAQs, the knowledge base, and returns/warranty policies.
2. **PII-free aggregate traffic statistics:** Category frequencies, process types, difficulty distribution, and risk indicators.
3. **Expert-written synthetic cases:** Missing information, typos, conflicting requests, multistep processes, and critical policy traps.

Synthetic data has a cost: Artificial cases can be cleaner and more predictable than real tickets. Before using them, I would ask support specialists to review their realism, and use scanning plus human review to check that the generation process has not copied real PII.

### Random or stratified sampling?

**Random sampling** selects cases at random. It can represent common requests well, but miss rare, critical problems.

**Stratified sampling** first divides cases into meaningful subgroups, or *strata*, then selects a specified number from each. Possible dimensions include:

- Ticket category: billing, returns, technical support, and the new category.
- Difficulty: easy, moderate, and complex.
- Risk: normal, high, and critical.
- Language, product, or agent segment where relevant.

**Risk-weighted sampling** allocates more examples to cases that could have serious consequences.

As an initial design, I might propose **240 synthetic cases**:

| Group | Count |
|---|---:|
| Cases representing existing categories | 160 |
| New category | 40 |
| Critical and challenging cases | 40 |
| **Total** | **240** |

These numbers are a starting design, not a proven optimum. A set of 240 cases may help uncover large regressions and recurring failure patterns, but it is **often insufficient to confidently rule out a small, two-percentage-point quality loss**.

There is another distinction: If we deliberately oversample critical cases, the raw average does not represent production traffic. I would report both **scores by stratum** and a **score weighted by current traffic shares**.

### How far back should we look: Is six months enough?

A six-month reference window may be a reasonable starting point, but it should not become dogma:

| Window | Benefit | Risk |
|---|---|---|
| **Last 3 months** | Responsive to emerging issues | May miss seasonality and rare events |
| **Last 6 months** | Balances recency and coverage | May miss annual patterns |
| **Last 12 months** | Better coverage of seasonal changes | May include obsolete business rules |

My practical approach would be to **compare 3-, 6-, and 12-month windows empirically** when estimating traffic distributions, exclude obsolete policies, and retain still-relevant historical critical cases separately.

A **frozen regression set** of stable comparison cases and a **rolling/challenge set** of refreshed, difficult cases would be versioned separately. This lets coverage evolve without losing comparability with past evaluations.

## 3. Reliable results with six hours of labeling per week

Human labels are expensive. But if we sacrifice their quality to save time, the golden set becomes a dataset that merely **looks trustworthy**.

The first question is who should label it. General-purpose *crowdsourcing*, which distributes work across a large group of people, can be useful in many settings. Here, however, we need **experienced support agents** who know company policy, plus **support QA or policy specialists** to resolve disagreements.

### A usability rubric

| Score | Definition | Quality metric outcome |
|---|---|---|
| **3** | Correct, complete, ready to use | Pass |
| **2** | Correct, usable with minor edits | Pass |
| **1** | Substantial omissions or incorrect information | Fail |
| **0** | Critical privacy, security, or policy error | Critical failure |

One primary metric would be:

> Human-validated usability = Responses scoring 2 or 3 / All evaluated responses

Old and new responses would also be compared **with model identities hidden and response order randomized**: “Old is better / tie / new is better.”

### An example weekly schedule

| Task | Time |
|---|---:|
| Primary review of 60 distinct cases × 4 minutes | 240 minutes |
| Independent second review of 12 cases × 4 minutes | 48 minutes |
| Resolve approximately 6 disagreements × 8 minutes | 48 minutes |
| Rubric calibration and feedback | 24 minutes |
| **Total** | **360 minutes / 6 hours** |

These times assume that both the old and new response are reviewed within each case. Case authoring, PII scanning, and data preparation require additional capacity.

Reviewing 240 distinct cases in four weeks is possible **only if the four-minute-per-case assumption holds**. I would measure actual labeling time in a first-week pilot and reduce the number of cases if necessary. Coverage should not grow at the expense of reliable labels.

### Label noise: Humans can be wrong too

Two experts may assign different scores to the same answer. Systematic or random labeling errors create **label noise**.

To control it, I would:

1. Have a subset of cases **independently labeled twice**.
2. Report chance-corrected agreement measures such as **Cohen’s kappa**, alongside simple agreement and confidence intervals.
3. Examine alternatives such as **Gwet’s AC1** when a dominant class makes kappa difficult to interpret, without treating the measures as interchangeable.
4. Resolve disagreements with a QA specialist and clarify ambiguous rubric rules.
5. Use **anchor examples** to track changes in annotators’ judgments over time.

A week with only **12 double-labeled cases** is a weak basis for a stable, precise agreement estimate. I would accumulate results across weeks and show uncertainty intervals appropriate to the small sample.

## 4. LLM-as-judge: Scaling evaluation without scaling mistakes

It is unrealistic to ask humans to recheck hundreds of responses after every code, prompt, or model change. I would therefore use **LLM-as-judge**: Another LLM evaluates suggestions against the supplied policy references and rubric.

That introduces a new problem: **The judge can itself be biased.**

- **Position bias:** The order of answers A and B affects the verdict.
- **Verbosity bias:** A longer answer may be rewarded as if it were more correct.
- **Style bias:** Professional wording may conceal incorrect policy information.
- **Self-preference / model-family bias:** The judge may favor outputs from particular model families.
- **Domain bias:** New ticket categories may fall outside its calibration coverage.

These risks are not merely theoretical. Zheng and colleagues’ **MT-Bench** study ([NeurIPS 2023](https://papers.neurips.cc/paper_files/paper/2023/hash/91f18a1287b398d378ef22505bf41832-Abstract-Datasets_and_Benchmarks.html)) and Ye and colleagues’ **CALM** research ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/fdca08d371e4b6c031397909e20043bd-Abstract-Conference.html)) systematically examine biases in LLM judges.

A subtler danger is that **humans and the judge may prefer the same incorrect answer**. High human–judge agreement does not automatically mean high factual correctness.

### How should the judge be validated?

I would run these checks on an independent, human-labeled validation set:

| Check | What it tells us |
|---|---|
| Human–judge agreement | Do humans and the judge reach the same decision? |
| Kappa / AC1 plus uncertainty | How robust is that agreement? |
| Critical failure recall | How often does the judge catch critical errors? |
| False positive rate | Does it incorrectly fail valid responses? |
| Position swap | Does swapping response order change the verdict? |
| Error analysis by category | Does it systematically fail on particular subgroups? |

The judge’s prompt, model, reference policies, and structured output would be versioned. Cases used to tune the judge prompt would be separate from its final validation set. Evaluation cases would also be kept out of the evaluated model’s training and prompt optimization; otherwise, data leakage could inflate the results. Cases with substantial human–judge disagreement or suspected critical errors would go to human review.

**Rule:** The judge helps reduce the cost of human evaluation; it is not an absolute authority replacing people and reference policies. I would not let it make automatic release decisions for segments where its reliability has not been established.

## 5. How do offline CI and online canary evaluation work together?

We need to measure the same problem from two perspectives.

**Offline CI:** Run the old and new versions on the same versioned, PII-free scenarios. Try to catch policy violations, usability regressions, and critical errors before release.

**Online canary:** Measure the new version’s utility on real tickets. For a reliable comparison, the 5% new-version group and 95% old-version group must be **randomly assigned during the same period from the same eligible traffic pool**.

The decision flow is:

1. Create synthetic cases through stratified sampling using approved policies and PII-free traffic statistics.
2. Build a versioned golden dataset through expert labeling and disagreement resolution; test the judge on a separate validation set.
3. Compare the old and new models on the same offline CI cases using the calibrated judge and safety checks.
4. Randomly split real traffic into 95% control and 5% canary, collecting exposure, acceptance, editing, timing, and error signals.
5. Feed the traffic-mix-adjusted online effect and offline results into the decision engine: **Rollback** for critical errors or demonstrated material degradation, **Hold** for insufficient evidence, and **Expand** for an acceptable difference.

The two paths share **quality definitions**, but real online customer content is not copied directly into the golden set. Aggregate canary statistics and expert reviews conducted within privacy rules can inform future synthetic scenarios.

### Which production telemetry fields matter?

- **Difficulty proxy:** An indirect indicator of ticket difficulty, such as the number of required steps or historical resolution complexity. It is not a definitive difficulty score.
- **Agent cohort:** A group of support agents sharing characteristics such as experience level or team.
- **Model version:** The version that generated the response, together with prompt and knowledge-base versions.
- **Exposure:** Whether the suggestion was actually shown to the agent. An unseen suggestion should not automatically count as a rejection.

Without these fields, acceptance rate is easy to misinterpret.

### Adjusting the effect for ticket category

I would compare old and new acceptance rates within each category:

> ΔQ_k = Q_new,k − Q_old,k

Here, k denotes the ticket category and Q its acceptance rate. I would then weight the differences using a common reference traffic distribution:

> ΔQ = Σ_k w_k × ΔQ_k; Σ_k w_k = 1

The same weights are used for both models.

I would present two reports:

1. **Like-for-like effect:** The difference caused by the model change under a fixed category distribution.
2. **Current-traffic effect:** The expected operational difference under today’s ticket distribution.

If the new category has no historical data, I would not force it into a comparison with the previous 61%. Where possible, I would compare it against a **concurrent control**. If the control model cannot produce valid responses for that category, I would state that limitation explicitly.

## 6. When can we say “Quality has declined”?

![Offline CI and online canary signals feeding a decision engine with Rollback, Hold, and Expand outcomes.](/images/rollback-hold-expand.svg)

I think we should build a system that can give the Tech Lead one of three outcomes from the start: **Rollback, Hold, or Expand.**

The decision needs two layers:

**1. Safety gate:** A verified new, serious privacy, security, or policy violation triggers consideration of rollback. A high average score must not conceal that risk.

**2. Quality/utility gate:** Decide using a predefined loss tolerance and statistical uncertainty.

An initial discussion might use **−2 percentage points** as an acceptable-loss boundary. This is not a universal number. It must be calibrated against the extra agent effort caused by rejections, customer harm, expected benefits, and error tolerance.

> ΔQ = Q_new − Q_old

Here, ΔQ is the difference in the metric being evaluated: usability offline, or acceptance weighted by a common traffic distribution online. Each metric needs its own tolerance; pp means percentage points.

With a 95% confidence interval, and under valid, predefined experiment and analysis assumptions:

| Outcome | Illustrative decision rule |
|---|---|
| **Rollback — evidence of material regression** | A critical new error, or the relevant difference’s confidence interval has an **upper bound < −2 pp** |
| **Hold — uncertainty** | The interval includes the −2 pp boundary, or sampling/measurement is insufficient |
| **Expand — loss tolerance satisfied** | The confidence interval has a **lower bound > −2 pp**, and safety and operational guardrails are satisfied |

These rules apply separately to human-validated offline quality and online utility, in their respective contexts. I would not average one metric into the other to hide a failure.

An important nuance: **Statistically significant degradation** and **material business degradation** are different concepts. A boundary such as −2 pp defines the amount of harm we cannot accept. Analysis timing, sampling plans, and the policy for repeated checks must also be set in advance for these confidence-interval decisions.

### Does a 5% canary generate enough data?

At an acceptance rate around 60%, assuming independent observations, a two-proportion test, a two-sided 5% significance level, 80% power, and a 19:1 control/treatment ratio, detecting a **three-percentage-point** difference may require roughly **2,200 treatment observations**. At a 5% canary allocation, that means approximately **44,000 eligible tickets**.

A **two-percentage-point** difference may require roughly **5,000 treatment observations**, or **100,000 eligible tickets** in total.

These rounded figures use the normal approximation `n_treatment ≈ (1.96 + 0.84)² × 0.60 × 0.40 × (1 + 1/19) / δ²`, where δ is the absolute difference to detect. This calculation tests for a difference from zero; demonstrating non-inferiority against a −2 pp boundary requires a separate power calculation.

These are planning approximations only. Agent clustering, traffic fluctuations, different metric definitions, and sequential tests change sample requirements. With low traffic, expecting a definitive answer in a few days is unrealistic.

**“We do not have enough evidence yet”** is therefore not a poor engineering answer. It is a necessary output of a well-designed evaluation system.

## 7. The real trade-offs in this design

| Design choice | Benefit | Cost |
|---|---|---|
| **Synthetic golden set** | PII protection and reproducible tests | May miss the variety of real-world language |
| **Stratified/risk-weighted sampling** | Better coverage of rare, critical failures | Raw results cannot directly represent production traffic |
| **Double human labeling** | Reveals label noise and ambiguous rubric rules | Fewer new cases labeled within the same budget |
| **LLM-as-judge** | Scales CI evaluation | Uncalibrated bias and false confidence |
| **5% randomized canary** | Live measurement with limited customer exposure | Small effects may require a long observation period |
| **Strict release gate** | Blocks harmful regressions | False alarms and release delays have costs |

Success does not always depend on more data or a more complex model. It depends on **managing uncertainty honestly with limited resources**.

## 8. The complete design

![System architecture connecting golden datasets and human labels to offline CI, a randomized canary, and a release decision engine; diagram labels are primarily in Turkish.](/images/system-design-golden-set.png)

*The diagram uses Turkish labels. Its three columns are Golden Set & Labels, Offline CI Eval, and Online Canary. The offline and online paths feed a release decision engine that produces Rollback, Hold, or Expand; the workflow and thresholds are described above.*

## 9. What would I tell the Tech Lead today?

This:

> “Acceptance has fallen from 61% to 58%, but the ticket mix changed during the same period. We cannot yet conclude that model quality has declined. We need to compare the old and new versions on concurrent, comparable traffic and on a human-validated golden set. While evidence remains insufficient, we should pause expansion and keep the canary at 5% under safety monitoring, provided no critical regression has been found.”

That may not sound flashy, but it is a responsible production answer. It does not hide behind an average, pretend to know what is unknown, or leave the decision criteria vague. It **defines in advance what evidence would change the decision**.

A good LLM evaluation system does more than answer “What score did this model get?” It faces a harder question:

**“Do we actually have enough evidence to give this model more responsibility in production?”**

## 10. Are there tools for this?

Three tools can help with different parts of this design:

- [Langfuse](https://langfuse.com/docs/evaluation/overview): Dataset management, human evaluation, and offline/online evaluation.
- [Phoenix](https://github.com/arize-ai/phoenix): Observing model behavior, tracing, and comparing experiments.
- [Evidently](https://github.com/evidentlyai/evidently): Monitoring changes in data distributions and model performance.

I wrote this design as a thought experiment, but it could become a product. Maybe someday…

---

## Glossary

| Term | Brief explanation |
|---|---|
| **Golden dataset** | Evaluation cases with expected behavior defined by experts |
| **Crowdsourcing** | Distributing work among many independent participants |
| **Stratified sampling** | Selecting examples from predefined subgroups |
| **Label noise** | Errors or inconsistencies in labels |
| **Inter-annotator agreement** | Agreement between different annotators’ decisions |
| **LLM-as-judge** | Using an LLM to evaluate another LLM’s outputs |
| **Difficulty proxy** | An indirect measure of ticket difficulty |
| **Agent cohort** | A group of support agents with a shared characteristic |
| **Exposure** | A suggestion actually being shown to an agent |
| **Offline CI eval** | Automated evaluation on a fixed test set before release |
| **Traffic-mix adjustment** | Normalizing the effect of different category distributions |
| **Non-inferiority** | Testing whether a new version is not worse beyond a predefined tolerance |
| **Rollback / Hold / Expand** | Revert, pause expansion, or increase rollout in a controlled way |

## Further reading

1. **Zheng et al. (NeurIPS 2023)** — [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://papers.neurips.cc/paper_files/paper/2023/hash/91f18a1287b398d378ef22505bf41832-Abstract-Datasets_and_Benchmarks.html). Position, verbosity, and related biases in LLM judges.
2. **Ye et al. (ICLR 2025)** — [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://proceedings.iclr.cc/paper_files/paper/2025/hash/fdca08d371e4b6c031397909e20043bd-Abstract-Conference.html). Analysis of LLM judge biases using CALM.
3. **Klie et al. (ACL 2024)** — [On Efficient and Statistical Quality Estimation for Data Annotation](https://aclanthology.org/2024.acl-long.837/). Statistical uncertainty and cost in small annotation-quality samples.
4. **Gwet (2008)** — [Computing inter-rater reliability and its variance in the presence of high agreement](https://pubmed.ncbi.nlm.nih.gov/18482474/). Gwet’s AC1 and inter-rater reliability.
5. **Zec et al. (2017)** — [High Agreement and High Prevalence: The Paradox of Cohen’s Kappa](https://pmc.ncbi.nlm.nih.gov/articles/PMC5712640/). Why kappa needs careful interpretation under certain class distributions.

*Note: This article is a system-design and research proposal. Dataset size, labeling speed, acceptable quality loss, and sample counts are illustrative engineering assumptions, not observed results.*
