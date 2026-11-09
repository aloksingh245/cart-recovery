"""Deterministic, dependency-ordered synthetic facts. Labels are derived afterward."""
from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
import random

from .common import TABLES, canonical, dt, iso, load_config
from .rules import Consent, Contact, Policy, Touch, attribute, evaluate, variant

PREFIX = {'consent':'CON-', 'session':'SES-2026-', 'cart_session':'CS-', 'cart_line':'LINE-',
          'cart_line_event':'LE-', 'cart_event':'CE-', 'campaign':'CMP-2026-',
          'campaign_event':'CME-', 'campaign_message':'DSP-2026-', 'send_attempt':'SEND-2026-',
          'send_event':'SE-', 'recovery_order':'ORD-2026-', 'order_line':'OL-', 'order_event':'OE-',
          'attribution':'ATR-2026-', 'decision_log':'DEC-', 'outbox_job':'JOB-', 'outbox_event':'JOBE-'}


class Dataset:
    def __init__(self):
        self.tables = {t['name']: [] for t in TABLES}
        self.counters = defaultdict(int)

    def add(self, table, **values):
        self.tables[table].append(values)
        return values

    def id(self, table):
        self.counters[table] += 1
        return PREFIX[table] + f'{self.counters[table]:06d}'


def generate(profile='starter', seed=20261022, scale=1.0):
    cfg = load_config('generation')
    counts = {k: int(v * scale) for k, v in cfg['profiles'][profile].items()}
    if counts['campaigns'] < 100 or min(counts.values()) < 10 or counts['campaigns'] > counts['customers'] or counts['abandoned_carts'] != counts['campaigns'] * 2:
        raise ValueError('Scale must retain at least 100 campaigns for complete anomaly coverage; abandoned must be twice campaigns <= customers')
    p = Policy(**load_config('policy'))
    rng = random.Random(seed)
    data = Dataset()
    add, newid = data.add, data.id
    start, cutoff = dt(cfg['start_at']), dt(cfg['observation_cutoff'])
    config_hash = sha256(canonical({'config':cfg, 'policy':load_config('policy'), 'profile':profile, 'seed':seed, 'scale':scale}).encode()).hexdigest()
    run = f'RUN-20261022-{config_hash[:12]}'
    add('dataset_run', run_id=run, seed=seed, profile=profile if scale==1 else 'custom', start_at=iso(start), cutoff_at=iso(cutoff), policy_version=p.version, config_sha256=config_hash)
    n = counts['campaigns']
    histories, contacts = defaultdict(list), defaultdict(list)
    consent_ids=defaultdict(list)
    for i in range(1, counts['customers'] + 1):
        cid = f'CUS-{i:06d}'
        add('customer', customer_id=cid, run_id=run, email=f'customer{i:06d}@example.test',
            phone_token=f'sms-test-{i:06d}', timezone='Asia/Kolkata', created_at=iso(start))
        channel = 'sms' if i % 5 == 0 else 'email'
        for ch in ('email', 'sms'):
            state = 'granted' if ch == channel else 'withdrawn'
            consent_id=newid('consent');consent_ids[cid].append(consent_id)
            add('consent', consent_id=consent_id, customer_id=cid, channel=ch, state=state,
                effective_at=iso(start), recorded_at=iso(start), revision=1, source='synthetic')
            histories[cid].append(Consent(ch, state, start, start, 1))

    def ce(cart, kind, when, total):
        rev = cart_revs[cart] + 1
        cart_revs[cart] = rev
        eid = newid('cart_event')
        return add('cart_event', cart_event_id=eid, cart_id=cart, event_type=kind, revision=rev,
                   total_minor=total, occurred_at=iso(when), recorded_at=iso(when), source_event_key=eid)

    def decision(cart, kind, result, reasons, when, refs, dispatch=None):
        return add('decision_log', decision_id=newid('decision_log'), cart_id=cart, dispatch_id=dispatch,
                   decision_type=kind, result=result, reason_codes=list(reasons), input_refs=refs,
                   policy_version=p.version, correlation_id=run, decided_at=iso(when))

    cart_revs = defaultdict(int)
    all_lines = {}
    touches = defaultdict(list)
    for i in range(1, counts['carts'] + 1):
        cart = f'CART-2026-{i:06d}'
        abandoned = i <= counts['abandoned_carts']
        # Two abandoned carts share a customer's cap; all campaign instances are unique customers.
        owner_num = ((i - 1) % n + 1) if abandoned else ((i - 1) % counts['customers'] + 1)
        cid = f'CUS-{owner_num:06d}'
        base = start + timedelta(days=1 + owner_num % 14, hours=9, minutes=owner_num % 40)
        if n < i <= 2*n:
            base += timedelta(minutes=35)
        if not abandoned:
            base = cutoff - timedelta(minutes=20) if i % 4 == 0 else start + timedelta(days=1 + i % 14, hours=9)
        add('cart', cart_id=cart, customer_id=cid, currency='INR', created_at=iso(base))
        for device in range(2 if i % 6 == 0 else 1):
            sid = newid('session')
            add('session', session_id=sid, customer_id=cid, device_id=f'device-{cid}-{device}',
                device_type='mobile' if device == 0 else 'desktop', started_at=iso(base), ended_at=iso(base + timedelta(minutes=10)))
            add('cart_session', cart_session_id=newid('cart_session'), cart_id=cart, session_id=sid, customer_id=cid, linked_at=iso(base))
        lines = []
        line_count = rng.choices([1,2,3,4,5,6,7,8], weights=[28,30,19,11,6,3,2,1])[0]
        for j in range(line_count):
            lid = newid('cart_line')
            price = max(9900, min(1999900, int(rng.lognormvariate(10.8, .85)//100*100)))
            qty = rng.choices([1,2,3,4], weights=[72,20,6,2])[0]
            add('cart_line', cart_line_id=lid, cart_id=cart, sku=f'SKU-{j+1:03d}-{i%53:02d}', created_at=iso(base))
            event = add('cart_line_event', line_event_id=newid('cart_line_event'), cart_line_id=lid, cart_id=cart,
                        revision=1, quantity=qty, unit_price_minor=price, occurred_at=iso(base), recorded_at=iso(base))
            lines.append(event)
        total = sum(l['quantity']*l['unit_price_minor'] for l in lines)
        ce(cart, 'created', base, total)
        activity = base
        if i % 7 == 0:
            activity = base + timedelta(minutes=5)
            old = lines[0]
            updated = old | dict(line_event_id=newid('cart_line_event'), quantity=old['quantity']+1,
                                 revision=2, occurred_at=iso(activity), recorded_at=iso(activity))
            add('cart_line_event', **updated)
            lines[0] = updated
            total = sum(l['quantity']*l['unit_price_minor'] for l in lines)
            ce(cart, 'updated', activity, total)
        all_lines[cart] = lines
        purchase_time = None
        channel = 'sms' if owner_num % 5 == 0 else 'email'
        if abandoned:
            detected = activity + timedelta(minutes=60)
            ce(cart, 'abandoned', detected, total)
            decision(cart, 'abandonment', 'eligible', [], detected, {'last_activity':iso(activity)})
            if i <= n:
                cmpid, dispatch = newid('campaign'), newid('campaign_message')
                template = f'MSG-{cart}-01'
                ab = variant(cid, seed)
                due = detected + timedelta(minutes=5)
                add('campaign', campaign_id=cmpid, cart_id=cart, customer_id=cid, episode=1,
                    variant=ab, created_at=iso(detected), policy_version=p.version)
                body = (f'Your {len(lines)} saved items are waiting.' if ab == 'A' else f'Return to your saved {len(lines)} items, worth INR {total/100:.2f}.')
                add('message_template', template_id=template, cart_id=cart, channel=channel, variant=ab,
                    version=1, subject='Your saved cart' if channel=='email' else None, body=body, created_at=iso(detected))
                add('campaign_message', dispatch_id=dispatch, campaign_id=cmpid, template_id=template,
                    cart_id=cart, touch_number=1, due_at=iso(due), idempotency_key=dispatch)
                job = newid('outbox_job')
                add('campaign_event', campaign_event_id=newid('campaign_event'), campaign_id=cmpid,
                    state='scheduled', occurred_at=iso(detected), recorded_at=iso(detected), reason_code='ELIGIBLE')
                decision(cart, 'enrollment', 'eligible', [], detected, {'last_activity':iso(activity)}, dispatch)
                if i % 17 == 0:
                    at = due-timedelta(minutes=2)
                    consent_id=newid('consent');consent_ids[cid].append(consent_id)
                    add('consent', consent_id=consent_id, customer_id=cid, channel=channel, state='withdrawn',
                        effective_at=iso(at), recorded_at=iso(at), revision=2, source='preference_center')
                    histories[cid].append(Consent(channel, 'withdrawn', at, at, 2))
                outcome = evaluate(now=due, last_activity=activity, purchased_at=None, quantity=sum(l['quantity'] for l in lines),
                                   total_minor=total, channel=channel, timezone='Asia/Kolkata', consent=histories[cid], contacts=contacts[cid], policy=p)
                sid = newid('send_attempt')
                add('send_attempt', send_id=sid, dispatch_id=dispatch, attempt_number=1, attempted_at=iso(due), policy_version=p.version)
                accepted = outcome.eligible and i % 29 != 0
                state = 'done' if accepted else 'cancelled' if not outcome.eligible else 'dead'
                add('outbox_job', job_id=job, dispatch_id=dispatch, state=state, available_at=iso(due), lease_until=None,
                    attempt_count=1, last_error=None if accepted else ','.join(outcome.reasons) or 'SIMULATED_FAILURE')
                for js, when in [('pending',detected), (state,due)]:
                    add('outbox_event', outbox_event_id=newid('outbox_event'), job_id=job, state=js, occurred_at=iso(when), reason_code='GENERATED_REPLAY')
                decision(cart, 'dispatch', 'eligible' if outcome.eligible else 'suppressed', outcome.reasons, due,
                         {'consent_ids':consent_ids[cid],
                          'last_activity':iso(activity)}, dispatch)
                def se(kind, when, reason=None):
                    eid = newid('send_event')
                    return add('send_event', send_event_id=eid, send_id=sid, event_type=kind, occurred_at=iso(when),
                               recorded_at=iso(when), provider_event_id=f'sim-{eid}' if accepted else None, reason_code=reason)
                if accepted:
                    add('send_acceptance', dispatch_id=dispatch, send_id=sid, provider_message_id=f'sim-{dispatch}', accepted_at=iso(due))
                    contacts[cid].append(Contact(channel,due))
                    se('submitted',due)
                    if i % 23 != 0:
                        se('delivered',due+timedelta(seconds=20))
                        if channel=='email' and rng.random()<.48:
                            se('opened',due+timedelta(minutes=3))
                        if i % 3 == 0 or i % 19 == 0:
                            clicktime=due+timedelta(minutes=10)
                            click = se('clicked',clicktime)
                            touches[cart].append(Touch(click['send_event_id'],sid,cid,cart,clicktime,due))
                            purchase_time=clicktime+timedelta(days=8 if i%19==0 else 0,hours=2)
                else:
                    se('suppressed' if not outcome.eligible else 'failed',due, ','.join(outcome.reasons) or 'SIMULATED_FAILURE')
                add('campaign_event', campaign_event_id=newid('campaign_event'), campaign_id=cmpid, state='completed' if accepted else 'suppressed',
                    occurred_at=iso(due), recorded_at=iso(due), reason_code='ACCEPTED' if accepted else 'DISPATCH_STOPPED')
            else:
                check = evaluate(now=detected,last_activity=activity,purchased_at=None,quantity=sum(l['quantity'] for l in lines),
                                 total_minor=total,channel=channel,timezone='Asia/Kolkata',consent=histories[cid],contacts=contacts[cid],policy=p)
                # No permission on the alternate channel covers primary delivery failures without forced enrollment.
                if check.eligible:
                    channel = 'sms' if channel=='email' else 'email'
                    check = evaluate(now=detected,last_activity=activity,purchased_at=None,quantity=1,total_minor=total,
                                     channel=channel,timezone='Asia/Kolkata',consent=histories[cid],contacts=contacts[cid],policy=p)
                decision(cart,'enrollment','suppressed',check.reasons,detected,{'channel':channel,'last_activity':iso(activity)})
                if i % 5 == 0:
                    purchase_time=detected+timedelta(hours=3)
        elif i % 4 != 0:
            purchase_time=activity+timedelta(minutes=20)
        if purchase_time and purchase_time < cutoff:
            oid=newid('recovery_order')
            add('recovery_order',order_id=oid,cart_id=cart,customer_id=cid,ordered_at=iso(purchase_time),currency='INR',total_minor=total)
            for line in lines:
                add('order_line',order_line_id=newid('order_line'),order_id=oid,cart_line_id=line['cart_line_id'],quantity=line['quantity'],unit_price_minor=line['unit_price_minor'])
            eid=newid('order_event')
            add('order_event',order_event_id=eid,order_id=oid,event_type='paid',amount_minor=total,occurred_at=iso(purchase_time),recorded_at=iso(purchase_time),source_event_key=eid)
            ce(cart,'purchased',purchase_time,total)
            winner=attribute(customer_id=cid,cart_id=cart,ordered_at=purchase_time,touches=touches[cart],policy=p)
            if winner:
                add('attribution',attribution_id=newid('attribution'),order_id=oid,send_id=winner.send_id,click_event_id=winner.event_id,
                    model='last_click_7d_same_cart_v1',revenue_minor=total,decided_at=iso(purchase_time+timedelta(days=1)),policy_version=p.version)
            decision(cart,'attribution','attributed' if winner else 'organic',[],purchase_time+timedelta(days=1),{'order_id':oid})
            if i%31==0:
                eid=newid('order_event')
                add('order_event',order_event_id=eid,order_id=oid,event_type='refunded',amount_minor=total//2,
                    occurred_at=iso(purchase_time+timedelta(days=1)),recorded_at=iso(purchase_time+timedelta(days=1)),source_event_key=eid)
    return data.tables
