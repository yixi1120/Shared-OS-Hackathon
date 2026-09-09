from __future__ import annotations

from typing import Protocol

from .models import (
    ArenaProgress,
    ArenaReport,
    ArenaRunMode,
    RankingEntry,
    ServiceListing,
    ServiceResult,
    TradeReceipt,
)
from .strategy import CritiqueStrategy, MarketStrategy


class ArenaClient(Protocol):
    """Boundary to replace once the organizer publishes the SharedNet contract."""

    async def discover_services(self) -> list[ServiceListing]: ...

    async def invoke_service(self, listing: ServiceListing) -> ServiceResult: ...

    async def post_critique(self, critique_text: str, product_id: str) -> None: ...

    async def submit_ranking(self, rankings: list[RankingEntry]) -> None: ...

    async def buy(self, listing: ServiceListing) -> TradeReceipt: ...


class ArenaRunner:
    def __init__(
        self,
        client: ArenaClient,
        *,
        critique_strategy: CritiqueStrategy | None = None,
        market_strategy: MarketStrategy | None = None,
    ) -> None:
        self.client = client
        self.critique_strategy = critique_strategy or CritiqueStrategy()
        self.market_strategy = market_strategy or MarketStrategy()

    async def run(self, agent_id: str) -> ArenaReport:
        return await self.run_round(agent_id, ArenaRunMode.FULL_DRY_RUN)

    async def run_round(
        self,
        agent_id: str,
        mode: ArenaRunMode,
        *,
        progress: ArenaProgress | None = None,
    ) -> ArenaReport:
        # Local import avoids a module cycle: graph nodes depend on ArenaClient.
        from .graph import build_arena_graph

        graph = build_arena_graph(
            self.client,
            critique_strategy=self.critique_strategy,
            market_strategy=self.market_strategy,
        )
        graph_input = {"agent_id": agent_id, "run_mode": mode}
        if progress is not None:
            graph_input["progress"] = progress
        state = await graph.ainvoke(graph_input)
        return state["report"]
