from sharedos_commerce_agent.graph import build_arena_graph
from sharedos_commerce_agent.harness import ArenaScenario, MockArenaClient
from sharedos_commerce_agent.models import ArenaRunMode


async def test_graph_exposes_business_nodes_in_execution_order() -> None:
    graph = build_arena_graph(MockArenaClient())
    visited: list[str] = []

    async for update in graph.astream(
        {"agent_id": "agent-commerce-network"}, stream_mode="updates"
    ):
        visited.extend(update)

    assert visited == [
        "prepare",
        "discover",
        "evaluate_services",
        "publish_required_feedback",
        "rank",
        "plan_market",
        "purchase",
        "audit",
    ]


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


async def test_market_round_skips_critique_actions() -> None:
    visited, state = await _visited_nodes(ArenaRunMode.MARKET)

    assert visited == ["prepare", "discover", "plan_market", "purchase", "audit"]
    assert state["progress"].critiques == []
    assert state["progress"].spent_credits >= 80
    assert state["compliant"] is True
