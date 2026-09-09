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
    assert len(result["scenarios"]) == 9
    assert {item["valid"] for item in result["scenarios"]} == {True, False}
