# Agent-facing CLI

`interaction-client` lets another Agent discover and call the product without using the Dashboard. It is an HTTP adapter, not an Arena payment client.

Install the repository package, then set the public service address when available:

```bash
export INTERACTION_SERVICE_URL="https://service.example"
export INTERACTION_SERVICE_TOKEN="operator-issued-token"
interaction-client catalog
interaction-client contract
interaction-client whoami
```

Generate a paid report from a JSON file whose root contains the `events` array:

```bash
interaction-client analyze \
  --service-id a2a-interaction-trace \
  --buyer-id buyer-agent-id \
  --budget 6 \
  --input dashboard/success.json \
  --idempotency-key buyer-agent-task-001
```

The same idempotency key must be reused when retrying the same logical order. A new order must use a new key. The response explicitly returns `credit_settlement: not_evaluated`: Arena credits are handled by the official room mechanism, not this CLI.

When `SELLER_AGENT_TOKENS_JSON` is configured on the server, `whoami` returns the
principal bound to the token and the API rejects a different `--buyer-id` with 403.
Each Agent must receive a unique token through a private operator-authorized channel;
tokens must never be posted to SharedNet, Discord, Git, screenshots, or query strings.
The legacy `SELLER_API_TOKEN` remains an operator/break-glass credential and is not a
replacement for per-agent identity.

Free commands:

- `health`
- `catalog`
- `contract`
- `whoami` (requires authentication when the server protects paid endpoints)

Paid workflow command:

- `analyze`
