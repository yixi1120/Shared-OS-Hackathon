import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from sharedos_commerce_agent.arena import persistent_arena_runner
from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.graph import build_arena_graph
from sharedos_commerce_agent.harness import ArenaScenario, MockArenaClient
from sharedos_commerce_agent.models import ArenaRunMode
from sharedos_commerce_agent.operation_journal import SqliteOperationJournal
from sharedos_commerce_agent.operation_journal import (
    InMemoryOperationJournal,
    OperationStatus,
)


class SimulatedProcessCrash(BaseException):
    pass


class CrashAfterSecondPaymentClient(MockArenaClient):
    crashed = False

    async def buy(self, listing, *, idempotency_key):
        receipt = await super().buy(listing, idempotency_key=idempotency_key)
        if len(self.purchases) == 2 and not self.crashed:
            self.crashed = True
            raise SimulatedProcessCrash("process stopped after payment")
        return receipt


class ConcurrencyProbeClient(MockArenaClient):
    active_invocations = 0
    max_active_invocations = 0

    async def invoke_service(self, listing):
        self.active_invocations += 1
        self.max_active_invocations = max(
            self.max_active_invocations, self.active_invocations
        )
        try:
            await asyncio.sleep(0.02)
            return await super().invoke_service(listing)
        finally:
            self.active_invocations -= 1


async def test_graph_exposes_business_nodes_in_execution_order() -> None:
    graph = build_arena_graph(MockArenaClient())
    visited: list[str] = []

    async for update in graph.astream(
        {"agent_id": "agent-commerce-network"}, stream_mode="updates"
    ):
        visited.extend(update)

    assert visited[:6] == [
        "prepare",
        "discover",
        "evaluate_services",
        "publish_required_feedback",
        "rank",
        "plan_market",
    ]
    assert visited[6:-1] == [
        node
        for _ in range(4)
        for node in ("prepare_purchase", "execute_purchase", "record_purchase")
    ]
    assert visited[-1] == "audit"


async def test_conditional_edge_fails_closed_when_discovery_is_insufficient() -> None:
    client = MockArenaClient(
        scenario=ArenaScenario(name="insufficient", listings=[])
    )
    graph = build_arena_graph(client)
    visited: list[str] = []
    final_state = None

    async for event in graph.astream(
        {"agent_id": "agent-commerce-network"}, stream_mode=["updates", "values"]
    ):
        mode, payload = event
        if mode == "updates":
            visited.extend(payload)
        else:
            final_state = payload

    assert visited == ["prepare", "discover", "audit"]
    assert final_state is not None
    assert final_state["compliant"] is False


async def _visited_nodes(mode: ArenaRunMode) -> tuple[list[str], dict]:
    graph = build_arena_graph(MockArenaClient())
    visited: list[str] = []
    final_state = None
    async for event in graph.astream(
        {"agent_id": "agent-commerce-network", "run_mode": mode},
        stream_mode=["updates", "values"],
    ):
        event_mode, payload = event
        if event_mode == "updates":
            visited.extend(payload)
        else:
            final_state = payload
    assert final_state is not None
    return visited, final_state


async def test_critique_round_does_not_spend_market_credits() -> None:
    visited, state = await _visited_nodes(ArenaRunMode.CRITIQUE)

    assert visited == [
        "prepare",
        "discover",
        "evaluate_services",
        "publish_required_feedback",
        "rank",
        "audit",
    ]
    assert state["progress"].spent_credits == 0
    assert state["compliant"] is True


async def test_service_evaluations_run_with_bounded_concurrency() -> None:
    client = ConcurrencyProbeClient()
    graph = build_arena_graph(client, max_concurrent_evaluations=2)

    state = await graph.ainvoke(
        {
            "agent_id": "agent-commerce-network",
            "run_mode": ArenaRunMode.CRITIQUE,
        }
    )

    assert state["compliant"] is True
    assert client.max_active_invocations == 2


async def test_market_round_skips_critique_actions() -> None:
    visited, state = await _visited_nodes(ArenaRunMode.MARKET)

    assert visited[:3] == ["prepare", "discover", "plan_market"]
    assert visited[3:-1] == [
        node
        for _ in range(4)
        for node in ("prepare_purchase", "execute_purchase", "record_purchase")
    ]
    assert visited[-1] == "audit"
    assert state["progress"].critiques == []
    assert state["progress"].spent_credits >= 80
    assert state["compliant"] is True


