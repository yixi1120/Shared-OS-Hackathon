# SharedOS Agent Commerce Network

An autonomous buyer-and-seller agent for the SharedOS Hackathon. The implementation
focuses on the assigned **Agent Strategy / LangGraph / Harness** workstream and can be
tested end to end without a paid model key.

## What it does

- Competes in the Critique round: discovers distinct products, objectively probes at least
  three, then translates the recorded evidence into the required disagreement and ranking.
- Competes in the Market round: creates a value-ranked purchase plan, spends 80–100 of
  the 100 credits, and buys from at least three distinct sellers.
- Sells machine-readable **A2A Interaction Trace** and **A2A Interaction Risk Report**
  services. The service checks task completion, artifact delivery, event order, latency,
  schema validity, disputes, and evidence provenance without claiming credit settlement.
- Quotes and negotiates within a reservation-price floor, accepts orders idempotently, delivers
  results, and keeps an auditable SQLite order ledger.
- Persists LangGraph checkpoints and derives stable purchase idempotency keys from the
  Arena run, service, and plan position so a resumed node cannot double-pay.
- Reuses stable keys when retrying feedback, ranking, and purchases after an ambiguous
  timeout, preventing a lost acknowledgement from duplicating external side effects.

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

## Run it

Requires `uv` and Python 3.11+.

```bash
uv sync
uv run pytest -q
uv run arena-harness
uv run commerce-api
```

The seller API then exposes Swagger documentation at `http://localhost:8000/docs`.
Its temporary service-order sequence is:

1. `GET /v1/catalog`
2. `POST /v1/quotes`
3. optionally `POST /v1/quotes/{quote_id}/negotiate`
4. `POST /v1/orders` with an idempotency key
5. `POST /v1/orders/{trade_id}/deliver`

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

The public hackathon material does not publish the final Arena endpoint paths, payload
schema, access token, or node ID. `HttpArenaClient` therefore requires organizer-supplied
routes instead of guessing them. Once those details arrive, configure or adjust only
`src/sharedos_commerce_agent/sharednet_adapter.py`; the strategy graph, seller API,
ledger, and tests remain unchanged.

Required organizer contract operations:

- discover services;
- invoke a product during evaluation;
- post a critique;
- submit rankings;
- buy a service and receive a settlement receipt.

## Important files

- `src/sharedos_commerce_agent/graph.py` — compiled LangGraph workflow
- `src/sharedos_commerce_agent/arena.py` — round orchestration and hard-rule checks
- `src/sharedos_commerce_agent/strategy.py` — required feedback, ranking, purchase, and pricing logic
- `src/sharedos_commerce_agent/telemetry.py` — deterministic A2A interaction evidence evaluation
- `tests/test_graph.py` — routing plus in-memory and SQLite crash-recovery tests
- `src/sharedos_commerce_agent/api.py` — seller REST API
- `src/sharedos_commerce_agent/ledger.py` — idempotent service-order ledger
- `src/sharedos_commerce_agent/harness.py` — full offline Arena simulation
- `tests/` — unit and end-to-end coverage
