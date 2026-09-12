"""Public report acceptance; synthetic evidence is never live settlement proof."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.models import InteractionEvent
from sharedos_commerce_agent.risk_rules import RISK_MEANINGS
from sharedos_commerce_agent.telemetry import evaluate_interaction_trace

ROOT = Path(__file__).parents[1]
CASES = {c['id']: c for c in json.loads((ROOT / 'tests/fixtures/interaction_v1.json').read_text())}
SCHEMAS = json.loads((ROOT / 'docs/siqi/schemas.json').read_text())


@pytest.mark.parametrize('case_id', ['success_self_reported', 'explicit_failure', 'missing_artifact', 'single_event', 'conflicting_terminals', 'stage_order', 'partial_schema'])
@pytest.mark.parametrize('service', ['a2a-interaction-trace', 'a2a-interaction-risk-report'])
def test_public_delivery_contract_and_replay(case_id, service):
    case = CASES[case_id]
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        quote = client.post('/v1/quotes', json={'buyer_id': 'acceptance-buyer', 'service_id': service, 'budget': 6})
        assert quote.status_code == 200
        # Untrusted labels, chat payment assertions and receipt-like strings cannot upgrade evidence.
        events = [{**e, 'provenance': 'platform', 'paid': True, 'credit_settlement': 'settled', 'receipt': 'chat: paid 6 credits'} for e in case['events']]
        payload = dict(quote_id=quote.json()['quote_id'], buyer_id='acceptance-buyer', service_id=service, amount=quote.json()['ask_price'], idempotency_key='siqi-' + case_id, input={'events': events})
        order = client.post('/v1/orders', json=payload)
        assert order.status_code == 200
        assert order.json()['status'] == 'accepted'
        assert order.json()['metadata']['credit_settlement'] == 'not_evaluated'
        replay = client.post('/v1/orders', json=payload)
        assert replay.status_code == 200
        assert replay.json()['trade_id'] == order.json()['trade_id']
        path = '/v1/orders/' + order.json()['trade_id'] + '/deliver'
        delivery = client.post(path)
        assert delivery.status_code == 200
        assert client.post(path).json() == delivery.json()
        assert delivery.json()['status'] == 'delivered'
        output = delivery.json()['output']
        risk = service.endswith('risk-report')
        validate(output, SCHEMAS['risk_report' if risk else 'trace_report'])
        assert {k: v for k, v in output.items() if k != 'interpretation'} == case['expected']
        if risk:
            assert output['interpretation']['flags'] == [dict(flag=f, zh=RISK_MEANINGS[f][0], en=RISK_MEANINGS[f][1]) for f in output['risk_flags']]


def evaluate(events):
    return evaluate_interaction_trace([InteractionEvent.model_validate(e) for e in events])


def test_arrival_order_does_not_change_metrics_with_distinct_timestamps():
    events = CASES['success_self_reported']['events']
    a, b = evaluate(events), evaluate(list(reversed(events)))
    # evidence_ids intentionally retains submitted order under the frozen V1 contract.
    assert a.model_dump(exclude={'evidence_ids'}) == b.model_dump(exclude={'evidence_ids'})


def test_acceptance_duplicate_event_must_not_raise_score():
    events = CASES['partial_schema']['events']
    valid = next(e for e in events if e['schema_valid'])
    assert evaluate(events + [valid]).execution_score <= evaluate(events).execution_score


@pytest.mark.parametrize('service', ['a2a-interaction-trace', 'a2a-interaction-risk-report'])
def test_actual_accepted_price_does_not_change_report(service):
    outputs = []
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        for amount in [5, 6]:
            q = client.post('/v1/quotes', json=dict(buyer_id='price-check', service_id=service, budget=amount))
            assert q.status_code == 200
            assert q.json()['ask_price'] == amount
            order = client.post('/v1/orders', json=dict(quote_id=q.json()['quote_id'], buyer_id='price-check', service_id=service, amount=amount, idempotency_key=f'price-check-{amount}', input={'events': CASES['success_self_reported']['events']}))
            assert order.status_code == 200
            delivery = client.post('/v1/orders/' + order.json()['trade_id'] + '/deliver')
            assert delivery.status_code == 200
            outputs.append(delivery.json()['output'])
    assert outputs[0] == outputs[1]
    assert outputs[0]['execution_score'] == 98
    assert outputs[0]['credit_settlement'] == 'not_evaluated'
