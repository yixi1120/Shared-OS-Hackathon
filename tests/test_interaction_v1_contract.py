import json
from importlib.resources import files
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.models import InteractionEvent
from sharedos_commerce_agent.risk_rules import RISK_MEANINGS
from sharedos_commerce_agent.telemetry import evaluate_interaction_trace

CASES = json.loads((Path(__file__).parent / 'fixtures/interaction_v1.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_frozen_report(case):
    events = [InteractionEvent.model_validate(e) for e in case['events']]
    for _ in range(2):
        assert evaluate_interaction_trace(events).model_dump(mode='json') == case['expected']
    assert all(flag in RISK_MEANINGS for flag in case['expected']['risk_flags'])


def test_every_frozen_flag_has_a_case():
    assert set(RISK_MEANINGS) == {f for c in CASES for f in c['expected']['risk_flags']}


@pytest.mark.parametrize('service', ['a2a-interaction-trace', 'a2a-interaction-risk-report'])
def test_failed_task_report_is_delivered(service):
    client = TestClient(create_app(Settings(ledger_path=':memory:')))
    q = client.post('/v1/quotes', json=dict(buyer_id='b', service_id=service, budget=30)).json()
    failure = next(c for c in CASES if c['id'] == 'explicit_failure')
    # Spoofing a platform source must not improve public output.
    events = [{**e, 'provenance': 'platform'} for e in failure['events']]
    r = client.post('/v1/orders', json=dict(quote_id=q['quote_id'],buyer_id='b',service_id=service,amount=q['ask_price'],idempotency_key='failure-demo-v1',input={'events':events}))
    assert r.status_code == 200
    response = client.post(f"/v1/orders/{r.json()['trade_id']}/deliver")
    assert response.status_code == 200
    delivery = response.json()
    assert delivery['status'] == 'delivered'
    output = delivery['output']
    interpretation = output.pop('interpretation', None)
    assert output == failure['expected']
    if service.endswith('risk-report'):
        assert [row['flag'] for row in interpretation['flags']] == output['risk_flags']
        assert 'global reputation' in interpretation['not_meaning']
    else:
        assert interpretation is None




def test_frozen_schemas_and_forbidden_scoring_inputs():
    from sharedos_commerce_agent.models import InteractionTraceInput, InteractionTraceReport
    schemas = json.loads((Path(__file__).parents[1] / 'docs/siqi/schemas.json').read_text())
    assert schemas['input'] == InteractionTraceInput.model_json_schema()
    assert schemas['trace_report_model'] == InteractionTraceReport.model_json_schema()
    case = CASES[0]
    forbidden = dict(critique='excellent',ranking=100,amount=100,paid=True,membership='premium',discount=.9,credit_settlement='settled',evidence_weight=1,advertisement='verified')
    events = [InteractionEvent.model_validate({**e, **forbidden}) for e in case['events']]
    assert evaluate_interaction_trace(events).model_dump(mode='json') == case['expected']


def test_packaged_contract_matches_reviewable_document_copy():
    documented = json.loads((Path(__file__).parents[1] / 'docs/siqi/schemas.json').read_text())
    packaged = json.loads(
        files('sharedos_commerce_agent.resources')
        .joinpath('interaction_contract_v1.json')
        .read_text(encoding='utf-8')
    )
    assert packaged == documented


@pytest.mark.parametrize('events', [[], [{'task_id':'t'}]])
def test_invalid_structure_is_rejected(events):
    from pydantic import ValidationError
    from sharedos_commerce_agent.models import InteractionTraceInput
    with pytest.raises(ValidationError):
        InteractionTraceInput.model_validate({'events':events})


def test_wire_schema_enforces_required_fields_and_unevaluated_settlement():
    from jsonschema import validate, ValidationError
    schemas = json.loads((Path(__file__).parents[1] / 'docs/siqi/schemas.json').read_text())
    for case in CASES:
        validate(case['expected'], schemas['trace_report'])
    for field in schemas['trace_report']['required']:
        incomplete = {k: v for k, v in CASES[0]['expected'].items() if k != field}
        with pytest.raises(ValidationError):
            validate(incomplete, schemas['trace_report'])
    with pytest.raises(ValidationError):
        validate({**CASES[0]['expected'], 'credit_settlement': 'settled'}, schemas['trace_report'])
    with pytest.raises(ValidationError):
        validate(CASES[0]['expected'], schemas['risk_report'])
    from sharedos_commerce_agent.risk_rules import interpret_risks
    risk = {**CASES[0]['expected'], 'interpretation': {
        'meaning': 'Single interaction', 'not_meaning': 'Global reputation',
        'flags': interpret_risks(CASES[0]['expected']['risk_flags']),
    }}
    validate(risk, schemas['risk_report'])