async def test_checkpoint_resume_reuses_purchase_idempotency_keys() -> None:
    client = CrashAfterSecondPaymentClient()
    graph = build_arena_graph(client, checkpointer=InMemorySaver())
    run_id = "arena-market-recovery-001"
    config = {"configurable": {"thread_id": run_id}}

    with pytest.raises(SimulatedProcessCrash):
        await graph.ainvoke(
            {
                "agent_id": "agent-commerce-network",
                "run_id": run_id,
                "run_mode": ArenaRunMode.MARKET,
            },
            config=config,
        )

    recovered = await graph.ainvoke(None, config=config)

    assert recovered["compliant"] is True
    assert recovered["progress"].spent_credits == 95
    assert len(recovered["progress"].receipts) == 4
    assert len(client.purchases) == 4
    assert len(client.purchases_by_key) == 4
    assert len(client.purchase_attempts) == 4
    assert len(set(client.purchase_attempts)) == 4


async def test_sqlite_checkpoint_survives_graph_recreation(tmp_path) -> None:
    client = CrashAfterSecondPaymentClient()
    checkpoint_path = str(tmp_path / "arena-checkpoints.sqlite3")
    journal_path = str(tmp_path / "outbound-operations.sqlite3")
    run_id = "arena-market-persistent-001"
    config = {"configurable": {"thread_id": run_id}}

    async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as saver:
        first_graph = build_arena_graph(
            client,
            checkpointer=saver,
            operation_journal=SqliteOperationJournal(journal_path),
        )
        with pytest.raises(SimulatedProcessCrash):
            await first_graph.ainvoke(
                {
                    "agent_id": "agent-commerce-network",
                    "run_id": run_id,
                    "run_mode": ArenaRunMode.MARKET,
                },
                config=config,
            )

    # A new saver and graph simulate a new process reading the same checkpoint file.
    async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as saver:
        restarted_graph = build_arena_graph(
            client,
            checkpointer=saver,
            operation_journal=SqliteOperationJournal(journal_path),
        )
        recovered = await restarted_graph.ainvoke(None, config=config)

    assert recovered["compliant"] is True
    assert recovered["progress"].spent_credits == 95
    assert len(client.purchases) == 4
    assert len(client.purchases_by_key) == 4
    assert len(client.purchase_attempts) == 4
    assert len(set(client.purchase_attempts)) == 4


async def test_bilateral_confirmation_is_recorded_but_not_counted_as_settlement() -> None:
    scenario = ArenaScenario(
        name="bilateral-only",
        buy_ack_timeouts_after_success={"demand-forecast"},
        hide_platform_receipts={"demand-forecast"},
        bilateral_confirmation_services={"demand-forecast"},
    )
    client = MockArenaClient(scenario=scenario)
    journal = InMemoryOperationJournal()
    run_id = "arena-bilateral-001"
    graph = build_arena_graph(client, operation_journal=journal)

    state = await graph.ainvoke(
        {
            "agent_id": "agent-commerce-network",
            "run_id": run_id,
            "run_mode": ArenaRunMode.MARKET,
        }
    )

    operation = journal.get(
        f"{run_id}:purchase:demand-forecast:3"
    )
    assert operation is not None
    assert operation.status is OperationStatus.BILATERALLY_CONFIRMED
    assert operation.evidence is not None
    assert operation.evidence.buyer_entry is not None
    assert operation.evidence.seller_entry is not None
    assert state["progress"].spent_credits == 60
    assert any("bilaterally confirmed" in item for item in state["violations"])


async def test_mismatched_bilateral_evidence_is_disputed() -> None:
    scenario = ArenaScenario(
        name="bilateral-mismatch",
        buy_ack_timeouts_after_success={"demand-forecast"},
        hide_platform_receipts={"demand-forecast"},
        mismatched_bilateral_services={"demand-forecast"},
    )
    client = MockArenaClient(scenario=scenario)
    journal = InMemoryOperationJournal()
    run_id = "arena-disputed-001"

    state = await build_arena_graph(
        client, operation_journal=journal
    ).ainvoke(
        {
            "agent_id": "agent-commerce-network",
            "run_id": run_id,
            "run_mode": ArenaRunMode.MARKET,
        }
    )

    operation = journal.get(
        f"{run_id}:purchase:demand-forecast:3"
    )
    assert operation is not None
    assert operation.status is OperationStatus.DISPUTED
    assert state["progress"].spent_credits == 60
    assert any("reconciliation disputed" in item for item in state["violations"])


async def test_persistent_runner_wires_both_checkpoint_and_operation_journal(
    tmp_path,
) -> None:
    client = CrashAfterSecondPaymentClient()
    settings = Settings(
        checkpoint_path=str(tmp_path / "checkpoints.sqlite3"),
        operation_journal_path=str(tmp_path / "operations.sqlite3"),
    )
    run_id = "persistent-runner-001"

    async with persistent_arena_runner(client, settings=settings) as runner:
        with pytest.raises(SimulatedProcessCrash):
            await runner.run_round(
                "agent-commerce-network",
                ArenaRunMode.MARKET,
                run_id=run_id,
            )

    async with persistent_arena_runner(client, settings=settings) as runner:
        report = await runner.resume(run_id)

    assert report.valid is True
    assert report.progress.spent_credits == 95
    assert len(client.purchase_attempts) == 4
