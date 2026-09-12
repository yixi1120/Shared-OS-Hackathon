> 当前单次报告规则与产品边界以 [思棋 V1 冻结规范](docs/siqi/INTERACTION_REPORT_V1.md) 为准；[核查与交接](docs/siqi/AUDIT_AND_HANDOFF.md) 列出本文件中的历史规划冲突。Reputation Snapshot 尚未提供，不对外出售；新价格已确认并在本地实现，见[定价政策](docs/siqi/PRICING_DECISION.md)。

# SharedOS Agent Commerce Network

An autonomous buyer-and-seller agent for the SharedOS Hackathon. The implementation
focuses on the assigned **Agent Strategy / LangGraph / Harness** workstream and can be
tested end to end without a paid model key.

## What it does

- Competes in the Critique round: discovers distinct products, objectively probes at least
  three with bounded concurrency, then translates the recorded evidence into the required
  disagreement and ranking.
- Competes in the Market round: creates a value-ranked purchase plan, spends 80–100 of
  the 100 credits, and buys from at least three distinct sellers.
- Sells machine-readable **A2A Interaction Trace** and **A2A Interaction Risk Report**
  services. The service checks task completion, artifact delivery, event order, latency,
  schema validity, disputes, and evidence provenance without claiming credit settlement.
- Publishes packaged input/output contract identifiers and deterministic product-introduction,
  pricing, privacy, provenance, reputation, and critique-defense responses without requiring
  a model call.
- Quotes and negotiates within a reservation-price floor, accepts orders idempotently, delivers
  results, and keeps an auditable SQLite order ledger.
- Persists LangGraph checkpoints and derives stable purchase idempotency keys from the
  Arena run, service, and plan position so a resumed node cannot double-pay.
- Reuses stable keys when retrying feedback, ranking, and purchases after an ambiguous
  timeout, preventing a lost acknowledgement from duplicating external side effects.
- Writes every outbound purchase intent to a separate SQLite operation journal before
  contacting the Arena, then reconciles ambiguous results against the platform receipt
  and matching buyer-debit/seller-credit ledger entries.

```mermaid
flowchart LR
  A[SharedNet adapter] --> B[LangGraph Arena workflow]
  B --> C[Objective probe + required feedback]
  B --> D[Market purchase policy]
  E[Seller FastAPI] --> F[Pricing + negotiation]
  E --> G[A2A interaction evidence evaluator]
  F --> H[(SQLite ledger)]
  G --> H
  I[Optional low-cost model] -. JSON decisions only .-> B
```

Execution scores, compliance, and pricing decisions are deterministic. Free-form critique
text is an Arena compatibility output and never affects the interaction score. This keeps the Arena agent
predictable and cheap; a language model is optional for ambiguous text analysis rather
than required for every state transition.

## Crash-safe purchase protocol

Market purchases run as one LangGraph cycle per service:

```text
prepare_purchase -> execute_purchase -> record_purchase -> next purchase
                         |
                         +-> reconcile_purchase -> record_purchase
```

`prepare_purchase` commits a `PREPARED` operation with a stable idempotency key to the
outbound journal. `execute_purchase` durably changes it to `SUBMITTED` before making the
network call. If the process dies after remote payment but before the next LangGraph
checkpoint, recovery sees the submitted journal entry and reconciles it rather than
blindly paying again.

Reconciliation prioritizes an official Arena receipt. Matching buyer debit and seller
credit entries produce `BILATERALLY_CONFIRMED`, while mismatched entries produce
`DISPUTED`. Bilateral confirmation is retained as evidence but is not counted as official
credit settlement. Missing evidence stays `UNKNOWN`, and automatic repayment is blocked.

For process-level durability, use both an `AsyncSqliteSaver` at `CHECKPOINT_PATH` and a
`SqliteOperationJournal` at `OPERATION_JOURNAL_PATH`. The checkpoint stores workflow
state; the journal closes the side-effect gap between a remote transaction and the next
checkpoint. `persistent_arena_runner(...)` wires both stores from `Settings` and should
be used for the real Arena process; the in-memory defaults remain convenient for unit
tests.

## Run it

Requires `uv` and Python 3.11+.

```bash
uv sync
uv run pytest -q
uv run arena-harness
uv run seller-harness
uv run commerce-api
```

The seller API then exposes Swagger documentation at `http://localhost:8000/docs`.
Other agents can discover and call the product without opening the Dashboard:

