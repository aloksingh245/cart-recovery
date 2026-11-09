"""Input-only structural/business validator and claim detector. Never reads truth."""
from collections import defaultdict
from zoneinfo import ZoneInfo

from .common import TABLES, dt, load_config
from .rules import Consent, Contact, Policy, evaluate


def index(tables, name, key=None):
    key = key or next(f['name'] for t in TABLES if t['name']==name for f in t['fields'] if f['pk'])
    return {r[key]:r for r in tables[name]}


def grouped(rows, key):
    out=defaultdict(list)
    for r in rows: out[r[key]].append(r)
    return out


def line_state(tables):
    return grouped(tables['cart_line_event'],'cart_id')


def snapshot(events, at):
    latest={}
    for e in events:
        if dt(e['occurred_at']) <= at and dt(e['recorded_at']) <= at:
            prev=latest.get(e['cart_line_id'])
            if prev is None or e['revision'] > prev['revision']: latest[e['cart_line_id']]=e
    return list(latest.values())


def validate(tables, check_profile=True):
    errors=[]
    def fail(check, record, detail):
        if len(errors)<100: errors.append({'check':check,'record_id':record,'detail':detail})
    indexes={}
    import re
    for t in TABLES:
        name=t['name']; pk=next(f['name'] for f in t['fields'] if f['pk'])
        indexes[name]={r.get(pk):r for r in tables.get(name,[])}
        if len(indexes[name]) != len(tables.get(name,[])): fail('PK_UNIQUENESS',name,'duplicate primary key')
        for f in t['fields']:
            vals=set()
            for r in tables.get(name,[]):
                v=r.get(f['name']); rid=r.get(pk)
                if f['required'] and v is None: fail('REQUIRED',rid,f['name'])
                if v is None: continue
                if f['unique']:
                    if str(v) in vals: fail('UNIQUE',rid,f['name'])
                    vals.add(str(v))
                if f['allowed'] and v not in f['allowed']: fail('ENUM',rid,f['name'])
                if f['type']=='text' and (not isinstance(v,str) or not v.strip()): fail('TEXT',rid,f['name'])
                if f['type']=='bigint' and (type(v) is not int or v<0): fail('RANGE',rid,f['name'])
                if f['type']=='timestamptz':
                    try:
                        if dt(v).utcoffset() is None: raise ValueError()
                    except (ValueError,TypeError): fail('TIMESTAMP',rid,f['name'])
                if f['check'] and ' ~ ' in f['check']:
                    pattern=f['check'].split("'")[1]
                    if not re.fullmatch(pattern,v): fail('ID_FORMAT',rid,f['name'])
    for t in TABLES:
        pk=next(f['name'] for f in t['fields'] if f['pk'])
        for f in t['fields']:
            if not f['fk']: continue
            parent,col=f['fk'].split('.')
            parent_values={r[col] for r in tables[parent]}
            for r in tables[t['name']]:
                if r[f['name']] is not None and r[f['name']] not in parent_values: fail('FOREIGN_KEY',r[pk],f['fk'])
    for t in TABLES:
        pk=next(f['name'] for f in t['fields'] if f['pk'])
        for constraint in t['constraints']:
            unique=re.fullmatch(r'UNIQUE \(([^)]+)\)',constraint)
            foreign=re.fullmatch(r'FOREIGN KEY \(([^)]+)\) REFERENCES (\w+)\(([^)]+)\)',constraint)
            if unique:
                cols=[x.strip() for x in unique[1].split(',')];seen_keys=set()
                for row in tables[t['name']]:
                    key=tuple(row.get(col) for col in cols)
                    if key in seen_keys:fail('COMPOUND_UNIQUE',row[pk],constraint)
                    seen_keys.add(key)
            if foreign:
                cols=[x.strip() for x in foreign[1].split(',')];parent_cols=[x.strip() for x in foreign[3].split(',')]
                parents={tuple(row.get(col) for col in parent_cols) for row in tables[foreign[2]]}
                for row in tables[t['name']]:
                    if tuple(row.get(col) for col in cols) not in parents:fail('COMPOUND_FOREIGN_KEY',row[pk],constraint)
        for row in tables[t['name']]:
            if 'occurred_at' in row and 'recorded_at' in row and dt(row['occurred_at'])>dt(row['recorded_at']):fail('DATE_ORDER',row[pk],'recorded before occurrence')
    if errors: return {'valid':False,'errors':errors,'row_counts':{k:len(v) for k,v in tables.items()}}
    customers=indexes['customer']; carts=indexes['cart']; lines=indexes['cart_line']; orders=indexes['recovery_order']
    cart_events=grouped(tables['cart_event'],'cart_id'); line_events=line_state(tables)
    for c in customers.values():
        try: ZoneInfo(c['timezone'])
        except Exception: fail('TIMEZONE',c['customer_id'],c['timezone'])
    for s in tables['session']:
        if dt(s['ended_at'])<dt(s['started_at']): fail('DATE_ORDER',s['session_id'],'session end before start')
    for link in tables['cart_session']:
        if carts[link['cart_id']]['customer_id'] != indexes['session'][link['session_id']]['customer_id']: fail('OWNERSHIP',link['cart_session_id'],'cross customer session')
    for line,events in grouped(tables['cart_line_event'],'cart_line_id').items():
        previous=0;at=None
        for event in sorted(events,key=lambda x:x['revision']):
            if event['revision']!=previous+1 or (at and dt(event['occurred_at'])<at):fail('LINE_REVISION',event['line_event_id'],'invalid line revision/time order')
            previous=event['revision'];at=dt(event['occurred_at'])
    for cart,events in cart_events.items():
        paid=None; abandoned=False; previous=0
        for e in sorted(events,key=lambda e:e['revision']):
            at=dt(e['occurred_at'])
            if e['revision']!=previous+1: fail('REVISION',e['cart_event_id'],'noncontiguous cart revision')
            previous=e['revision']
            total=sum(x['quantity']*x['unit_price_minor'] for x in snapshot(line_events[cart],at))
            if total!=e['total_minor']: fail('ARITHMETIC',e['cart_event_id'],'cart total does not match line history')
            if paid:fail('CART_LIFECYCLE',e['cart_event_id'],'purchased cart is terminal')
            if e['event_type']=='purchased': paid=at
            if e['event_type']=='abandoned':
                activity=max(dt(x['occurred_at']) for x in events if x['event_type'] in ('created','updated','checkout_started','reopened') and dt(x['occurred_at'])<=at)
                if paid or (at-activity).total_seconds()<3600 or abandoned: fail('ABANDONMENT',e['cart_event_id'],'invalid abandonment episode')
                abandoned=True
            if e['event_type']=='reopened': abandoned=False
    ol=grouped(tables['order_line'],'order_id'); oe=grouped(tables['order_event'],'order_id')
    for oid,order in orders.items():
        if sum(l['quantity']*l['unit_price_minor'] for l in ol[oid])!=order['total_minor']: fail('ARITHMETIC',oid,'order total')
        for l in ol[oid]:
            if lines[l['cart_line_id']]['cart_id']!=order['cart_id']: fail('OWNERSHIP',l['order_line_id'],'cross-cart order line')
        paid=[e for e in oe[oid] if e['event_type']=='paid']
        if len(paid)!=1 or paid[0]['occurred_at']!=order['ordered_at'] or paid[0]['amount_minor']!=order['total_minor']: fail('PAYMENT',oid,'payment must reconcile at order time')
        if sum(e['amount_minor'] for e in oe[oid] if e['event_type']=='refunded')>order['total_minor']: fail('REFUND',oid,'refund exceeds payment')
    cons=grouped(tables['consent'],'customer_id'); accepted=index(tables,'send_acceptance','send_id')
    dispatches=indexes['campaign_message']; campaigns=indexes['campaign']; templates=indexes['message_template']; sends=indexes['send_attempt']
    contacts=defaultdict(list)
    for receipt in sorted(tables['send_acceptance'],key=lambda x:(x['accepted_at'],x['send_id'])):
        send=sends[receipt['send_id']]; msg=dispatches[send['dispatch_id']]; cmp=campaigns[msg['campaign_id']]
        cid=cmp['customer_id']; cart=cmp['cart_id']; at=dt(receipt['accepted_at']); ch=templates[msg['template_id']]['channel']
        history=[Consent(c['channel'],c['state'],dt(c['effective_at']),dt(c['recorded_at']),c['revision']) for c in cons[cid]]
        events=cart_events[cart]
        last=max(dt(e['occurred_at']) for e in events if e['event_type'] in ('created','updated','checkout_started','reopened') and dt(e['occurred_at'])<=at)
        # Indexed payment lookup avoids cart-by-order quadratic scans for full data.
        purchased=next((dt(e['occurred_at']) for e in events if e['event_type']=='purchased' and dt(e['occurred_at'])<=at),None)
        ls=snapshot(line_events[cart],at)
        check=evaluate(now=at,last_activity=last,purchased_at=purchased,quantity=sum(x['quantity'] for x in ls),total_minor=sum(x['quantity']*x['unit_price_minor'] for x in ls),channel=ch,timezone=customers[cid]['timezone'],consent=history,contacts=contacts[cid])
        if not check.eligible: fail('DISPATCH_POLICY',receipt['send_id'],','.join(check.reasons))
        contacts[cid].append(Contact(ch,at))
    for e in tables['send_event']:
        if e['event_type'] in ('delivered','opened','clicked'):
            a=accepted.get(e['send_id'])
            if not a or dt(e['occurred_at'])<dt(a['accepted_at']): fail('SEND_LIFECYCLE',e['send_event_id'],'receipt before acceptance')
            if e['event_type']=='opened' and templates[dispatches[sends[e['send_id']]['dispatch_id']]['template_id']]['channel']=='sms': fail('SMS_OPEN',e['send_event_id'],'SMS has no opens')
    winners=oracle_attributions(tables)
    seen=set()
    for a in tables['attribution']:
        oid=a['order_id']
        if oid in seen: fail('DOUBLE_ATTRIBUTION',a['attribution_id'],'duplicate order credit')
        seen.add(oid)
        if winners.get(oid)!=a['click_event_id'] or a['revenue_minor']!=orders[oid]['total_minor']: fail('ATTRIBUTION',a['attribution_id'],'wrong winning click or revenue')
    if set(winners)!=seen: fail('ATTRIBUTION_COVERAGE','attribution','missing or extra credit')
    values=sorted(e['total_minor'] for e in tables['cart_event'] if e['event_type']=='created')
    channels=grouped(tables['message_template'],'channel')
    coverage={'multi_device_carts':sum(len(v)>1 for v in grouped(tables['cart_session'],'cart_id').values()),
              'consent_withdrawals':sum(x['state']=='withdrawn' and x['revision']>1 for x in tables['consent']),
              'quantity_updates':sum(x['revision']>1 for x in tables['cart_line_event']),
              'channel_templates':{k:len(v) for k,v in channels.items()},
              'cap_conflict_decisions':sum('CHANNEL_CAP' in x['reason_codes'] or 'GLOBAL_CAP' in x['reason_codes'] for x in tables['decision_log'])}
    distribution={'cart_total_minor_p50':values[len(values)//2] if values else None,'cart_total_minor_p90':values[int(len(values)*.9)] if values else None,
                  'lines_per_cart':len(tables['cart_line'])/len(carts) if carts else None}
    run=tables['dataset_run'][0] if tables['dataset_run'] else {}
    expected=load_config('generation')['profiles'].get(run.get('profile'))
    if expected and check_profile:
        actual={'customers':len(customers),'carts':len(carts),'abandoned_carts':len({x['cart_id'] for x in tables['cart_event'] if x['event_type']=='abandoned'}),'campaigns':len(campaigns),'send_attempts':len(sends)}
        if actual!=expected:fail('PROFILE_COUNTS',run.get('run_id'),'profile volume differs from configuration')
    return {'coverage':coverage,'distribution':distribution,'valid':not errors,'errors':errors,'row_counts':{k:len(v) for k,v in tables.items()},
            'ever_abandoned':len({e['cart_id'] for e in tables['cart_event'] if e['event_type']=='abandoned'}),
            'accepted_sends':len(accepted),'credited_orders':len(seen)}


def oracle_attributions(tables):
    """Independent slow/readable rule oracle; does not call production attribute()."""
    sends=index(tables,'send_attempt'); msgs=index(tables,'campaign_message'); receipts=index(tables,'send_acceptance','send_id')
    by_cart=defaultdict(list)
    for event in tables['send_event']:
        if event['event_type']=='clicked' and event['send_id'] in receipts:
            msg=msgs[sends[event['send_id']]['dispatch_id']]
            by_cart[msg['cart_id']].append(event)
    winners={}
    for order in tables['recovery_order']:
        hits=[]
        for event in by_cart[order['cart_id']]:
            age=(dt(order['ordered_at'])-dt(event['occurred_at'])).total_seconds()
            if 0<age<=7*86400: hits.append(event)
        if hits: winners[order['order_id']]=sorted(hits,key=lambda e:(dt(e['occurred_at']),e['send_event_id'],e['send_id']))[-1]['send_event_id']
    return winners


def detect(tables, claims):
    cons=grouped(tables['consent'],'customer_id'); carts=index(tables,'cart'); orders=index(tables,'recovery_order')
    sends=index(tables,'send_attempt'); msgs=index(tables,'campaign_message'); templates=index(tables,'message_template')
    attrs=index(tables,'attribution','order_id'); le=line_state(tables); findings=[]
    for c in claims:
        payload=c['payload']; at=dt(c['occurred_at']); issue=None; evidence=[]
        if c['claim_type']=='acceptance':
            msg=msgs[sends[c['entity_id']]['dispatch_id']]; cid=carts[msg['cart_id']]['customer_id']; ch=templates[msg['template_id']]['channel']
            known=[x for x in cons[cid] if x['channel']==ch and dt(x['effective_at'])<=at and dt(x['recorded_at'])<=at]
            latest=max(known,key=lambda x:(dt(x['effective_at']),x['state']=='withdrawn',x['revision']),default=None)
            if latest is None or latest['state']!='granted': issue='SEND_AFTER_OPT_OUT'; evidence=[latest['consent_id']] if latest else []
        elif c['claim_type']=='abandonment':
            paid=[o for o in orders.values() if o['cart_id']==c['entity_id'] and dt(o['ordered_at'])<=at]
            if paid: issue='ABANDONED_AFTER_PURCHASE'; evidence=[paid[0]['order_id']]
        elif c['claim_type']=='credit':
            winner=attrs.get(c['entity_id'])
            if winner and winner['send_id']!=payload['send_id']: issue='DOUBLE_ATTRIBUTION'; evidence=[winner['attribution_id']]
        elif c['claim_type']=='snapshot':
            expected=sum(x['quantity']*x['unit_price_minor'] for x in snapshot(le[c['entity_id']],at))
            if payload['total_minor']!=expected: issue='STALE_CART_TOTAL'; evidence=[x['line_event_id'] for x in snapshot(le[c['entity_id']],at)]
        if issue: findings.append({'offending_record_id':c['claim_id'],'entity_id':c['entity_id'],'issue_type':issue,'supporting_ids':evidence,'expected_action':'reject_claim'})
    return findings
