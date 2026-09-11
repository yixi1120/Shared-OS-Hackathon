from pathlib import Path
import os, json, uuid, urllib.request, urllib.error
from datetime import datetime, timezone
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'docs/guansheng/verification';OUT.mkdir(exist_ok=True)
BASE=os.environ.get('DASHBOARD_TEST_BASE','http://127.0.0.1:8786').rstrip('/')
TOKEN=os.environ['SELLER_API_TOKEN']
checks=[]
def call(path,body=None,auth=True):
    headers={'Content-Type':'application/json'}
    if auth:headers['Authorization']='Bearer '+TOKEN
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=30) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
def ok(name,condition):
    assert condition,name
    checks.append(name)
def save(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
_,catalog=call('/v1/catalog')
ok('Both runtime catalog prices are 6',len(catalog)==2 and all(x['price']==6 for x in catalog))
_,product=call('/product/catalog.json')
ok('Machine catalog has both services',len(product['services'])==2)
for sku in ['a2a-interaction-trace','a2a-interaction-risk-report']:
    for budget,expected in [(0,None),(4,None),(5,5),(6,6),(100,6)]:
        status,q=call('/v1/quotes',{'buyer_id':'verify-v3','service_id':sku,'budget':budget})
        ok(f'{sku} budget {budget}',status==409 and q['detail']=='insufficient_budget' if expected is None else status==200 and q['ask_price']==expected and q['reservation_price']==5 and q['pricing_policy_version']=='arena-fixed-v1')
    for name,score in [('success',98),('failure',43),('conflict',57.5)]:
        payload=json.loads((ROOT/'dashboard'/f'{name}.json').read_text())
        _,q=call('/v1/quotes',{'buyer_id':'verify-v3','service_id':sku,'budget':6})
        status,order=call('/v1/orders',{'quote_id':q['quote_id'],'buyer_id':'verify-v3','service_id':sku,'amount':q['ask_price'],'idempotency_key':str(uuid.uuid4()),'input':payload})
        ok(f'{sku} {name} order',status==200)
        status,delivery=call('/v1/orders/'+order['trade_id']+'/deliver',{})
        kind='risk' if sku.endswith('report') else 'trace'
        schema=json.loads((ROOT/'docs/guansheng'/f'{kind}_delivery.schema.json').read_text())
        Draft202012Validator(schema).validate(delivery)
        o=delivery['output']
        ok(f'{kind} {name} strict schema score and provenance',status==200 and o['execution_score']==score and o['evidence_weight']==.15 and o['credit_settlement']=='not_evaluated')
        if kind=='risk':ok(f'{name} interpretation flags aligned',[x['flag'] for x in o['interpretation']['flags']]==o['risk_flags'])
        if name=='conflict':
            ok(f'{kind} conflicting terminal fails closed',o['completed'] is False and o['reputation_eligible'] is False and 'conflicting_terminal_task_state' in o['risk_flags'])
        save(f'{name}-{kind}.json',delivery)
status,data=call('/v1/quotes',{'buyer_id':'verify-v3','service_id':'a2a-interaction-trace','budget':6},False)
ok('No credentials rejected',status==401)
save('unauthorized.json',{'http_status':status,'response':data})
_,q=call('/v1/quotes',{'buyer_id':'verify-v3','service_id':'a2a-interaction-trace','budget':6})
status,data=call('/v1/orders',{'quote_id':q['quote_id'],'buyer_id':'verify-v3','service_id':'a2a-interaction-trace','amount':6,'idempotency_key':str(uuid.uuid4()),'input':{'events':[]}})
ok('Invalid empty event input rejected',status==422)
for offer in [4,4]:
    status,d=call('/v1/quotes/'+q['quote_id']+'/negotiate',{'buyer_offer':offer})
ok('Second low offer closes negotiation',status==200 and not d['accepted'] and d.get('counter_price') is None)
payload=json.loads((ROOT/'dashboard/success.json').read_text())
status,data=call('/v1/orders',{'quote_id':q['quote_id'],'buyer_id':'verify-v3','service_id':'a2a-interaction-trace','amount':5,'idempotency_key':str(uuid.uuid4()),'input':payload})
ok('Closed quote cannot order',status==409)
for service in product['services']:
    for key in ['input_schema','output_schema']:
        status,schema=call('/product/'+service[key]);Draft202012Validator.check_schema(schema);ok(service['service_id']+' '+key+' resolves',status==200)
status,rulebook=call('/product/risk_flags.json')
ok('14 known risk flags including conflicting terminal',status==200 and len(rulebook['flags'])==14 and any(x['flag']=='conflicting_terminal_task_state' for x in rulebook['flags']))
payload=json.loads((ROOT/'dashboard/success.json').read_text())
payload['events'][0]['occurred_at']='2026-09-10T00:00:00'
_,q=call('/v1/quotes',{'buyer_id':'verify-v3','service_id':'a2a-interaction-trace','budget':6})
status,data=call('/v1/orders',{'quote_id':q['quote_id'],'buyer_id':'verify-v3','service_id':'a2a-interaction-trace','amount':6,'idempotency_key':str(uuid.uuid4()),'input':payload})
ok('Timezone-free event rejected before order',status==422)
save('api-checks.json',{'checked_at':datetime.now(timezone.utc).isoformat(),'base_url':BASE,'scope':'real local HTTP service; fixture inputs; not Arena settlement','passed':len(checks),'checks':checks})
print(f'{len(checks)} HTTP/contract checks passed')
