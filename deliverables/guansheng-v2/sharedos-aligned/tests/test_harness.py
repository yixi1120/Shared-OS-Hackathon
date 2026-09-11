from sharedos_commerce_agent.harness import run_harness, run_suite


async def test_full_arena_harness_is_compliant() -> None:
    result = await run_harness()

    assert result["valid"] is True
    assert result["phase"] == "complete"
    assert result["report"]["progress"]["spent_credits"] >= 80
    assert len(result["report"]["progress"]["purchased_products"]) >= 3
    assert result["side_effects"]["critiques_posted"] == 3
    assert result["side_effects"]["ranking_entries"] == 3


async def test_fault_injection_suite_matches_expectations() -> None:
    result = await run_suite()

    assert result["suite_passed"] is True
    assert len(result["scenarios"]) == 14
    assert {item["valid"] for item in result["scenarios"]} == {True, False}

    ack_loss_scenarios = [
        item for item in result["scenarios"] if "ack_is_lost" in item["scenario"]
    ]
    assert len(ack_loss_scenarios) == 3
    assert all(item["valid"] for item in ack_loss_scenarios)
    assert all(
        item["side_effects"]
        == {"critiques_posted": 3, "ranking_entries": 3, "purchases": 4}
        for item in ack_loss_scenarios
    )
