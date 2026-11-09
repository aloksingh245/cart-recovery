import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
import pytest

from cart_recovery.common import ROOT,canonical
from cart_recovery.generator import generate
from cart_recovery.validation import validate,detect
from cart_recovery.exports import write_dataset,read_dataset,challenges,evaluate_findings
from cart_recovery.repository import initialize,import_tables,connect,insert,new_id
from cart_recovery import services as s,queries


def test_generation_reconciliation_export_and_truth_isolation(tmp_path):
    data=generate(); report=validate(data)
    assert report['valid'],report['errors']
    assert (report['row_counts']['cart'],report['ever_abandoned'],report['row_counts']['campaign'],report['row_counts']['send_attempt'])==(1000,400,200,200)
    assert {x['channel'] for x in data['message_template']}=={'email','sms'}
    assert any(e['revision']>1 for e in data['cart_line_event'])
    a=tmp_path/'a';b=tmp_path/'b'
    write_dataset(data,a);write_dataset(generate(),b)
    assert (a/'metadata/checksums.json').read_bytes()==(b/'metadata/checksums.json').read_bytes()
    assert read_dataset(a)==read_dataset(a,'csv')
    assert canonical(read_dataset(a))==canonical(data)
    claims,truth=challenges(data)
    assert all('issue_type' not in claim for claim in claims)
    evaluation=evaluate_findings(detect(data,claims),truth)
    assert evaluation['passed'] and evaluation['tp']==20
    assert all(x['tp']==5 for x in evaluation['classes'].values())


def test_validator_detects_arithmetic_and_foreign_key_damage():
    data=generate();data['cart_event'][0]['total_minor']+=1
    assert not validate(data)['valid']
    data=generate();data['cart'][0]['customer_id']='CUS-999999'
    assert any(e['check']=='FOREIGN_KEY' for e in validate(data)['errors'])


@pytest.fixture
def db(monkeypatch):
    import os
    dsn=os.environ.get('TEST_DATABASE_URL')
    if not dsn:pytest.skip('TEST_DATABASE_URL required for end-to-end PostgreSQL tests')
    schema='recovery_e2e_'+uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('DATABASE_URL',dsn);monkeypatch.setenv('RECOVERY_SCHEMA',schema)
    initialize();import_tables(generate())
    yield
    with psycopg.connect(dsn,autocommit=True) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_recovery_withdrawal_retry_multidevice_and_refund(db):
    a=s.scenario('recovery'); out=s.work_once();assert out.get('accepted'),out
    s.callback(out['send_id'],'delivered','delivery-one')
    s.advance(1);s.callback(out['send_id'],'clicked','click-one')
    assert s.callback(out['send_id'],'clicked','click-one')['provider_event_id']=='click-one'
    s.advance(1);order=s.pay(a['cart_id'],'pay-one')
    assert s.pay(a['cart_id'],'pay-two')['order_id']==order['order_id']
    assert s.settle()['settled']==0
    s.advance(1440); assert s.settle()=={'settled':1,'credited':1}
    assert s.settle()=={'settled':0,'credited':0}
    s.refund(order['order_id'],10000,'refund-one')
    detail=queries.timeline(a['cart_id']);assert detail['attribution']['send_id']==out['send_id']
    metrics=queries.metrics();assert metrics['reconciled'];assert metrics['net_credited_minor']==metrics['gross_credited_minor']-metrics['credited_refunds_minor']
    b=s.scenario('withdrawal'); assert s.work_once().get('idle')
    assert not any(x['accepted_at'] for x in queries.timeline(b['cart_id'])['sends'])
    r=s.scenario('retry'); assert s.work_once().get('retry')
    s.advance(1); assert s.work_once().get('accepted')
    multi=s.scenario('multidevice');assert multi['suppressed'] and 'ACTIVE_CART' in multi['reasons']
    assert len(queries.timeline(multi['cart_id'])['sessions'])==2
    s.advance(60); assert 'dispatch_id' in s.enroll(multi['cart_id'])


