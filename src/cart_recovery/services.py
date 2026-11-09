"""Transactional recovery services. Customer locks serialize consent, carts and sends."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from hashlib import sha256

from .common import dt, iso, canonical
from .repository import connect, insert, new_id
from .rules import Consent, Contact, Touch, evaluate, attribute, variant


class Conflict(ValueError): pass


def clock(c): return c.execute('SELECT clock FROM runtime_state WHERE id=1').fetchone()['clock']


def audit(c,actor,action,entity=None,details=None):
    insert(c,'operation_event',actor=actor,action=action,entity_id=entity,details=details or {},occurred_at=clock(c))


def cart_state(c,cart_id,lock=False):
    cart=c.execute('SELECT * FROM cart WHERE cart_id=%s',(cart_id,)).fetchone()
    if not cart: raise LookupError('Cart not found')
    if lock:c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(cart['customer_id'],))
    now=clock(c)
    lines=c.execute('''SELECT DISTINCT ON (cart_line_id) * FROM cart_line_event
        WHERE cart_id=%s AND occurred_at<=%s AND recorded_at<=%s ORDER BY cart_line_id,revision DESC''',(cart_id,now,now)).fetchall()
    events=c.execute('SELECT * FROM cart_event WHERE cart_id=%s AND occurred_at<=%s AND recorded_at<=%s ORDER BY revision',(cart_id,now,now)).fetchall()
    activity=max((e['occurred_at'] for e in events if e['event_type'] in ('created','updated','reopened','checkout_started')),default=cart['created_at'])
    order=c.execute('SELECT * FROM recovery_order WHERE cart_id=%s',(cart_id,)).fetchone()
    return cart,lines,events,activity,order


def cart_event(c,cart,kind,total,at=None):
    rev=c.execute('SELECT COALESCE(max(revision),0)+1 AS n FROM cart_event WHERE cart_id=%s',(cart,)).fetchone()['n']
    eid=new_id(c,'CE-'); now=at or clock(c)
    return insert(c,'cart_event',cart_event_id=eid,cart_id=cart,event_type=kind,revision=rev,total_minor=total,
                  occurred_at=now,recorded_at=now,source_event_key=eid)


def decision(c,cart,kind,result,reasons,refs,dispatch=None):
    return insert(c,'decision_log',decision_id=new_id(c,'DEC-'),cart_id=cart,dispatch_id=dispatch,
        decision_type=kind,result=result,reason_codes=list(reasons),input_refs=refs,policy_version='recovery-v1',correlation_id=dispatch or cart,decided_at=clock(c))


def campaign_event(c,campaign,state,reason):
    now=clock(c)
    insert(c,'campaign_event',campaign_event_id=new_id(c,'CME-'),campaign_id=campaign,state=state,occurred_at=now,recorded_at=now,reason_code=reason)


def job_state(c,job,state,reason,available=None):
    c.execute('UPDATE outbox_job SET state=%s,lease_until=NULL,last_error=%s,available_at=COALESCE(%s,available_at) WHERE job_id=%s',
              (state,None if state=='done' else reason,available,job['job_id']))
    insert(c,'outbox_event',outbox_event_id=new_id(c,'JOBE-'),job_id=job['job_id'],state=state,occurred_at=clock(c),reason_code=reason)


def send_event(c,sid,kind,at=None,reason=None,provider_key=None):
    now=clock(c)
    return insert(c,'send_event',send_event_id=new_id(c,'SE-'),send_id=sid,event_type=kind,
                  occurred_at=at or now,recorded_at=now,provider_event_id=provider_key,reason_code=reason)


def check_dispatch(c,cart_id,channel):
    cart,lines,events,activity,order=cart_state(c,cart_id,True); now=clock(c); cid=cart['customer_id']
    customer=c.execute('SELECT * FROM customer WHERE customer_id=%s',(cid,)).fetchone()
    consent=c.execute('SELECT * FROM consent WHERE customer_id=%s',(cid,)).fetchall()
    contacts=c.execute('''SELECT a.accepted_at,t.channel FROM send_acceptance a JOIN send_attempt s USING(send_id)
        JOIN campaign_message m ON m.dispatch_id=s.dispatch_id JOIN campaign p USING(campaign_id)
        JOIN message_template t USING(template_id) WHERE p.customer_id=%s AND a.accepted_at>%s''',(cid,now-timedelta(days=7))).fetchall()
    block=c.execute('''SELECT * FROM contact_block_event WHERE customer_id=%s AND channel=%s AND effective_at<=%s AND recorded_at<=%s
                       ORDER BY effective_at DESC,block_event_id DESC LIMIT 1''',(cid,channel,now,now)).fetchone()
    blocked=bool(block and block['state']=='blocked') or not customer['email' if channel=='email' else 'phone_token']
    result=evaluate(now=now,last_activity=activity,purchased_at=order['ordered_at'] if order else None,
        quantity=sum(x['quantity'] for x in lines),total_minor=sum(x['quantity']*x['unit_price_minor'] for x in lines),channel=channel,
        timezone=customer['timezone'],consent=[Consent(x['channel'],x['state'],x['effective_at'],x['recorded_at'],x['revision']) for x in consent],
        contacts=[Contact(x['channel'],x['accepted_at']) for x in contacts],blocked=blocked)
    refs={'consent_ids':[x['consent_id'] for x in consent if x['channel']==channel and x['effective_at']<=now and x['recorded_at']<=now],
          'cart_event_ids':[x['cart_event_id'] for x in events], 'last_activity':iso(activity),'contacts':[iso(x['accepted_at']) for x in contacts]}
    return result,refs,cart,lines


def enroll(cart_id,channel='email'):
    with connect() as c:
        check,refs,cart,lines=check_dispatch(c,cart_id,channel)
        existing=c.execute('SELECT campaign_id,episode,created_at FROM campaign WHERE cart_id=%s ORDER BY episode DESC LIMIT 1',(cart_id,)).fetchone()
        activity=dt(refs['last_activity'])
        changed=c.execute("SELECT 1 FROM cart_event WHERE cart_id=%s AND event_type IN ('updated','reopened') AND occurred_at>=%s LIMIT 1",(cart_id,existing['created_at'])).fetchone() if existing else None
        if existing and not changed:return {'campaign_id':existing['campaign_id'],'existing':True}
        episode=existing['episode']+1 if existing else 1
        if not check.eligible:
            decision(c,cart_id,'enrollment','suppressed',check.reasons,refs)
            return {'suppressed':True,'reasons':check.reasons}
        now=clock(c); total=sum(x['quantity']*x['unit_price_minor'] for x in lines)
        events=c.execute("SELECT event_type FROM cart_event WHERE cart_id=%s ORDER BY revision DESC LIMIT 1",(cart_id,)).fetchone()
        if not events or events['event_type']!='abandoned':cart_event(c,cart_id,'abandoned',total)
        decision(c,cart_id,'abandonment','eligible',[],refs)
        cmpid=new_id(c,'CMP-2026-'); dsp=new_id(c,'DSP-2026-'); template=f'MSG-{cart_id}-{episode:02d}'; ab=variant(cart['customer_id'])
        insert(c,'campaign',campaign_id=cmpid,cart_id=cart_id,customer_id=cart['customer_id'],episode=episode,variant=ab,created_at=now,policy_version='recovery-v1')
        insert(c,'message_template',template_id=template,cart_id=cart_id,channel=channel,variant=ab,version=1,
               subject='Your saved cart' if channel=='email' else None,body=f"Your {sum(x['quantity'] for x in lines)} saved items are ready. Cart {cart_id}." if ab=='A' else f"Return to your saved items worth INR {total/100:,.2f}. Cart {cart_id}.",created_at=now)
        insert(c,'campaign_message',dispatch_id=dsp,campaign_id=cmpid,template_id=template,cart_id=cart_id,touch_number=1,due_at=now,idempotency_key=dsp)
        job={'job_id':new_id(c,'JOB-'),'dispatch_id':dsp,'state':'pending','available_at':now,'lease_until':None,'attempt_count':0,'last_error':None}
        insert(c,'outbox_job',**job); job_state(c,job,'pending','ENROLLED');campaign_event(c,cmpid,'scheduled','ELIGIBLE')
        decision(c,cart_id,'enrollment','eligible',[],refs,dsp)
        return {'campaign_id':cmpid,'dispatch_id':dsp,'channel':channel}


def scan(limit=200):
    with connect() as c:
        now=clock(c)
        rows=c.execute('''SELECT c.cart_id FROM cart c WHERE NOT EXISTS(SELECT 1 FROM recovery_order o WHERE o.cart_id=c.cart_id)
            AND NOT EXISTS(SELECT 1 FROM campaign p WHERE p.cart_id=c.cart_id AND p.created_at >=
                (SELECT max(e.occurred_at) FROM cart_event e WHERE e.cart_id=c.cart_id AND e.event_type IN ('created','updated','checkout_started','reopened')))
            AND (SELECT max(e.occurred_at) FROM cart_event e WHERE e.cart_id=c.cart_id AND e.event_type IN ('created','updated','checkout_started','reopened')) BETWEEN %s AND %s
            ORDER BY c.cart_id LIMIT %s''',(now-timedelta(days=14),now-timedelta(hours=1),limit)).fetchall()
    results=[]
    for row in rows:
        first=enroll(row['cart_id'],'email')
        if first.get('suppressed'): first=enroll(row['cart_id'],'sms')
        results.append(first)
    return {'scanned':len(rows),'queued':sum('dispatch_id' in x for x in results),'results':results}


def work_once():
    # Simulator executes inside the customer transaction: acceptance and capacity commit atomically.
    with connect() as c:
        now=clock(c)
        if c.execute('SELECT paused FROM runtime_state WHERE id=1').fetchone()['paused']:return {'paused':True}
        candidate=c.execute('''SELECT j.job_id,p.customer_id FROM outbox_job j JOIN campaign_message m USING(dispatch_id)
            JOIN campaign p USING(campaign_id) WHERE (j.state IN ('pending','retry') AND j.available_at<=%s)
            OR (j.state='leased' AND j.lease_until<=%s) ORDER BY j.available_at,j.job_id LIMIT 1''',(now,now)).fetchone()
        if not candidate:return {'idle':True}
        c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(candidate['customer_id'],))
        job=c.execute('SELECT * FROM outbox_job WHERE job_id=%s FOR UPDATE SKIP LOCKED',(candidate['job_id'],)).fetchone()
        if not job or job['state'] not in ('pending','retry','leased') or job['available_at']>now:return {'contended':True}
        msg=c.execute('''SELECT m.*,t.channel FROM campaign_message m JOIN message_template t USING(template_id) WHERE dispatch_id=%s''',(job['dispatch_id'],)).fetchone()
        if c.execute('SELECT 1 FROM send_acceptance WHERE dispatch_id=%s',(msg['dispatch_id'],)).fetchone():
            job_state(c,job,'done','RECEIPT_RECONCILED');return {'reconciled':True}
        check,refs,cart,lines=check_dispatch(c,msg['cart_id'],msg['channel'])
        retry_only=set(check.reasons)<= {'QUIET_HOURS','CHANNEL_CAP','GLOBAL_CAP'}
        if not check.eligible and retry_only:
            wait=now+timedelta(hours=1)
            job_state(c,job,'retry',','.join(check.reasons),wait)
            decision(c,cart['cart_id'],'dispatch','deferred',check.reasons,refs,msg['dispatch_id'])
            return {'deferred':True,'reasons':check.reasons,'available_at':iso(wait)}
        sid=new_id(c,'SEND-2026-');number=job['attempt_count']+1
        insert(c,'send_attempt',send_id=sid,dispatch_id=msg['dispatch_id'],attempt_number=number,attempted_at=now,policy_version='recovery-v1')
        c.execute('UPDATE outbox_job SET attempt_count=%s WHERE job_id=%s',(number,job['job_id']))
        if not check.eligible:
            send_event(c,sid,'suppressed',reason=','.join(check.reasons));job_state(c,job,'cancelled',','.join(check.reasons))
            campaign_event(c,msg['campaign_id'],'suppressed',','.join(check.reasons));decision(c,cart['cart_id'],'dispatch','suppressed',check.reasons,refs,msg['dispatch_id'])
            return {'suppressed':True,'send_id':sid,'reasons':check.reasons}
        # A persisted scenario operation selects one deterministic transient failure for a real retry.
        transient=c.execute("SELECT 1 FROM operation_event WHERE entity_id=%s AND action='simulate_transient'",(cart['cart_id'],)).fetchone()
        if transient and number==1:
            send_event(c,sid,'failed',reason='SIMULATED_TRANSIENT');job_state(c,job,'retry','SIMULATED_TRANSIENT',now+timedelta(minutes=1))
            return {'retry':True,'send_id':sid}
        insert(c,'send_acceptance',dispatch_id=msg['dispatch_id'],send_id=sid,provider_message_id='sim-'+msg['dispatch_id'],accepted_at=now)
        send_event(c,sid,'submitted',provider_key='sim-submit-'+sid)
        job_state(c,job,'done','ACCEPTED');campaign_event(c,msg['campaign_id'],'completed','ACCEPTED')
        decision(c,cart['cart_id'],'dispatch','eligible',[],refs,msg['dispatch_id'])
        return {'accepted':True,'send_id':sid,'dispatch_id':msg['dispatch_id']}


def cancel_pending(c,customer_id,reason,channel=None,cart_id=None):
    rows=c.execute('''SELECT j.*,m.campaign_id,m.cart_id,t.channel FROM outbox_job j JOIN campaign_message m USING(dispatch_id)
        JOIN campaign p USING(campaign_id) JOIN message_template t USING(template_id)
        WHERE p.customer_id=%s AND j.state IN ('pending','retry','leased') ORDER BY job_id FOR UPDATE OF j''',(customer_id,)).fetchall()
    for job in rows:
        if channel and channel!=job['channel']:continue
        if cart_id and cart_id!=job['cart_id']:continue
        if job['attempt_count']==0:
            sid=new_id(c,'SEND-2026-');insert(c,'send_attempt',send_id=sid,dispatch_id=job['dispatch_id'],attempt_number=1,attempted_at=clock(c),policy_version='recovery-v1')
            send_event(c,sid,'suppressed',reason=reason)
            c.execute('UPDATE outbox_job SET attempt_count=1 WHERE job_id=%s',(job['job_id'],))
        decision(c,job['cart_id'],'dispatch','suppressed',[reason],{'customer_id':customer_id},job['dispatch_id'])
        job_state(c,job,'cancelled',reason);campaign_event(c,job['campaign_id'],'cancelled',reason)
    return len(rows)


def set_consent(customer_id,channel,state,actor='manager'):
    with connect() as c:
        if not c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(customer_id,)).fetchone():raise LookupError('Customer not found')
        rev=c.execute('SELECT COALESCE(max(revision),0)+1 AS n FROM consent WHERE customer_id=%s AND channel=%s',(customer_id,channel)).fetchone()['n'];now=clock(c)
        row=insert(c,'consent',consent_id=new_id(c,'CON-'),customer_id=customer_id,channel=channel,state=state,effective_at=now,recorded_at=now,revision=rev,source='preference_center')
        if state=='withdrawn':cancel_pending(c,customer_id,'NO_CONSENT',channel)
        audit(c,actor,'consent_'+state,customer_id,{'channel':channel})
        return row


def callback(send_id,kind,key):
    with connect() as c:
        existing=c.execute('SELECT * FROM send_event WHERE provider_event_id=%s',(key,)).fetchone()
        if existing:
            if existing['send_id']!=send_id or existing['event_type']!=kind:raise Conflict('Callback key already has a different payload')
            return existing
        receipt=c.execute('''SELECT a.*,m.cart_id,p.customer_id,t.channel FROM send_acceptance a JOIN send_attempt s USING(send_id)
            JOIN campaign_message m ON m.dispatch_id=s.dispatch_id JOIN campaign p USING(campaign_id) JOIN message_template t USING(template_id) WHERE a.send_id=%s''',(send_id,)).fetchone()
        if not receipt:raise LookupError('Accepted send not found')
        c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(receipt['customer_id'],))
        if kind=='opened' and receipt['channel']=='sms':raise Conflict('SMS has no open event')
        if clock(c)<receipt['accepted_at']:raise Conflict('Callback cannot precede acceptance')
        return send_event(c,send_id,kind,provider_key=key)


def pay(cart_id,key):
    with connect() as c:
        cart,lines,events,activity,existing=cart_state(c,cart_id,True)
        if existing:return existing
        total=sum(x['quantity']*x['unit_price_minor'] for x in lines)
        if not total:raise Conflict('Empty cart cannot be purchased')
        now=clock(c); oid=new_id(c,'ORD-2026-')
        row=insert(c,'recovery_order',order_id=oid,cart_id=cart_id,customer_id=cart['customer_id'],ordered_at=now,currency='INR',total_minor=total)
        for l in lines:
            if l['quantity']:insert(c,'order_line',order_line_id=new_id(c,'OL-'),order_id=oid,cart_line_id=l['cart_line_id'],quantity=l['quantity'],unit_price_minor=l['unit_price_minor'])
        insert(c,'order_event',order_event_id=new_id(c,'OE-'),order_id=oid,event_type='paid',amount_minor=total,occurred_at=now,recorded_at=now,source_event_key=key)
        cart_event(c,cart_id,'purchased',total);cancel_pending(c,cart['customer_id'],'PURCHASED',cart_id=cart_id)
        audit(c,'customer','purchase',cart_id,{'order_id':oid})
        return row


def settle():
    with connect() as c:
        now=clock(c)
        orders=c.execute('''SELECT * FROM recovery_order o WHERE ordered_at<=%s AND NOT EXISTS(
            SELECT 1 FROM decision_log d WHERE d.decision_type='attribution' AND d.input_refs->>'order_id'=o.order_id)
            ORDER BY order_id''',(now-timedelta(days=1),)).fetchall()
        count=0
        for order in orders:
            c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(order['customer_id'],))
            if c.execute("SELECT 1 FROM decision_log WHERE decision_type='attribution' AND input_refs->>'order_id'=%s",(order['order_id'],)).fetchone():continue
            rows=c.execute('''SELECT e.*,a.accepted_at FROM send_event e JOIN send_acceptance a USING(send_id)
                JOIN send_attempt s USING(send_id) JOIN campaign_message m ON m.dispatch_id=s.dispatch_id
                WHERE m.cart_id=%s AND e.event_type='clicked' AND e.recorded_at<=%s''',(order['cart_id'],now)).fetchall()
            winner=attribute(customer_id=order['customer_id'],cart_id=order['cart_id'],ordered_at=order['ordered_at'],
                touches=[Touch(e['send_event_id'],e['send_id'],order['customer_id'],order['cart_id'],e['occurred_at'],e['accepted_at']) for e in rows])
            if winner:
                insert(c,'attribution',attribution_id=new_id(c,'ATR-2026-'),order_id=order['order_id'],send_id=winner.send_id,click_event_id=winner.event_id,
                    model='last_click_7d_same_cart_v1',revenue_minor=order['total_minor'],decided_at=now,policy_version='recovery-v1');count+=1
            decision(c,order['cart_id'],'attribution','attributed' if winner else 'organic',[],{'order_id':order['order_id']})
        return {'settled':len(orders),'credited':count}


def advance(minutes,actor='manager'):
    with connect() as c:
        c.execute('UPDATE runtime_state SET clock=clock+(%s * interval \'1 minute\') WHERE id=1',(minutes,))
        audit(c,actor,'advance_clock',details={'minutes':minutes})
        return {'clock':clock(c)}


def scenario(kind='recovery',channel='email'):
    with connect() as c:
        now=clock(c)
        run=c.execute('SELECT run_id FROM dataset_run ORDER BY run_id LIMIT 1').fetchone()
        if not run:raise Conflict('Import a dataset first using recovery demo')
        cid=new_id(c,'CUS-');cart=new_id(c,'CART-2026-');base=now-timedelta(minutes=70)
        insert(c,'customer',customer_id=cid,run_id=run['run_id'],email=cid.lower()+'@example.test',phone_token='sms-test-'+cid,timezone='UTC',created_at=base)
        for ch in ('email','sms'):
            insert(c,'consent',consent_id=new_id(c,'CON-'),customer_id=cid,channel=ch,state='granted',effective_at=base,recorded_at=base,revision=1,source='synthetic')
        insert(c,'cart',cart_id=cart,customer_id=cid,currency='INR',created_at=base)
        sid=new_id(c,'SES-2026-');insert(c,'session',session_id=sid,customer_id=cid,device_id=cid+'-mobile',device_type='mobile',started_at=base,ended_at=base+timedelta(minutes=5))
        insert(c,'cart_session',cart_session_id=new_id(c,'CS-'),cart_id=cart,session_id=sid,customer_id=cid,linked_at=base)
        lid=new_id(c,'LINE-');insert(c,'cart_line',cart_line_id=lid,cart_id=cart,sku='SKU-DEMO',created_at=base)
        insert(c,'cart_line_event',line_event_id=new_id(c,'LE-'),cart_line_id=lid,cart_id=cart,revision=1,quantity=2,unit_price_minor=249900,occurred_at=base,recorded_at=base)
        cart_event(c,cart,'created',499800,base)
        if kind=='retry':audit(c,'manager','simulate_transient',cart)
        if kind=='multidevice':
            sid=new_id(c,'SES-2026-');insert(c,'session',session_id=sid,customer_id=cid,device_id=cid+'-desktop',device_type='desktop',started_at=now,ended_at=now)
            insert(c,'cart_session',cart_session_id=new_id(c,'CS-'),cart_id=cart,session_id=sid,customer_id=cid,linked_at=now)
            cart_event(c,cart,'updated',499800)
        audit(c,'manager','create_scenario',cart,{'kind':kind,'channel':channel})
    result=enroll(cart,channel)
    if kind=='withdrawal':set_consent(cid,channel,'withdrawn')
    return {'cart_id':cart,'customer_id':cid,'kind':kind,**result}


def update_quantity(cart_id,line_id,quantity):
    with connect() as c:
        cart,lines,events,activity,order=cart_state(c,cart_id,True)
        if order:raise Conflict('Purchased cart is closed')
        old=next((x for x in lines if x['cart_line_id']==line_id),None)
        if not old:raise LookupError('Cart line not found')
        now=clock(c)
        latest=max((e['occurred_at'] for e in events),default=now)
        if now<=latest:
            now=c.execute("UPDATE runtime_state SET clock=GREATEST(clock,%s) WHERE id=1 RETURNING clock",(latest+timedelta(microseconds=1),)).fetchone()['clock']
        insert(c,'cart_line_event',line_event_id=new_id(c,'LE-'),cart_line_id=line_id,cart_id=cart_id,
            revision=old['revision']+1,quantity=quantity,unit_price_minor=old['unit_price_minor'],occurred_at=now,recorded_at=now)
        total=sum((quantity if x['cart_line_id']==line_id else x['quantity'])*x['unit_price_minor'] for x in lines)
        if any(e['event_type']=='abandoned' for e in events):cart_event(c,cart_id,'reopened',total)
        cart_event(c,cart_id,'updated',total)
        cancel_pending(c,cart['customer_id'],'CART_UPDATED',cart_id=cart_id)
        return {'cart_id':cart_id,'total_minor':total,'quantity':quantity}


def refund(order_id,amount,key):
    with connect() as c:
        order=c.execute('SELECT * FROM recovery_order WHERE order_id=%s',(order_id,)).fetchone()
        if not order:raise LookupError('Order not found')
        c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(order['customer_id'],))
        already=c.execute("SELECT COALESCE(sum(amount_minor),0) AS n FROM order_event WHERE order_id=%s AND event_type='refunded'",(order_id,)).fetchone()['n']
        if amount<=0 or amount+already>order['total_minor']:raise Conflict('Refund must be positive and within remaining paid amount')
        now=clock(c)
        return insert(c,'order_event',order_event_id=new_id(c,'OE-'),order_id=order_id,event_type='refunded',amount_minor=amount,occurred_at=now,recorded_at=now,source_event_key=key)


def cancel_campaign(campaign_id,actor='manager'):
    with connect() as c:
        campaign=c.execute('SELECT * FROM campaign WHERE campaign_id=%s',(campaign_id,)).fetchone()
        if not campaign:raise LookupError('Campaign not found')
        c.execute('SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE',(campaign['customer_id'],))
        count=cancel_pending(c,campaign['customer_id'],'MANAGER_CANCELLED',cart_id=campaign['cart_id'])
        audit(c,actor,'cancel_campaign',campaign_id)
        return {'cancelled_jobs':count}
