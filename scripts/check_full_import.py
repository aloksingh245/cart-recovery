"""Verify CSV/JSON equality and SQL round-trip in an isolated temporary schema."""
import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from cart_recovery.common import ROOT,TABLES,COLUMNS,canonical,iso
from cart_recovery.exports import read_dataset
from datetime import datetime

p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=ROOT/'data/full');p.add_argument('--out',type=Path,default=ROOT/'artifacts/full-import.json');a=p.parse_args()
dsn=os.environ.get('DATABASE_URL','postgresql://recovery:recovery_local@localhost:55432/recovery')
name='recovery_roundtrip_'+uuid4().hex
baseline=a.input/'input/baseline'
json_data=read_dataset(a.input);csv_data=read_dataset(a.input,'csv')
assert json_data==csv_data,'CSV and JSON disagree'
del csv_data
with psycopg.connect(dsn,autocommit=True) as c:
    c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        env=os.environ|{'PGOPTIONS':'-c search_path='+name}
        subprocess.run(['psql',dsn,'-X','-v','ON_ERROR_STOP=1','-q','-f',str(a.input/'metadata/schema.sql'),'-f',str(baseline/'seed.sql')],env=env,check=True,stdout=subprocess.DEVNULL)
        c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(name)))
        counts={}
        for t in TABLES:
            columns=COLUMNS[t['name']]
            with c.cursor() as cursor:
                cursor.execute(sql.SQL('SELECT {} FROM {} ORDER BY {}').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier(t['name']),sql.Identifier(columns[0])))
                expected=sorted(json_data[t['name']],key=lambda r:str(r[columns[0]]))
                rows=cursor.fetchall();assert len(rows)==len(expected)
                for row,want in zip(rows,expected):
                    actual={k:iso(v) if isinstance(v,datetime) else v for k,v in zip(columns,row)}
                    assert actual==want,(t['name'],actual,want)
                counts[t['name']]=len(rows)
        result={'passed':True,'representations':['csv','json','sql'],'row_counts':counts,'compared_rows':sum(counts.values())}
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(result)
    finally:
        c.execute('SET search_path TO public')
        c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
