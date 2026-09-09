# Devpost 文案底稿

状态：可编辑底稿，不能直接作为已上线声明提交。方括号字段须用真实值替换；“Integration status”只在真实测试通过后改写为事实。

## Project name

Verified Agent Transaction Intelligence

## Tagline

Understand an agent trade through structured evidence, transparent risk flags, and explicit limits.

## Inspiration

In an agent marketplace, a persuasive pitch is not evidence of successful execution. Buyers need to know what a particular trade actually delivered, which claims are supported, and which remain uncertain. We focus on one transaction first, rather than claiming to solve global reputation on day one.

## What it does

Our local service accepts structured transaction lifecycle events and returns a machine-readable transaction trace. The trace describes ordering, completion, price consistency, reported latency, schema compliance, disputes, and evidence references. The current local runtime preserves source claims but does not authenticate them; a caller-supplied platform label alone is never treated as platform verification. A single report is explicitly scoped to a single transaction.

## How we built it

Our architecture separates the personal competitor agent from the inbound seller runtime. The competitor agent handles Arena participation. The local runtime implements input checks, a ledger, and delivery. SharedOS authorization, trusted evidence authentication and real Arena settlement still require production integration. A separate intelligence module owns deterministic scoring and risk rules. The sales layer explains outputs and requests runtime quotes; it cannot authorize payments or edit scores.

Integration status: [Replace with verified facts about the actual SharedOS Cloud turns, grants, purpose string, and audit references. Do not submit this placeholder or describe the offline fixture runner as production.]

## Service listing — publish only after activation

**Verified Transaction Trace.** Submit lifecycle events for one transaction and subject agent using the attached TransactionEvent schema: transaction_id, subject_agent_id, stage, occurred_at, amount, schema_valid, evidence_id, and provenance. The service returns TransactionTraceReport fields covering completion, ordering, schema validity rate, price consistency, dispute status, latency, the approved transaction reliability metric, evidence references, and risk flags. Confidence is single-transaction; source claims require runtime authentication. Price: [confirmed Arena credits]. Call on SharedNet: [actual service address and official invocation payload]. Delivery: [verified bound, no more than 300 seconds]. The service does not require raw prompts or full deliverable content.

Do not list Transaction Risk Report as a separate paid service unless its additional output is agreed and running. Do not list Reputation Snapshot unless its evidence threshold, contract, scoring rules, and delivery are all ready.

## What makes it useful to another agent

The output is structured for another agent to consume during a purchasing or debugging task. Evidence references allow a specific finding to be challenged. Missing or weaker evidence remains visible in the explanation instead of being replaced by confident sales language. Buying a report never buys a better score.

## Challenges

Distinguishing evidence submitted by one party from evidence authenticated by a trusted source is central to the design. We also keep sales, settlement, and scoring separate so that negotiation cannot alter a factual result. [Add one concrete, observed implementation challenge and how the team resolved it.]

## Accomplishments

[Insert only verified results: an external agent call and receipt, an authorization denial, a bounded delivery measurement, and a trace whose evidence can be inspected. Do not present local synthetic tests as SharedNet trades.]

## What we learned

A transaction report must state both its observed facts and its limits. One successful trade does not establish global reputation, and an evidence label is not proof of its origin.

## What is next

After the Arena service is reliable, we plan to aggregate eligible independent traces into a reputation snapshot with sample size and confidence. This future capability is not a promise included in the current trace purchase.

## Required identifiers

| Field | Actual value required |
|---|---|
| Team lead Discord username | [required] |
| Personal agent SharedNet node ID | [required] |
| SharedOS purpose string | [required] |
| Product agent addresses | [required] |
| SharedNet service invocation address | [required] |
| Repository URL, accessible to judges | [required] |
| Optional demo video, ≤2 minutes | [actual link, or omit] |

Screenshots must show actual runtime results if used to substantiate implementation. If a synthetic screenshot is retained as a UI illustration, label it clearly and do not use it as evidence of completed trades.
