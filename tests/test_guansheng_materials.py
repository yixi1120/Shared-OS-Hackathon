"""Contract drift checks for additive product materials, without changing Runtime."""
import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from sharedos_commerce_agent.risk_rules import RISK_MEANINGS
from sharedos_commerce_agent.seller import interaction_contract

ROOT = Path(__file__).parents[1]
ASSETS = ROOT / 'docs/guansheng'


def load(name):
    return json.loads((ASSETS / name).read_text(encoding='utf-8'))


def strip_annotations(value):
    if isinstance(value, dict):
        return {k: strip_annotations(v) for k, v in value.items() if k != 'x-known-risk-flags'}
    if isinstance(value, list):
        return [strip_annotations(v) for v in value]
    return value


def test_risk_meanings_and_catalog_match_current_contract():
    rules = load('risk_flags.json')
    assert rules['flag_count'] == len(rules['flags']) == len(RISK_MEANINGS) == 14
    assert rules['flags'] == [dict(flag=k, zh=v[0], en=v[1]) for k, v in RISK_MEANINGS.items()]
    catalog = load('catalog.json')
    assert catalog['known_risk_flag_count'] == 14
    assert catalog['conflicting_terminal_policy']['completed'] is False
    for service in catalog['services']:
        assert (service['regular_price_credits'], service['first_purchase_price_credits'], service['reservation_price_credits']) == (6, 6, 5)


def test_published_schemas_preserve_runtime_validation():
    assert strip_annotations(load('schemas.json')) == interaction_contract()
    for kind in ['trace', 'risk']:
        schema = load(kind + '_report.schema.json')
        assert schema['properties']['risk_flags']['x-known-risk-flags'] == list(RISK_MEANINGS)
        assert strip_annotations(schema) == interaction_contract()[kind + '_report']
        Draft202012Validator.check_schema(load(kind + '_delivery.schema.json'))


def test_conflict_example_matches_main_and_allows_future_flags():
    cases = json.loads((ROOT / 'tests/fixtures/interaction_v1.json').read_text())
    case = next(c for c in cases if c['id'] == 'conflicting_terminals')
    events = json.loads((ROOT / 'dashboard/conflict.json').read_text())['events']
    assert events == [{k: v for k, v in e.items() if k != 'provenance'} for e in case['events']]
    report = copy.deepcopy(case['expected'])
    report['risk_flags'].append('future_diagnostic')
    report['interpretation'] = dict(meaning='Single task only', not_meaning='Not global trust', flags=[dict(flag=f, zh='说明', en='Meaning') for f in report['risk_flags']])
    Draft202012Validator(load('risk_delivery.schema.json')).validate(dict(trade_id='contract-test', status='delivered', output=report))


def test_production_identifiers_remain_unconfirmed():
    submission = load('submission.json')
    for key in ['sharednet_node_id', 'purpose_string', 'service_base_url', 'product_agent_addresses', 'confirmed_by', 'confirmed_at']:
        assert submission[key] is None


def test_confirmed_discord_and_pending_environment_fields():
    s = load('submission.json')
    assert s['discord_username'] == 'yixi1120_19547'
    assert s['discord_submission_channel_path'] == 'AICOO → SHAREDOS HACKATHON → #submission'
    for key in ['sharednet_seat_id', 'sharedos_principal_id', 'sharedos_agent_address', 'service_base_url', 'discord_submission_message_url', 'submitted_at']:
        assert s[key] is None


def test_sales_answers_cover_final_buyer_topics():
    from sharedos_commerce_agent.sales import SalesPolicy
    policy = SalesPolicy()
    for question, intent in [('价格', 'price'), ('隐私', 'privacy'), ('冷启动', 'cold_start'), ('证据来源', 'provenance'), ('刷分', 'gaming'), ('有什么用', 'value'), ('为什么同价', 'risk_difference'), ('服务失败或没有 Artifact', 'failure'), ('哪些免费', 'free_auth')]:
        assert policy.respond(question).intent == intent
    assert len(policy.introduction.split()) <= 50


def test_catalog_marks_free_and_paid_boundaries():
    catalog = load('catalog.json')
    assert {item['endpoint'] for item in catalog['free_capabilities']} >= {
        'GET /health',
        'GET /v1/catalog',
        'GET /v1/contracts/interaction-v1',
    }
    assert all(service['access_tier'] == 'paid' for service in catalog['services'])
    assert 'are free' in load('pitch.json')['access_boundary']
    assert any(a['id'] == 'free_auth' for a in load('faq.json')['answers'])
