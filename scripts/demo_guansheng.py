"""Reproduce actual local API outcomes. No external network or Arena credits."""
from pathlib import Path
from datetime import datetime, timezone
from time import perf_counter
import copy
import json
import os

os.environ.setdefault('LEDGER_PATH', ':memory:')
from fastapi.testclient import TestClient
from sharedos_commerce_agent.api import create_app
from sharedos_commerce_agent.config import Settings

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/guansheng/local-runtime-results'
OUT.mkdir(parents=True,exist_ok=True)

def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    events=[{'transaction_id':'local-demo-tx','subject_agent_id':'local-demo-seller','stage':stage,
             'occurred_at':f'2026-09-10T00:00:0{i}Z','amount':10,'evidence_id':f'local-evidence-{i}',
             'provenance':'self_reported'} for i,stage in enumerate(['quoted','accepted','paid','delivered','acknowledged'])]
    with TestClient(create_app(Settings(ledger_path=':memory:'))) as client:
        catalog=client.get('/v1/catalog').json();save('catalog.json',catalog)
        save('sales.json',client.get('/v1/sales').json())
        started=perf_counter()
        quote=client.post('/v1/quotes',json={'buyer_id':'local-demo-buyer','service_id':'verified-transaction-trace','budget':30}).json()
        req={'quote_id':quote['quote_id'],'buyer_id':'local-demo-buyer','service_id':quote['service_id'],
             'amount':quote['ask_price'],'idempotency_key':'local-demo-success-001','input':{'events':events}}
        response=client.post('/v1/orders',json=req);response.raise_for_status();receipt=response.json()
        delivery=client.post('/v1/orders/'+receipt['trade_id']+'/deliver');delivery.raise_for_status()
        elapsed=round((perf_counter()-started)*1000,3)
        success=delivery.json()
        save('success.json',{'mode':'local_runtime_demo','request':req,'quote':quote,'receipt':receipt,
             'delivery':success,'local_api_elapsed_ms':elapsed,'network_payment':False,'sharedos_authorization':False})
        bad=copy.deepcopy(req);bad['idempotency_key']='local-demo-failure-001';bad['input']['events']=[]
        failure=client.post('/v1/orders',json=bad)
        save('failure.json',{'mode':'local_runtime_demo','request':bad,'http_status':failure.status_code,'response':failure.json()})
        denied=copy.deepcopy(req);denied['buyer_id']='different-buyer';denied['idempotency_key']='local-demo-mismatch-001'
        mismatch=client.post('/v1/orders',json=denied)
        save('identity-mismatch.json',{'mode':'local_runtime_demo','request':denied,'http_status':mismatch.status_code,'response':mismatch.json(),'notice':'409 quote identity mismatch, not SharedOS authorization.'})
        assert failure.status_code==422 and mismatch.status_code==409
        fixtures={'events':events,'success':{'report':success['output']},
                  'failure':{'status':'failed','error':{'http_status':422,'detail':failure.json()}},
                  'unauthorized':{'status':'rejected','error':{'http_status':409,'detail':mismatch.json(),'notice':'Quote identity guard only; no SharedOS authorization.'}}}
        (ROOT/'src/sharedos_commerce_agent/dashboard/fixtures.js').write_text('const FIXTURES = '+json.dumps(fixtures,ensure_ascii=False)+';',encoding='utf-8')
        save('run-summary.json',{'run_at':datetime.now(timezone.utc).isoformat(),'success_status':200,
            'failure_status':422,'identity_mismatch_status':409,'local_api_elapsed_ms':elapsed,
            'report_score_from_existing_telemetry':success['output']['reliability_score'],
            'source_commit':'ebac64cb6182607f029c00bc17d07a114a041f48','mode':'local_runtime_demo',
            'live_sharednet_test':False,'two_hour_soak_test':False})
        print(json.dumps({'success':200,'failure':422,'identity_mismatch':409,'local_elapsed_ms':elapsed}))

if __name__=='__main__':main()
