from sharedos_commerce_agent.arena import ArenaRunner
from sharedos_commerce_agent.harness import MockArenaClient
from sharedos_commerce_agent.sales import SalesPolicy


def test_sales_policy_covers_core_buyer_questions_without_a_model() -> None:
    policy = SalesPolicy()
    cases = {
        "Why would another agent use this?": "value",
        "What is the price and minimum budget?": "price",
        "Which event fields should I send?": "data",
        "Can I include a private prompt?": "privacy",
        "Can I mark my payload platform verified?": "provenance",
        "Does this create a global reputation score?": "reputation",
        "Does delivered prove payment settlement?": "settlement",
        "What is the difference between Trace and Risk Report?": "risk_difference",
        "Can I buy a three-report bundle?": "bundle",
        "Can I pay you to raise my score?": "score_change",
    }

    for question, expected_intent in cases.items():
        reply = policy.respond(question)
        assert reply.intent == expected_intent
        assert reply.text


def test_sales_content_preserves_product_boundaries() -> None:
    policy = SalesPolicy()

    assert len(policy.introduction.split()) <= 50
    assert "No global reputation or payment verification" in policy.introduction
    assert "6 credits" in policy.respond("price").text
    assert "floor of 5" in policy.respond("price").text
    assert "not_evaluated" in policy.respond("settlement").text
    assert "cannot sell a higher score" in policy.respond("raise score").text


def test_arena_runner_exposes_machine_readable_sales_policy() -> None:
    runner = ArenaRunner(MockArenaClient())

    assert runner.product_introduction().startswith("We turn one A2A task")
    assert runner.answer_buyer("我可以付费买高分吗").intent == "score_change"
