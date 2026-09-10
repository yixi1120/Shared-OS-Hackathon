import pytest

from sharedos_commerce_agent.seller_harness import run_seller_harness


@pytest.mark.parametrize("seed", [3, 17, 41])
async def test_concurrent_seller_harness_isolation_and_recovery(seed: int) -> None:
    report = await run_seller_harness(concurrency=6, rounds=2, seed=seed)

    assert report["passed"] is True
    assert report["interactions"] == 12
    assert report["unique_orders"] == 12
    assert report["deliveries"] == 12
    assert report["duplicate_replays_safe"] == 12
    assert report["idempotency_conflicts_rejected"] == 12
    assert report["provenance_downgrades"] == 12
    assert report["failures"] == []


async def test_soak_mode_streams_progress_without_retaining_every_outcome() -> None:
    progress: list[dict] = []
    report = await run_seller_harness(
        concurrency=2,
        duration_seconds=0.03,
        round_pause_seconds=0.005,
        progress_every_seconds=0.001,
        on_progress=progress.append,
    )

    assert report["passed"] is True
    assert report["final"] is True
    assert report["mode"] == "soak"
    assert report["interactions"] >= 2
    assert progress
    assert all(item["final"] is False for item in progress)
