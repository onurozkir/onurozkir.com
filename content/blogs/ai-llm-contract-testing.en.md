---
title: "We Let the LLM In. It Doesn't Own the Place: Contract Testing"
date: "2026-10-19T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/en/ai-native-swe/ai-llm-contract-testing/"
series: "ai-native-swe"
description: "Checking LLM replies at the application boundary: a TypeScript experiment with contract tests, schema validation, timeouts, retries, PII checks and a circuit breaker."
summary: "The first AI Native SWE article examines a small TypeScript experiment that adds LLM reply suggestions to a support system. A local mock provider exercises malformed JSON, timeouts, personal data and provider errors. We separate what contract checks protect from the work still needed before production use."
tags: ["AI Native SWE", "AI", "LLM", "Contract Testing", "Software Architecture", "AI Reliability", "Circuit Breaker", "Data Privacy", "Resilience"]
image: "/images/ai-native-swe-contract-testing.png"
imageAlt: "AI Native SWE Contract Testing cover showing unpredictable LLM output passing through a validation gate into an application while malformed pieces are diverted."
toc: true
summaryForLLM: true
mathjax: false
---

A while ago, a colleague and I were discussing what developers would do after LLMs took over. My answer was disappointingly unvisionary: “What we've always done.”

We'll connect services, distrust incoming data, and add timeouts. Then we'll investigate why the timeouts didn't work. This time, the service happens to write better sentences than we do while being wrong.

I've been giving myself small engineering experiments to work through. AI Native Software Engineer, AI Agent Architect, AI Reliability Engineer, Multi Agent Systems Engineer, Human AI Workflow Architect, AI Forward Engineer... Written together, those sound less like one person's career plan and more like an entire department's hiring budget. Before trying to fit them into a LinkedIn headline, I thought I should do some of the work.

That's what **AI Native SWE** is for. Build small things and poke at them. Where does a model help? How much authority should an agent have? If several agents agree with each other, have we solved anything? Where does a human need to step in? I'd like to work through those questions in code. This episode doesn't have an agent army. Let's connect one external service properly first. More participants will bring their own problems soon enough.

Our scenario is a customer support system. A support agent opens a ticket, and category rules produce a canned response. We want to add an LLM suggestion that the person can review, edit, and send.

“Call the API and put the response on screen” is the short part. This repository deals with what follows: What if the response is broken, arrives late, contains personal data, or the provider spends the afternoon returning HTTP 500?

One detail up front: There's no real LLM provider here. There's a local mock HTTP service. This is a small experiment in integration boundaries, not a story about something I've successfully shipped to production. I can find my own mistakes without paying for tokens yet. Excellent unit economics.

## The canned response hasn't done anything wrong

The existing flow generates a deterministic response for a `refund`, `shipping`, or `general` ticket. Same category, same template. Its literary merit is debatable, but its behavior is predictable.

The LLM suggestion sits on top of that. If a usable suggestion arrives, we can use it. Otherwise, the canned response is still available. The human decides what actually goes to the customer.

The screen behavior I want is simple: Show the fallback immediately, then offer the model's suggestion after it passes our checks. An “AI is thinking” indicator shouldn't turn a working support dashboard into a waiting room.

**The demo doesn't implement that entire screen experience.** The CLI computes the fallback before running the LLM attempt, but prints the scenario's lines after it finishes. The HTTP endpoint used for Postman also computes the fallback first, then awaits `suggest()` and sends one response. A real interface needs a delivery mechanism such as separate requests, polling, or streaming to show the fallback immediately.

“Computed first” and “shown to the user first” are different things. A fast backend that hasn't told the user anything yet is mostly impressing itself.

## “Please return JSON” isn't a contract

We can ask for JSON in the prompt. We can even ask very politely. The application still needs to parse and check whatever crosses its boundary.

Here's an example response accepted by the contract in `src/contract.ts`:

```json
{
  "contract_version": 1,
  "suggestion_id": "123e4567-e89b-42d3-a456-426614174000",
  "status": "suggestion",
  "reply": {
    "subject": "About your refund request",
    "body": "Hello, we have received your refund request and will follow up after reviewing it."
  },
  "confidence": 0.72,
  "metadata": {
    "model": "mock-gpt-1",
    "generated_at": "2026-10-19T09:30:00.000Z",
    "latency_ms": 42
  }
}
```

The subject must contain 1–200 characters, the body 1–4000. `confidence` must be a number between 0 and 1, or `null`. The suggestion ID must be a UUID, and the timestamp must match the schema's ISO datetime format.

That `0.72` doesn't mean we have evidence that the answer has a 72% chance of being correct. The demo doesn't measure calibration or use confidence to decide whether to accept the suggestion. A decimal point isn't peer review.

There's also `status: "unavailable"`, which requires `reply: null`. The provider is allowed to return no suggestion. We don't treat that as malformed JSON, and we exclude it from the contract violation denominator. A mock being able to return this state obviously doesn't prove that a real model knows when to stop guessing.

