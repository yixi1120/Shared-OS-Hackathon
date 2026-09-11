from datetime import timedelta
from itertools import product

import pytest
from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.models import Quote, QuoteRequest, utc_now
from sharedos_commerce_agent.strategy import PricingPolicy

SERVICES = ['a2a-interaction-trace', 'a2a-interaction-risk-report']


def client():
    return TestClient(create_app(Settings(ledger_path=':memory:')))


def quote(c, service=SERVICES[0], budget=100):
    return c.post('/v1/quotes', json=dict(buyer_id='buyer', service_id=service, budget=budget))


def order_body(q, amount=None):
    return dict(quote_id=q['quote_id'],buyer_id='buyer',service_id=q['service_id'],
                amount=q['ask_price'] if amount is None else amount,idempotency_key='pricing-order-001',
                input={'events':[dict(task_id='task',subject_agent_id='subject',stage='task_failed',occurred_at='2026-09-10T00:00:00Z')]})


@pytest.mark.parametrize('service,budget', product(SERVICES, [0,4,5,6,100]))
def test_catalog_budget_and_quote(service,budget):
    c=client()
    assert {s['price'] for s in c.get('/v1/catalog').json()} == {6}
    r=quote(c,service,budget)
    if budget<5:
        assert r.status_code==409
        assert r.json()['detail']=='insufficient_budget'
        return
    assert r.status_code==200
    q=r.json()
    assert (q['ask_price'],q['reservation_price'])==(min(6,budget),5)
    assert q['budget']==budget and q['pricing_policy_version']=='arena-fixed-v1'
    assert c.post('/v1/orders',json=order_body(q)).status_code==200
    assert quote(c,service,budget).json()['ask_price']==q['ask_price']


@pytest.mark.parametrize('first', [True,False])
def test_modifiers_never_reprice(first):
    policy=PricingPolicy()
    for complexity,urgency,reputation in product([.5,1,3],[.5,1,2],[0,.5,1]):
        q=policy.quote(QuoteRequest(buyer_id='b',service_id=SERVICES[0],budget=100,
                                    complexity=complexity,urgency=urgency,buyer_reputation=reputation),first_purchase=first)
        assert (q.ask_price,q.reservation_price)==(6,5)


def test_counter_close_and_new_quote():
    c=client();q=quote(c).json();url=f"/v1/quotes/{q['quote_id']}/negotiate"
    first=c.post(url,json={'buyer_offer':4}).json()
    assert not first['accepted'] and first['counter_price']==5
    second=c.post(url,json={'buyer_offer':4}).json()
    assert not second['accepted'] and second['counter_price'] is None
    assert not c.post(url,json={'buyer_offer':100}).json()['accepted']
    assert c.post('/v1/orders',json=order_body(q)).status_code==409
    assert quote(c).status_code==200


@pytest.mark.parametrize('budget,offer,expected',[(5,100,5),(6,100,6),(6,5,5)])
def test_accept_and_order_binding(budget,offer,expected):
    c=client();q=quote(c,budget=budget).json();url=f"/v1/quotes/{q['quote_id']}/negotiate"
    result=c.post(url,json={'buyer_offer':offer}).json()
    assert result['accepted'] and result['final_price']==expected<=budget
    assert c.post(url,json={'buyer_offer':100}).json()['final_price']==expected
    assert c.post('/v1/orders',json=order_body(q,expected+1)).status_code==409
    assert c.post('/v1/orders',json=order_body(q,expected)).status_code==200


def test_legacy_quote_terms_survive_policy_change():
    old=Quote(buyer_id='buyer',service_id=SERVICES[0],ask_price=13,reservation_price=10,
              pitch='old terms',expires_at=utc_now()+timedelta(minutes=10))
    policy=PricingPolicy()
    assert policy.negotiate(old,100).final_price==13
    assert policy.negotiate(old,10).final_price==10
    assert policy.negotiate(old,8,prior_low_offers=2).counter_price==11
    current=policy.quote(QuoteRequest(buyer_id='b',service_id=SERVICES[0],budget=5),first_purchase=True)
    changed=PricingPolicy(base_price=20,floor_price=15)
    assert changed.negotiate(current,100).final_price==5
    assert changed.negotiate(current,4).counter_price==5


def test_expired_quote_rejects_negotiation_and_order(monkeypatch):
    import sharedos_commerce_agent.strategy as strategy
    monkeypatch.setattr(strategy,'utc_now',lambda:utc_now()-timedelta(minutes=11))
    c=client();q=quote(c).json()
    assert c.post(f"/v1/quotes/{q['quote_id']}/negotiate",json={'buyer_offer':5}).status_code==410
    assert c.post('/v1/orders',json=order_body(q)).status_code==410
