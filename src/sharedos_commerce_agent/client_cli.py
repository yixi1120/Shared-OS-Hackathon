from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import httpx


class InteractionServiceClient:
    """Small agent-facing client for the public HTTP service contract."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 30,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def __enter__(self) -> "InteractionServiceClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def health(self) -> dict[str, Any]:
        return self._json(self.client.get("/health"))

    def catalog(self) -> list[dict[str, Any]]:
        payload = self._json(self.client.get("/v1/catalog"))
        if not isinstance(payload, list):
            raise ValueError("catalog response must be a JSON list")
        return payload

    def contract(self) -> dict[str, Any]:
        return self._json(self.client.get("/v1/contracts/interaction-v1"))

    def whoami(self) -> dict[str, Any]:
        return self._json(self.client.get("/v1/auth/whoami"))

    def analyze(
        self,
        *,
        service_id: str,
        buyer_id: str,
        budget: int,
        input_payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        quote = self._json(
            self.client.post(
                "/v1/quotes",
                json={
                    "buyer_id": buyer_id,
                    "service_id": service_id,
                    "budget": budget,
                },
            )
        )
        order = self._json(
            self.client.post(
                "/v1/orders",
                json={
                    "quote_id": quote["quote_id"],
                    "buyer_id": buyer_id,
                    "service_id": service_id,
                    "amount": quote["ask_price"],
                    "idempotency_key": idempotency_key,
                    "input": input_payload,
                },
            )
        )
        delivery = self._json(
            self.client.post(f"/v1/orders/{order['trade_id']}/deliver")
        )
        return {
            "quote": quote,
            "order": order,
            "delivery": delivery,
            "credit_settlement": "not_evaluated",
        }

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        response.raise_for_status()
        return response.json()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interaction-client",
        description="Agent-facing CLI for A2A Interaction Intelligence.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("INTERACTION_SERVICE_URL", "http://127.0.0.1:8000"),
        help="Service base URL (or set INTERACTION_SERVICE_URL).",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("INTERACTION_SERVICE_TOKEN"),
        help="Optional bearer token (or set INTERACTION_SERVICE_TOKEN).",
    )
    parser.add_argument("--timeout", type=float, default=30)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check service availability (free).")
    subparsers.add_parser("catalog", help="Read services and prices (free).")
    subparsers.add_parser("contract", help="Read input/output schemas (free).")
    subparsers.add_parser(
        "whoami", help="Resolve the authenticated Seller API principal."
    )

    analyze = subparsers.add_parser(
        "analyze", help="Request and deliver one paid Trace or Risk report."
    )
    analyze.add_argument(
        "--service-id",
        required=True,
        choices=("a2a-interaction-trace", "a2a-interaction-risk-report"),
    )
    analyze.add_argument("--buyer-id", required=True)
    analyze.add_argument("--budget", type=int, default=6, choices=range(5, 101))
    analyze.add_argument("--input", required=True, type=Path)
    analyze.add_argument(
        "--idempotency-key",
        default=None,
        help="Reuse this key when retrying the same logical order.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with InteractionServiceClient(
            args.base_url, token=args.token, timeout_seconds=args.timeout
        ) as client:
            if args.command == "health":
                result = client.health()
            elif args.command == "catalog":
                result = client.catalog()
            elif args.command == "contract":
                result = client.contract()
            elif args.command == "whoami":
                result = client.whoami()
            else:
                payload = json.loads(args.input.read_text(encoding="utf-8"))
                result = client.analyze(
                    service_id=args.service_id,
                    buyer_id=args.buyer_id,
                    budget=args.budget,
                    input_payload=payload,
                    idempotency_key=args.idempotency_key or f"cli-{uuid4()}",
                )
    except (OSError, ValueError, json.JSONDecodeError, httpx.HTTPError) as exc:
        print(f"interaction-client: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