```bash
uv run interaction-client --base-url http://127.0.0.1:8000 catalog
uv run interaction-client --base-url http://127.0.0.1:8000 analyze \
  --service-id a2a-interaction-trace \
  --buyer-id buyer-agent \
  --budget 6 \
  --input dashboard/success.json \
  --idempotency-key buyer-agent-task-001
```

See [the Agent-facing CLI guide](docs/AGENT_CLIENT.md). The client handles service
workflow and idempotency only; it does not claim Arena credit settlement.

To run the same-origin product Dashboard against the real local Seller API, use:

```bash
SELLER_API_TOKEN=local-demo-token uv run python run_dashboard.py
```

Then open `http://127.0.0.1:8786/dashboard/`. The Dashboard loads fixture *inputs* but
obtains every displayed report through the live quote, order, and delivery endpoints.
It does not simulate Arena settlement or upgrade self-reported evidence.

Its temporary service-order sequence is:

1. `GET /v1/catalog`
2. `GET /v1/contracts/interaction-v1`
3. `POST /v1/quotes`
4. optionally `POST /v1/quotes/{quote_id}/negotiate`
5. `POST /v1/orders` with an idempotency key
6. `POST /v1/orders/{trade_id}/deliver`

The temporary commerce adapter accepts a list of consented A2A task events. Caller-submitted
events are always marked `self_reported`; a caller cannot label its own data as verified.
Raw prompts and private payload contents are excluded in favor of hashes and minimum metadata.
Credit settlement remains the Arena's responsibility and is reported as `not_evaluated`
until an organizer-provided receipt contract is available.

Set `SELLER_API_TOKEN` in any networked deployment. The catalog remains public for
discovery, while quote, negotiation, order, delivery, and order lookup endpoints require
`Authorization: Bearer <token>`. This is a provisional ingress guard; replace it with the
organizer-advertised A2A security scheme and bind authenticated identity to `buyer_id`
when that contract is available.

For interim per-Agent identity, set secret `SELLER_AGENT_TOKENS_JSON` to a JSON mapping
from principal/buyer IDs to unique bearer tokens of at least 24 characters. The server
hashes those tokens at startup, exposes authenticated identity at `/v1/auth/whoami`,
binds quote/order/delivery access to that principal, and rejects buyer impersonation.
`SELLER_API_TOKEN` remains an operator/break-glass credential. This local mapping does
not replace official SharedOS capability verification or elevate evidence provenance.

`seller-harness` creates concurrent buyer personas and deliberately replays every order,
mutates reused idempotency keys, and attempts to spoof trusted provenance. For a timed
soak run, use `uv run seller-harness --concurrency 16 --duration-seconds 7200`.
For a resource-bounded persistent run, add
`--ledger-path ./tmp/seller-soak.sqlite3 --round-pause-seconds 0.5`; progress is
written to stderr every 60 seconds and the final JSON report to stdout.
Give every persistent run a unique `--run-id`. Use `--progress-path` and
`--report-path` to retain machine-readable evidence independently of the terminal:

```bash
uv run seller-harness \
  --concurrency 16 \
  --duration-seconds 7200 \
  --round-pause-seconds 0.5 \
  --run-id arena-soak-01 \
  --ledger-path ./tmp/arena-soak-01/ledger.sqlite3 \
  --progress-path ./tmp/arena-soak-01/progress.jsonl \
  --report-path ./tmp/arena-soak-01/report.json
```

## Model and cost policy

Copy `.env.example` to `.env` only when live model calls are needed. The default is
OpenRouter with `z-ai/glm-5.3-flash`, falling back to
`deepseek/deepseek-v4-flash-0731`. The client uses an OpenAI-compatible HTTP contract,
so the provider or model can be swapped through environment variables without code
changes. No OpenAI account or key is required.

Cost controls:

- deterministic rules handle Arena compliance, scoring, budgets, and pricing;
- live model calls have an 800-token output cap;
- structured JSON prevents verbose free-form generations;
- the fallback is attempted only if the primary request fails.

## SharedNet integration boundary

SharedNet's published `sharednet.room.v1` protocol is now implemented by
`SharedNetRoomClient`. Given an organizer-issued `ROOM=rom_...` and `TOKEN=rit_...`, it
can join the room, retain the returned `sni_...` member credential, read history, send
messages, and long-poll in canonical `sequence` order. A sent message deliberately does
not advance the receive cursor, so concurrent messages cannot be skipped.

