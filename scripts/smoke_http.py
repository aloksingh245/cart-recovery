"""Exercise a freshly running application's actual authenticated HTTP workflow."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
import httpx

p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8080');p.add_argument('--out',default='artifacts/http-smoke.json');a=p.parse_args()
with httpx.Client(base_url=a.url,timeout=30) as c:
    assert c.get('/readyz').status_code==200
    assert c.post('/api/login',json={'username':'manager','password':'recovery-demo'}).status_code==200
    def post(path,payload=None):
        r=c.post('/api'+path,json=payload or {},headers={'X-Recovery-Request':'1','Idempotency-Key':uuid4().hex})
        assert r.status_code==200,(path,r.status_code,r.text)
        return r.json()
    baseline=c.get('/api/metrics').json()
    scenario=post('/scenarios',{'kind':'recovery','channel':'email'});cart=scenario['cart_id']
    result=post('/worker'); accepted=[x for x in result['results'] if x.get('accepted')]
    assert accepted,result
    detail=c.get('/api/carts/'+cart).json();sid=next(s['send_id'] for s in detail['sends'] if s['accepted_at'])
    post('/sends/'+sid+'/events',{'kind':'delivered'});post('/clock',{'minutes':1});post('/sends/'+sid+'/events',{'kind':'clicked'})
    post('/clock',{'minutes':1});order=post('/carts/'+cart+'/purchase');post('/clock',{'minutes':1440});post('/settle')
    detail=c.get('/api/carts/'+cart).json();assert detail['attribution']['send_id']==sid,detail
    stopped=post('/scenarios',{'kind':'withdrawal','channel':'sms'})
    post('/worker');blocked=c.get('/api/carts/'+stopped['cart_id']).json();assert not any(s['accepted_at'] for s in blocked['sends'])
    assert any('NO_CONSENT' in d['reason_codes'] for d in blocked['decisions'])
    final=c.get('/api/metrics').json();assert final['reconciled'] and final['credited_orders']==baseline['credited_orders']+1
    result={'passed':True,'cart_id':cart,'order_id':order['order_id'],'winning_send':sid,'suppressed_cart':stopped['cart_id'],'reconciled':True}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(result)