I use Zod's `.strict()` on the top-level object. If the provider adds an unexpected `sentiment` field, we reject the response. There's a cost: Even a harmless extra field can break the integration. For this experiment, I've chosen explicit version management over silently accepting those additions. That strictness is only configured at the top level; the nested objects don't have the same unknown-field policy.

## The provider's DTO shouldn't move in permanently

Incoming data follows this path:

```text
Raw HTTP body
  → JSON.parse          → parse_error
  → contract_version    → version_mismatch
  → Zod schema          → schema_violation
  → toDomain()          → Suggestion or null
```

`parseContract()` accepts raw text and returns either a validated payload or a classified violation. Then `toDomain()` maps the external representation into our own type:

```ts
export type Suggestion = {
  suggestionId: string;
  subject: string;
  body: string;
  confidence: number | null;
};
```

`src/domain.ts` doesn't know about Zod or the provider's DTO. `suggestion_id` stays outside; `suggestionId` is what our application uses. This boundary is called an anti-corruption layer. The name sounds like it requires a parliamentary committee. The implementation mostly requires keeping someone else's data model out of our business logic.

The service returns either a suggestion or a reason such as `timeout`, `contract_violation`, or `pii_detected`. Callers don't each invent their own interpretation of the provider's JSON.

## The model doesn't get an unlimited thinking allowance

There are two budgets in `src/config.ts`:

```ts
export const BUDGETS = { TOTAL_MS: 3000, LLM_CALL_MS: 2200 } as const;
```

3000 ms is the total budget tracked when scheduling attempts in the service flow. 2200 ms is the default ceiling for one HTTP attempt. `src/llmClient.ts` uses an `AbortController` to cancel the request when its timer fires. Actual cancellation also depends on event loop scheduling. Adding a stopwatch doesn't promote JavaScript to a real-time operating system.

If the first attempt returns a 5xx and time remains, we allow one retry. Its deadline is the smaller of 2200 ms and the remaining total budget. So 2200 ms isn't a shared ceiling for the entire retry sequence. Parsing and PII checks happen afterward, and nothing here measures an end-to-end browser rendering deadline.

The retry policy is deliberately limited:

| Outcome | Retry | Reason |
|---|---|---|
| HTTP 5xx | At most once, if time remains | The server failure might be temporary. |
| Timeout | No | We've waited enough for this suggestion. |
| Invalid JSON / schema / version | No | This attempt returned data outside the contract. |
| PII in output | No | Reject the suggestion and use the fallback. |
| `unavailable` | No | The provider validly returned no suggestion. |
| HTTP 4xx / network error | No | This example's policy is to stop here. |

Not retrying malformed JSON doesn't mean the model would certainly make the same mistake twice. It's a choice to limit time and request count for this feature. “Try again” is easy to type. The person waiting at the other end has a less theoretical relationship with latency.

## A phone number in a prompt is still a phone number

We send only the ticket's subject, body, and category. The subject and body pass through `maskPii()` first. Recognized phone, email, and 11-digit national ID patterns become `[masked-phone]`, `[masked-email]`, and `[masked-national_id]`.

We also scan **both the subject and body** of the returned suggestion with `detectPii()`. A match rejects the suggestion with reason `pii_detected`. Masking the input doesn't earn the output a free pass.

These checks use regular expressions. Names, addresses, phone numbers written as words, and formats from other countries can fall outside their coverage. A match also doesn't establish that the data came from another customer. This example recognizes certain patterns and rejects them. Asking a regex to establish data provenance and provide legal counsel feels like scope creep.

There's no persistent database for suggestions; counters and breaker state live in memory. Those choices alone don't establish GDPR or KVKK compliance. An actual integration also needs decisions about provider processing, retention, and access.

The demo's content exposure deserves a precise description too. Service metrics track outcome codes rather than message text, but the CLI prints the accepted mock suggestion's subject. The HTTP demo response exposes ticket and suggestion contents for inspection. Those debugging conveniences need a review before anything handles real customer data.

## We should be able to turn it off

Handling each failed request isn't enough. If the provider keeps returning broken responses, we should stop knocking on the same door.

`src/metrics.ts` contains a rolling window of the last 20 recorded outcomes and a circuit breaker. `unavailable` is excluded from the violation denominator; timeout and PII rates use the total recorded count.

| Measurement | Threshold |
|---|---|
| Contract violation rate | Greater than 10% |
| Timeout rate | Greater than 50% |
| PII detection rate | Greater than 10% |
| Breaker p99 from accepted calls | Above 2200 ms, with tracking advanced by two distinct high p99 values |

That last row is awkward because the implementation is more specific than “two slow calls trip the breaker.” Its streak advances when the high p99 value changes. Timeouts don't contribute latency samples. With this small window, p99 is effectively the largest recorded latency anyway. Writing “p99” on a dashboard doesn't suddenly give us a large-scale performance study.

An open breaker stops new LLM calls for 60 seconds. After that, `half_open` permits one probe. An accepted suggestion closes the breaker; a timeout, contract violation, or PII rejection during that probe opens it again. We can also disable calls before they start with `flagEnabled = false`.