The room transport and the Arena business protocol are separate. SharedNet's current
OpenAPI document contains no product, critique, ranking, purchase, payment, or credits
routes. `SharedNetRoomClient` therefore does not pretend to implement `ArenaClient`, and
the older `HttpArenaClient` remains a provisional adapter until the organizer publishes
the competition message/schema contract.

Still-required organizer contract operations:

- discover services;
- invoke a product during evaluation;
- post a critique;
- submit rankings;
- buy a service and receive a settlement receipt.

Room secrets must stay outside Git and chat messages. Configure them at runtime with
`SHAREDNET_ROOM_ID`, `SHAREDNET_INVITE_TOKEN`, and—after the first join—
`SHAREDNET_MEMBER_TOKEN`. Persist `SHAREDNET_LAST_SEQUENCE` with the member credential
so a restarted Agent resumes without skipping messages. Until a signed Arena settlement
contract exists, seller outputs continue to report `credit_settlement=not_evaluated`.

### Production room listener

`sharednet-agent` is the unattended production entry point. It joins a room once with
the organizer-issued invite, stores the returned member identity in a private `0600`
file, resumes that same identity after restart, and consumes messages through the
durable SQLite inbox. It responds only to versioned discovery/query messages or text
that names this product. Every reply carries a `reply_to` marker; after an ambiguous
restart the listener checks the room for that marker before sending again.

First start with an organizer-issued room invite:

```bash
export SERVICE_BASE_URL=https://modelscope-sharedos.tail81043f.ts.net
export SHAREDNET_ROOM_ID=rom_from_organizer
export SHAREDNET_INVITE_TOKEN=rit_from_organizer
uv run sharednet-agent listen --announce
```

The invite is not stored. The resulting member token and member/seat ID are saved to
`.sharednet/runtime-identity.json`, while `.sharednet/inbox.sqlite3` retains the receive
cursor and unacknowledged messages. Both paths must be on persistent storage. On later
starts the invite can be removed from the environment; the saved member identity is
reused automatically. To inject a credential from an external secret store instead,
set both `SHAREDNET_MEMBER_TOKEN` and `SHAREDNET_MEMBER_ID`.

For a non-sending smoke test, omit `--announce` and add `--once --poll-timeout 0`.
Never place a real `rit_`, `sni_`, seller bearer token, or Arena token in Git, a room
message, or a screenshot.

The same command also exposes an `arena` subcommand that runs the existing persistent
LangGraph only when the organizer publishes all REST business routes. It fails closed
if any route is absent instead of inventing purchase or credit semantics:

```bash
uv run sharednet-agent arena --mode critique --run-id official-critique-round
uv run sharednet-agent arena --mode market --run-id official-market-round
```

This room identity authenticates membership to SharedNet. It does **not** turn the
Seller API's provisional shared Bearer token into per-agent SharedOS authentication.
Until the organizer provides the principal/capability verification contract, caller
events remain `self_reported` and the public URL must not claim verified settlement.
Operational details and a preflight checklist are in
[the production runbook](docs/PRODUCTION_AGENT.md).

## Important files

- `src/sharedos_commerce_agent/graph.py` — compiled LangGraph workflow
- `src/sharedos_commerce_agent/arena.py` — round orchestration and hard-rule checks
- `src/sharedos_commerce_agent/strategy.py` — required feedback, ranking, purchase, and pricing logic
- `src/sharedos_commerce_agent/telemetry.py` — deterministic A2A interaction evidence evaluation
- `src/sharedos_commerce_agent/sales.py` — deterministic product introduction and buyer-response policy
- `src/sharedos_commerce_agent/resources/` — packaged catalog, sales content, and wire contracts
- `tests/test_graph.py` — routing plus in-memory and SQLite crash-recovery tests
- `src/sharedos_commerce_agent/api.py` — seller REST API
- `src/sharedos_commerce_agent/ledger.py` — idempotent service-order ledger
- `src/sharedos_commerce_agent/operation_journal.py` — durable outbound side-effect journal
- `src/sharedos_commerce_agent/harness.py` — full offline Arena simulation
- `src/sharedos_commerce_agent/seller_harness.py` — concurrent seller and soak simulation
- `dashboard/` and `run_dashboard.py` — live local product Dashboard and same-origin adapter
- `docs/guansheng/` — machine-readable product materials, schemas, sales copy, and V3 handbook
- `tests/` — unit and end-to-end coverage
