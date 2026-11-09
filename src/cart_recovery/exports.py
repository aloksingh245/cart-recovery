import csv
import json
import shutil
from hashlib import sha256
from pathlib import Path
from datetime import timedelta

from .common import ROOT, TABLES, COLUMNS, canonical, dt, iso, load_config
from .validation import validate, detect, oracle_attributions, grouped


def challenges(tables):
    """Construct false and true claims; truth is kept in a separate export."""
    claims=[]; truth=[]
    def add(kind,entity,at,payload,issue=None):
        key=f'CLAIM-{len(claims)+1:06d}'
        claims.append({'claim_id':key,'claim_type':kind,'entity_id':entity,'occurred_at':at,'recorded_at':at,'payload':payload})
        if issue: truth.append({'truth_id':f'TRUTH-{len(truth)+1:06d}','offending_record_id':key,'entity_id':entity,
                                'issue_type':issue,'expected_decision':'reject_claim','policy_version':'recovery-v1'})
    suppressed=[s for s in tables['send_event'] if s['event_type']=='suppressed'][:5]
    for s in suppressed: add('acceptance',s['send_id'],s['occurred_at'],{},'SEND_AFTER_OPT_OUT')
    for o in tables['recovery_order'][:5]: add('abandonment',o['cart_id'],iso(dt(o['ordered_at'])+timedelta(minutes=1)),{},'ABANDONED_AFTER_PURCHASE')
    accepted=tables['send_acceptance']
    for a in tables['attribution'][:5]:
        other=next(s for s in accepted if s['send_id']!=a['send_id'])
        add('credit',a['order_id'],a['decided_at'],{'send_id':a['send_id']})
        add('credit',a['order_id'],a['decided_at'],{'send_id':other['send_id']},'DOUBLE_ATTRIBUTION')
    updates=[e for e in tables['cart_event'] if e['event_type']=='updated'][:5]
    by_cart=grouped(tables['cart_event'],'cart_id')
    for e in updates:
        old=next(x for x in by_cart[e['cart_id']] if x['event_type']=='created')
        add('snapshot',e['cart_id'],e['occurred_at'],{'total_minor':old['total_minor']},'STALE_CART_TOTAL')
        add('snapshot',e['cart_id'],e['occurred_at'],{'total_minor':e['total_minor']})
    return claims,truth


def evaluate_findings(findings, truth):
    actual={(x['issue_type'],x['offending_record_id']) for x in findings}
    expected={(x['issue_type'],x['offending_record_id']) for x in truth}
    classes={}
    for label in sorted({x[0] for x in expected|actual}):
        a={x for x in actual if x[0]==label}; e={x for x in expected if x[0]==label}
        tp=len(a&e); fp=len(a-e); fn=len(e-a)
        classes[label]={'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}
    tp=len(actual&expected); fp=len(actual-expected); fn=len(expected-actual)
    return {'passed':not fp and not fn,'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,
            'recall':tp/(tp+fn) if tp+fn else None,'classes':classes}


def sql_value(v):
    if v is None:return 'NULL'
    if isinstance(v,(int,float)):return str(v)
    if isinstance(v,(list,dict)):v=canonical(v)
    return "'"+str(v).replace("'","''")+"'"


def write_dataset(tables, output, check_profile=True):
    out=Path(output)
    if out.exists() and any(out.iterdir()): raise ValueError('Output directory must be empty to avoid mixing generation runs')
    for sub in ('input/baseline/csv','input/baseline/json','input/challenge','ground_truth','metadata'): (out/sub).mkdir(parents=True,exist_ok=True)
    report=validate(tables,check_profile=check_profile)
    report['scope']='baseline' if check_profile else 'live_snapshot'
    if not report['valid']: raise ValueError(f'Baseline validation failed: {report["errors"][:3]}')
    with (out/'input/baseline/seed.sql').open('w') as sqlfile:
        sqlfile.write('BEGIN;\n')
        for t in TABLES:
            name=t['name']; cols=COLUMNS[name]; rows=sorted(tables[name],key=lambda r:str(r[cols[0]]))
            with (out/f'input/baseline/csv/{name}.csv').open('w',newline='') as f:
                w=csv.writer(f,lineterminator='\n'); w.writerow(cols)
                for r in rows:w.writerow([canonical(r[c]) if isinstance(r[c],(dict,list)) else r[c] for c in cols])
            (out/f'input/baseline/json/{name}.json').write_text(canonical(rows)+'\n')
            for offset in range(0,len(rows),500):
                values=','.join('('+','.join(sql_value(r[c]) for c in cols)+')' for r in rows[offset:offset+500])
                sqlfile.write(f'INSERT INTO {name} ({",".join(cols)}) VALUES {values};\n')
        sqlfile.write('COMMIT;\n')
    claims,truth=challenges(tables)
    (out/'input/challenge/claims.jsonl').write_text(''.join(canonical(x)+'\n' for x in claims))
    (out/'ground_truth/ground_truth.json').write_text(canonical(truth)+'\n')
    with (out/'ground_truth/anomalies.csv').open('w',newline='') as f:
        cols=list(truth[0]) if truth else ['truth_id','offending_record_id','issue_type']
        w=csv.DictWriter(f,fieldnames=cols,lineterminator='\n');w.writeheader();w.writerows(truth)
    # Independent oracle supplies expected order credits; never part of input features.
    (out/'ground_truth/decisions.json').write_text(canonical(oracle_attributions(tables))+'\n')
    findings=detect(tables,claims)
    evaluation=evaluate_findings(findings,truth)
    (out/'metadata/validation-summary.json').write_text(canonical(report)+'\n')
    (out/'metadata/evaluation.json').write_text(canonical(evaluation)+'\n')
    (out/'metadata/findings.json').write_text(canonical(findings)+'\n')
    for source,name in [('db/001_initial.sql','schema.sql'),('docs/data-dictionary.csv','data-dictionary.csv'),('docs/source-manifest.json','source-manifest.json'),('config/generation.json','generation-config.json'),('config/policy.json','policy.json')]: shutil.copyfile(ROOT/source,out/'metadata'/name)
    code_hash=sha256()
    for source in sorted((ROOT/'src/cart_recovery').glob('*.py')):
        code_hash.update(source.name.encode());code_hash.update(source.read_bytes())
    run=tables['dataset_run'][0]|{'generator_version':'1.0.0','code_sha256':code_hash.hexdigest()}
    (out/'metadata/run.json').write_text(canonical(run)+'\n')
    (out/'metadata/README.md').write_text('# Synthetic cart recovery dataset\n\nAll entity data is synthetic. Input features and evaluator-only ground truth are separate.\nApply metadata/schema.sql before input/baseline/seed.sql to an empty PostgreSQL schema.\nMoney is integer INR paise. Times are UTC. Policy and generation settings are included.\n')
    checks={str(p.relative_to(out)):sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'metadata/checksums.json').write_text(canonical(checks)+'\n')
    return report|{'evaluation':evaluation,'payload_files':len(checks)}


def read_dataset(directory, format='json'):
    root=Path(directory)
    if (root/'input/baseline').exists():root=root/'input/baseline'
    result={}
    for t in TABLES:
        name=t['name']
        if format=='json':result[name]=json.loads((root/f'json/{name}.json').read_text())
        else:
            with (root/f'csv/{name}.csv').open(newline='') as f:rows=list(csv.DictReader(f))
            for row in rows:
                for field in t['fields']:
                    v=row[field['name']]
                    row[field['name']]=None if v=='' else int(v) if field['type']=='bigint' else json.loads(v) if field['type']=='jsonb' else v
            result[name]=rows
    return result