def test_api_auth_and_transactional_idempotency(db):
    from cart_recovery.api import app
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            assert (await client.get('/api/metrics')).status_code==401
            assert (await client.post('/api/login',json={'username':'analyst','password':'recovery-demo'})).status_code==200
            headers={'X-Recovery-Request':'1','Idempotency-Key':'scenario-api'}
            assert (await client.post('/api/scenarios',json={},headers=headers)).status_code==403
            await client.post('/api/login',json={'username':'manager','password':'recovery-demo'})
            assert (await client.post('/api/scenarios',json={})).status_code==403
            first=await client.post('/api/scenarios',json={},headers=headers)
            assert first.status_code==200,first.text
            again=await client.post('/api/scenarios',json={},headers=headers)
            assert again.json()==first.json()
            changed=await client.post('/api/scenarios',json={'kind':'withdrawal'},headers=headers)
            assert changed.status_code==409
            result=(await client.get('/api/carts/'+first.json()['cart_id'])).json()
            assert len(result['lines'])==1 and len(result['decisions'])>=2
            bad=await client.post('/api/clock',json={'minutes':-1},headers=headers|{'Idempotency-Key':'bad-clock'})
            assert bad.status_code==422
            cross=await client.post('/api/clock',json={'minutes':1},headers=headers|{'Origin':'https://attacker.test','Idempotency-Key':'cross'})
            assert cross.status_code==403
            m=await client.get('/api/metrics');assert m.status_code==200,m.text
            assert (await client.get('/api/carts')).status_code==200
            assert (await client.get('/api/campaigns')).status_code==200
    asyncio.run(run())


def test_two_workers_cannot_accept_two_customer_carts_inside_cap(db):
    a=s.scenario('recovery');b=s.scenario('recovery')
    # Build another legitimate cart for A's customer rather than a malformed ownership join.
    with connect() as c:
        now=s.clock(c);cart=new_id(c,'CART-2026-');base=now-__import__('datetime').timedelta(minutes=70)
        insert(c,'cart',cart_id=cart,customer_id=a['customer_id'],currency='INR',created_at=base)
        lid=new_id(c,'LINE-');insert(c,'cart_line',cart_line_id=lid,cart_id=cart,sku='SKU-CAP',created_at=base)
        insert(c,'cart_line_event',line_event_id=new_id(c,'LE-'),cart_line_id=lid,cart_id=cart,revision=1,quantity=1,unit_price_minor=10000,occurred_at=base,recorded_at=base)
        s.cart_event(c,cart,'created',10000,base)
    s.enroll(cart)
    def work(_):
        return [s.work_once() for _ in range(4)]
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(work,range(2)))
    with connect() as c:
        row=c.execute('''SELECT count(*) AS n FROM send_acceptance a JOIN send_attempt s USING(send_id)
            JOIN campaign_message m ON m.dispatch_id=s.dispatch_id JOIN campaign p USING(campaign_id) WHERE p.customer_id=%s''',(a['customer_id'],)).fetchone()
        assert row['n']==1
    assert 'CHANNEL_CAP' in str(queries.timeline(cart)['decisions'])


def test_cart_update_reopens_episode_and_late_purchase_has_no_credit(db):
    first=s.scenario('recovery'); detail=queries.timeline(first['cart_id'])
    s.update_quantity(first['cart_id'],detail['lines'][0]['cart_line_id'],3)
    s.advance(60); second=s.enroll(first['cart_id'])
    assert second['campaign_id']!=first['campaign_id']
    accepted=s.work_once();assert accepted.get('accepted'),accepted
    s.advance(1);s.callback(accepted['send_id'],'clicked','late-click')
    s.advance(8*1440);order=s.pay(first['cart_id'],'late-pay')
    s.advance(1440);assert s.settle()['credited']==0
    assert queries.timeline(first['cart_id'])['attribution'] is None
    m=queries.metrics();assert m['late_orders']>=1 and m['reconciled']


def test_same_clock_quantity_update_preserves_historical_totals(db):
    from cart_recovery.repository import dump_tables
    a=s.scenario('recovery');before=queries.timeline(a['cart_id'])
    s.update_quantity(a['cart_id'],before['lines'][0]['cart_line_id'],4)
    report=validate(dump_tables(),check_profile=False)
    assert report['valid'],report['errors']
    after=queries.timeline(a['cart_id'])
    assert after['lines'][0]['occurred_at']>before['events'][-1]['occurred_at']
