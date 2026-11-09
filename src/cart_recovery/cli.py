import argparse
import json
import shutil
import time
from pathlib import Path

from .common import ROOT,canonical


def main():
    parser=argparse.ArgumentParser(description='Consent-aware synthetic cart recovery')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('policy');sub.add_parser('init-db')
    for command in ('generate','demo','reproducibility'):
        p=sub.add_parser(command);p.add_argument('--profile',choices=['starter','full'],default='starter');p.add_argument('--seed',type=int,default=20261022)
        p.add_argument('--out',type=Path);p.add_argument('--scale',type=float,default=1.0)
    for command in ('validate','import-data','evaluate','export'):
        p=sub.add_parser(command);p.add_argument('--input',type=Path,default=ROOT/'data/starter');p.add_argument('--out',type=Path)
    w=sub.add_parser('worker');w.add_argument('--once',action='store_true');w.add_argument('--limit',type=int,default=100)
    sub.add_parser('scan');sub.add_parser('settle')
    args=parser.parse_args()
    if args.command=='worker' and args.limit<1:parser.error('--limit must be positive')
    from .repository import initialize,connect,import_tables,dump_tables,insert
    from .generator import generate
    from .exports import write_dataset,read_dataset,evaluate_findings
    from .validation import validate,detect
    from . import services
    result={}
    if args.command=='policy':result=json.loads((ROOT/'config/policy.json').read_text())
    elif args.command=='init-db':initialize();result={'initialized':True}
    elif args.command in ('generate','demo'):
        out=args.out or ROOT/'data'/args.profile
        if args.command=='demo':
            initialize()
            with connect() as c:existing=c.execute('SELECT count(*) AS n FROM customer').fetchone()['n']
            if existing:print(canonical({'ready':True,'customers':existing,'note':'existing database retained'}));return
        if args.command=='demo' and out.exists() and any(out.iterdir()):
            tables=read_dataset(out);result=validate(tables)
            run=tables['dataset_run'][0]
            if not result['valid'] or run['seed']!=args.seed or run['profile']!=(args.profile if args.scale==1 else 'custom'):raise ValueError('Existing export is invalid or has a different profile/seed; choose a new --out')
        else:
            tables=generate(args.profile,args.seed,args.scale)
            result=write_dataset(tables,out)
        if args.command=='demo':
            import_tables(tables)
            claims=[json.loads(line) for line in (out/'input/challenge/claims.jsonl').read_text().splitlines()]
            findings=detect(tables,claims)
            with connect() as c:
                for finding in findings:insert(c,'issue',issue_type=finding['issue_type'],offending_record_id=finding['offending_record_id'],entity_id=finding['entity_id'],supporting_ids=finding['supporting_ids'],created_at=services.clock(c))
            result['imported']=True
    elif args.command=='reproducibility':
        base=args.out or ROOT/'artifacts'/f'reproducibility-{args.profile}'
        base.mkdir(parents=True,exist_ok=True)
        paths=[base/'run-a',base/'run-b']
        for path in paths:write_dataset(generate(args.profile,args.seed,args.scale),path)
        manifests=[json.loads((p/'metadata/checksums.json').read_text()) for p in paths]
        a,b=manifests
        mismatches=[name for name in a.keys()|b.keys() if a.get(name)!=b.get(name)]
        result={'passed':not mismatches,'seed':args.seed,'profile':args.profile,'compared_payloads':len(a),'mismatches':mismatches,
                'row_counts':json.loads((paths[0]/'metadata/validation-summary.json').read_text())['row_counts']}
        (base/'report.json').write_text(canonical(result)+'\n')
        if mismatches:raise SystemExit('Reproducibility failed')
    elif args.command=='validate':
        result=validate(read_dataset(args.input))
        if not result['valid']:print(canonical(result));raise SystemExit(1)
    elif args.command=='import-data':
        initialize();tables=read_dataset(args.input);report=validate(tables)
        if not report['valid']:raise ValueError(report['errors'])
        import_tables(tables)
        claims_path=args.input/'input/challenge/claims.jsonl'
        if claims_path.exists():
            findings=detect(tables,[json.loads(line) for line in claims_path.read_text().splitlines()])
            with connect() as c:
                for finding in findings:insert(c,'issue',issue_type=finding['issue_type'],offending_record_id=finding['offending_record_id'],entity_id=finding['entity_id'],supporting_ids=finding['supporting_ids'],created_at=services.clock(c))
        result={'imported':True,'row_counts':report['row_counts']}
    elif args.command=='evaluate':
        tables=read_dataset(args.input)
        claims=[json.loads(line) for line in (args.input/'input/challenge/claims.jsonl').read_text().splitlines()]
        findings=detect(tables,claims)
        truth=json.loads((args.input/'ground_truth/ground_truth.json').read_text())
        result=evaluate_findings(findings,truth)
        if not result['passed']:print(canonical(result));raise SystemExit(1)
    elif args.command=='export':result=write_dataset(dump_tables(),args.out or ROOT/'data/export',check_profile=False)
    elif args.command=='scan':result=services.scan()
    elif args.command=='settle':result=services.settle()
    elif args.command=='worker':
        while True:
            results=[]
            for _ in range(args.limit):
                row=services.work_once();results.append(row)
                if row.get('idle') or row.get('paused'):break
            settled=services.settle()
            if args.once:result={'results':results,'settlement':settled};break
            if not results[-1].get('idle') and not results[-1].get('paused'):print(canonical({'results':results}),flush=True)
            time.sleep(1)
    if getattr(args,'out',None) and args.command in ('validate','evaluate'):args.out.write_text(canonical(result)+'\n')
    print(json.dumps(result,indent=2,default=str))


if __name__=='__main__':main()
