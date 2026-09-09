import copy
import jsonschema
import pytest
from fastapi.testclient import TestClient

from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings
from sharedos_commerce_agent.ledger import Ledger
from sharedos_commerce_agent.sales import TransactionInput, answer, introduction, templates
from sharedos_commerce_agent.seller import SellerService


def payload():
    return {"events": [
        {"transaction_id":"local-demo-tx", "subject_agent_id":"demo-seller", "stage":stage,
         "occurred_at":f"2026-09-10T00:00:0{i}Z", "amount":10,
         "evidence_id":f"demo-evidence-{i}", "provenance":"self_reported"}
        for i,stage in enumerate(["quoted","accepted","paid","delivered","acknowledged"])
    ]}


def order(client, data=None, buyer="demo-buyer"):
    quote=client.post('/v1/quotes',json={"buyer_id":buyer,"service_id":"verified-transaction-trace","budget":30}).json()
    request={"quote_id":quote['quote_id'],"buyer_id":buyer,"service_id":quote['service_id'],
             "amount":quote['ask_price'],"idempotency_key":"local-demo-order-0001","input":data or payload()}
    return request


def test_machine_catalog_matches_runtime_schema():
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        entries=client.get('/v1/catalog').json()
        assert len(entries)==2
        jsonschema.validate(payload(),entries[0]['input_schema'])
        request=order(client)
        receipt=client.post('/v1/orders',json=request).json()
        delivery=client.post(f"/v1/orders/{receipt['trade_id']}/deliver").json()
        jsonschema.validate(delivery['output'],entries[0]['report_schema'])
        assert all(e['verified'] is False for e in delivery['evidence_provenance'])
        assert entries[0]['pricing']['runtime_policy']['base_price']==12
        assert entries[0]['pricing']['catalog_price_is_binding'] is False


@pytest.mark.parametrize('topic',list(templates()['faq']))
def test_faq_without_model(topic):
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        response=client.post('/v1/sales/respond',json={'topic':topic})
        assert response.status_code==200
        assert response.json()['side_effects'] is False
        assert response.json()['text']==answer(topic)['text']


@pytest.mark.parametrize('kind',['extra_event','extra_payload','mixed','duplicate','timezone','empty'])
def test_rejected_input_never_creates_local_paid_record(kind):
    seller=SellerService(Ledger(':memory:'))
    data=payload()
    if kind=='extra_event':data['events'][0]['raw_prompt']='PRIVATE_SENTINEL'
    if kind=='extra_payload':data['private_notes']='PRIVATE_SENTINEL'
    if kind=='mixed':data['events'][1]['transaction_id']='different'
    if kind=='duplicate':data['events'][1]['evidence_id']=data['events'][0]['evidence_id']
    if kind=='timezone':data['events'][0]['occurred_at']='2026-09-10T00:00:00'
    if kind=='empty':data['events']=[]
    with pytest.raises(ValueError):
        seller.settle(buyer_id='demo',service_id='verified-transaction-trace',amount=12,
                      idempotency_key='reject-case-key',input_payload=data)
    assert seller.ledger.list()==[]


def test_api_error_does_not_echo_private_input():
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        data=payload();data['events'][0]['raw_prompt']='PRIVATE_SENTINEL'
        response=client.post('/v1/orders',json=order(client,data))
        assert response.status_code==422
        assert 'PRIVATE_SENTINEL' not in response.text


def test_source_claim_is_preserved_never_promoted():
    seller=SellerService(Ledger(':memory:'));data=payload()
    data['events'][0]['provenance']='platform'
    receipt=seller.settle(buyer_id='demo',service_id='verified-transaction-trace',amount=12,
                         idempotency_key='source-claim-case',input_payload=data)
    result=seller.deliver(receipt.trade_id)
    assert result['evidence_provenance'][0]=={'evidence_id':'demo-evidence-0','claimed':'platform','verified':False}


def test_buyer_mismatch_is_not_claimed_as_sharedos_authorization():
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        request=order(client);request['buyer_id']='other-buyer'
        response=client.post('/v1/orders',json=request)
        assert response.status_code==409
        assert response.json()['detail']=='Order does not match quote'


def test_short_intro_and_dashboard():
    assert len(introduction().split())<=45
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        assert client.get('/dashboard/').status_code==200
        assert client.get('/dashboard/fixtures.js').status_code==200


async def test_brain_receives_sales_intro():
    from sharedos_commerce_agent.graph import build_arena_graph
    from sharedos_commerce_agent.harness import MockArenaClient
    state=await build_arena_graph(MockArenaClient()).ainvoke({'agent_id':'agent-commerce-network'})
    assert state['sales_intro']==introduction()
    assert state['compliant'] is True
