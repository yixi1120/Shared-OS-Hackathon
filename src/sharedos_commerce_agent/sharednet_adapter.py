from __future__ import annotations

from dataclasses import dataclass

import httpx

from .models import RankingEntry, ServiceListing, ServiceResult, TradeReceipt


@dataclass(frozen=True, slots=True)
class SharedNetRoutes:
    """Organizer-supplied paths; intentionally has no guessed defaults."""

    discover: str
    invoke: str
    critique: str
    ranking: str
    buy: str


class HttpArenaClient:
    """REST adapter for the ArenaClient boundary.

    Route templates may contain ``{service_id}``. If the organizer's payload schema
    differs, only this adapter needs to change; the strategy and compliance graph do not.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str,
        routes: SharedNetRoutes,
        timeout_seconds: float = 30,
    ) -> None:
        self.routes = routes
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def discover_services(self) -> list[ServiceListing]:
        response = await self.client.get(self.routes.discover)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("services", payload) if isinstance(payload, dict) else payload
        return [ServiceListing.model_validate(record) for record in records]

    async def invoke_service(self, listing: ServiceListing) -> ServiceResult:
        path = self.routes.invoke.format(service_id=listing.service_id)
        response = await self.client.post(
            path, json={"service_id": listing.service_id, "mode": "evaluate"}
        )
        response.raise_for_status()
        return ServiceResult.model_validate(response.json())

    async def post_critique(self, critique_text: str, product_id: str) -> None:
        response = await self.client.post(
            self.routes.critique,
            json={"product_id": product_id, "critique": critique_text},
        )
        response.raise_for_status()

    async def submit_ranking(self, rankings: list[RankingEntry]) -> None:
        response = await self.client.post(
            self.routes.ranking,
            json={"rankings": [item.model_dump(mode="json") for item in rankings]},
        )
        response.raise_for_status()

    async def buy(self, listing: ServiceListing) -> TradeReceipt:
        path = self.routes.buy.format(service_id=listing.service_id)
        response = await self.client.post(
            path,
            json={
                "service_id": listing.service_id,
                "seller_id": listing.seller_id,
                "amount": listing.price,
            },
        )
        response.raise_for_status()
        return TradeReceipt.model_validate(response.json())