These are experiment settings. There's no minimum sample count, so a violation on the first call can produce a 100% rate and open the breaker. `provider_error` outcomes aren't recorded in these windows either, and recovery is incomplete when a half-open probe returns `provider_error` or `unavailable`. Those paths need work before real use. Installing a fuse doesn't certify the entire building's wiring.

## What are the contract tests actually testing?

I'm not testing whether the model writes a good answer here. I'm testing **what our application does** when the provider behaves in different ways at the boundary.

`src/provider.ts` supplies ten modes through a local HTTP server:

| Mode | Experiment |
|---|---|
| `valid` | Is the valid fixture accepted? |
| `unavailable` | Is no suggestion handled as a valid outcome? |
| `malformed_json` | Is non-JSON text rejected? |
| `wrong_type` | Does `confidence: "high"` get through? It shouldn't. |
| `unknown_field` | Is an extra top-level field rejected? |
| `version_2` | Is an unsupported contract version stopped at the boundary? |
| `pii_body` | Is a suggestion containing a phone number rejected? |
| `slow` | Does the client time out against a 2600 ms provider delay? |
| `flaky_500` | Does the one permitted retry recover from an initial 500? |
| `always_500` | Do we stop trying when the provider keeps returning 500? |

This isn't a setup that verifies both sides of a contract against a real provider. It exercises the consumer boundary using mock responses we control. We'd still need to verify that the actual provider meets the contract.

More to the point, passing the schema doesn't make an answer correct. A customer can ask for a refund and receive shipping advice wrapped in immaculate JSON. Contract checks won't catch that. A real model needs separate content evaluations, task correctness checks, prompt injection testing, and human review. All the braces can be in the right places while the answer is useless.

## A timely answer to yesterday's question

There's another timing problem. While the model works on ticket version 1, the customer can add a new message. The suggestion arrives within budget but answers a question that has changed.

The repository has ticket versions and `bumpVersion()`. A deterministic fallback's ID includes `${ticket.id}-d${ticket.version}`. **The LLM suggestion carries the provider's UUID, which doesn't establish freshness.** There's no implemented flow that compares the request's ticket version with the current version and rejects a stale LLM suggestion.

In a product, we'd capture the ticket ID and version when starting the request, then compare them again before applying the suggestion. I'd also want an automated test of that race. Spending 2200 ms preparing “Have you tried restarting it?” after the customer has already resolved the issue is a particularly efficient way to look unhelpful.

## Let's break it locally

With Node.js 20 or later:

```bash
npm install
npm test
npm run typecheck
npm run demo
```

The CLI runs six scenarios: `valid`, `unavailable`, `malformed_json`, `pii_body`, `slow`, and `flaky_500`. To try every mode over HTTP:

```bash
npm run server
```

Import `postman_collection.json` into Postman. For example, send this to `POST http://127.0.0.1:3000/api/suggest`:

```json
{
  "ticketId": "t-refund",
  "mode": "malformed_json"
}
```

You'll get `contract_violation` in `llmResult.reason` and the fallback in `finalDisplayedSuggestion`. That's the demo endpoint's field name; there isn't a frontend displaying it yet.

The HTTP demo shares breaker state between requests. If one scenario opens the breaker, another mode may return `circuit_open`. Use `POST /api/breaker/reset` for a fresh scenario. The CLI instead starts each scenario with its own clean breaker. Give the mock a fair trial before concluding that `valid` is broken too.

## What would bring this closer to a real system?

First, a real provider adapter, a freshness check, and an interface flow that actually delivers the fallback early. With multiple instances, we'd also need to decide which metrics and breaker decisions should be local and which should be shared. Right now, each process lives in its own little world.

Then I'd consider a shadow phase: Make calls and measure outcomes without showing suggestions to support staff. That still sends data to a provider and incurs costs; hiding the result doesn't make the experiment free of risk. Afterward, a small opt-in support group and a gradual rollout based on measurements. Those are possible next steps, not rollout features implemented in this repository.

The work in this episode sits closest to AI Reliability Engineer territory: Recognize a broken response, limit waiting, and turn the feature off when necessary. Having a human review and send the draft opens the Human AI Workflow Architect discussion too. When I give agents tools and permissions, I'll need to think about contracts for actions. When there are several agents, their messages will need boundaries as well. For now, I'm practicing with one HTTP service.

Which brings me back to my answer to that colleague. We're still checking external data, deciding when to give up on a service, and leaving the user a working path.

The service can now introduce its wrong answer with “Absolutely, I'd be happy to help.” We'll still check the tests.

## Source code and references

- [Demo repository and setup instructions](https://github.com/onurozkir/ai-llm-contract-testing)
- [Contract schema and domain mapping](https://github.com/onurozkir/ai-llm-contract-testing/blob/main/src/contract.ts)
- [Timeout, retry and PII orchestration](https://github.com/onurozkir/ai-llm-contract-testing/blob/main/src/suggestionService.ts)
- [Metrics and circuit breaker](https://github.com/onurozkir/ai-llm-contract-testing/blob/main/src/metrics.ts)
