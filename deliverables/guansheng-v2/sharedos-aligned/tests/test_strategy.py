import pytest

from sharedos_commerce_agent.harness import MOCK_LISTINGS
from sharedos_commerce_agent.models import QuoteRequest
from sharedos_commerce_agent.strategy import ComplianceError, MarketStrategy, PricingPolicy


def test_quote_and_negotiation_respect_floor() -> None:
    policy = PricingPolicy()
    quote = policy.quote(
        QuoteRequest(
            buyer_id="buyer", service_id="a2a-interaction-trace", budget=50
        ),
        first_purchase=True,
    )

    assert quote.reservation_price <= quote.ask_price <= 50
    rejected = policy.negotiate(quote, max(1, quote.reservation_price - 1))
    assert not rejected.accepted
    assert rejected.counter_price >= quote.reservation_price

    accepted = policy.negotiate(quote, quote.reservation_price)
    assert accepted.accepted
    assert accepted.final_price == quote.reservation_price


def test_market_plan_satisfies_arena_rules() -> None:
    plan = MarketStrategy().plan_purchases(
        MOCK_LISTINGS, own_agent_id="agent-commerce-network"
    )

    assert 80 <= sum(item.price for item in plan) <= 100
    assert len({item.seller_id for item in plan}) >= 3


def test_market_plan_fails_closed_without_three_products() -> None:
    with pytest.raises(ComplianceError):
        MarketStrategy().plan_purchases(
            MOCK_LISTINGS[:2], own_agent_id="agent-commerce-network"
        )
