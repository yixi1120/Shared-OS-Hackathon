from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .config import Settings
from .models import (
    ArenaProgress,
    ArenaReport,
    ArenaRunMode,
    RankingEntry,
    ServiceListing,
    ServiceResult,
    TradeReconciliation,
    TradeReceipt,
)
from .operation_journal import (
    InMemoryOperationJournal,
    OperationJournal,
    SqliteOperationJournal,
)
from .sales import SalesPolicy, SalesReply
from .strategy import CritiqueStrategy, MarketStrategy


class ArenaClient(Protocol):
    """Boundary to replace once the organizer publishes the SharedNet contract."""

    async def discover_services(self) -> list[ServiceListing]: ...

    async def invoke_service(self, listing: ServiceListing) -> ServiceResult: ...

    async def post_critique(
        self, critique_text: str, product_id: str, *, idempotency_key: str
    ) -> None: ...

    async def submit_ranking(
        self, rankings: list[RankingEntry], *, idempotency_key: str
    ) -> None: ...

    async def buy(
        self, listing: ServiceListing, *, idempotency_key: str
    ) -> TradeReceipt: ...

    async def reconcile_trade(
        self, listing: ServiceListing, *, idempotency_key: str
    ) -> TradeReconciliation: ...


class ArenaRunner:
    def __init__(
        self,
        client: ArenaClient,
        *,
        critique_strategy: CritiqueStrategy | None = None,
        market_strategy: MarketStrategy | None = None,
        checkpointer=None,
        operation_journal: OperationJournal | None = None,
        sales_policy: SalesPolicy | None = None,
        max_concurrent_evaluations: int = 3,
    ) -> None:
        self.client = client
        self.critique_strategy = critique_strategy or CritiqueStrategy()
        self.market_strategy = market_strategy or MarketStrategy()
        self.checkpointer = checkpointer or InMemorySaver()
        self.operation_journal = operation_journal or InMemoryOperationJournal()
        self.sales_policy = sales_policy or SalesPolicy()
        self.max_concurrent_evaluations = max_concurrent_evaluations

    def product_introduction(self) -> str:
        return self.sales_policy.introduction

    def answer_buyer(self, message: str) -> SalesReply:
        return self.sales_policy.respond(message)

    async def run(self, agent_id: str) -> ArenaReport:
        return await self.run_round(agent_id, ArenaRunMode.FULL_DRY_RUN)

    async def run_round(
        self,
        agent_id: str,
        mode: ArenaRunMode,
        *,
        progress: ArenaProgress | None = None,
        run_id: str | None = None,
    ) -> ArenaReport:
        # Local import avoids a module cycle: graph nodes depend on ArenaClient.
        from .graph import build_arena_graph

        graph = build_arena_graph(
            self.client,
            critique_strategy=self.critique_strategy,
            market_strategy=self.market_strategy,
            checkpointer=self.checkpointer,
            operation_journal=self.operation_journal,
            max_concurrent_evaluations=self.max_concurrent_evaluations,
        )
        active_run_id = run_id or str(uuid4())
        graph_input = {
            "agent_id": agent_id,
            "run_id": active_run_id,
            "run_mode": mode,
        }
        if progress is not None:
            graph_input["progress"] = progress
        config = {"configurable": {"thread_id": active_run_id}}
        state = await graph.ainvoke(graph_input, config=config)
        return state["report"]

    async def resume(self, run_id: str) -> ArenaReport:
        """Resume the unfinished graph identified by a previously persisted run ID."""

        from .graph import build_arena_graph

        graph = build_arena_graph(
            self.client,
            critique_strategy=self.critique_strategy,
            market_strategy=self.market_strategy,
            checkpointer=self.checkpointer,
            operation_journal=self.operation_journal,
            max_concurrent_evaluations=self.max_concurrent_evaluations,
        )
        config = {"configurable": {"thread_id": run_id}}
        state = await graph.ainvoke(None, config=config)
        if "report" not in state:
            raise RuntimeError(f"Arena run {run_id} did not reach its audit report")
        return state["report"]


@asynccontextmanager
async def persistent_arena_runner(
    client: ArenaClient,
    *,
    settings: Settings | None = None,
    critique_strategy: CritiqueStrategy | None = None,
    market_strategy: MarketStrategy | None = None,
    sales_policy: SalesPolicy | None = None,
    max_concurrent_evaluations: int = 3,
) -> AsyncIterator[ArenaRunner]:
    """Create a runner with both workflow and side-effect durability enabled."""

    active_settings = settings or Settings.from_env()
    async with AsyncSqliteSaver.from_conn_string(
        active_settings.checkpoint_path
    ) as checkpointer:
        yield ArenaRunner(
            client,
            critique_strategy=critique_strategy,
            market_strategy=market_strategy,
            checkpointer=checkpointer,
            operation_journal=SqliteOperationJournal(
                active_settings.operation_journal_path
            ),
            sales_policy=sales_policy,
            max_concurrent_evaluations=max_concurrent_evaluations,
        )
