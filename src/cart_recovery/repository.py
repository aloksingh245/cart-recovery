import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .common import ROOT, TABLES, COLUMNS, canonical

DEFAULT_DSN='postgresql://recovery:recovery_local@localhost:55432/recovery'


CURRENT=ContextVar('recovery_connection',default=None)


@contextmanager
def connect():
    if CURRENT.get() is not None:
        yield CURRENT.get()
        return
    options={}
    if os.environ.get('RECOVERY_SCHEMA'):options['options']='-c search_path='+os.environ['RECOVERY_SCHEMA']
    with psycopg.connect(os.environ.get('DATABASE_URL',DEFAULT_DSN),row_factory=dict_row,**options) as connection:
        yield connection


def initialize():
    with connect() as c:
        if not c.execute("SELECT to_regclass('customer') AS t").fetchone()['t']:
            c.execute((ROOT/'db/001_initial.sql').read_text())
        if not c.execute("SELECT to_regclass('runtime_state') AS t").fetchone()['t']:
            c.execute((ROOT/'db/002_runtime.sql').read_text())
        if not c.execute('SELECT 1 FROM schema_version WHERE version=3').fetchone():
            c.execute((ROOT/'db/003_indexes.sql').read_text())


def insert(c,table,**row):
    fields=list(row)
    c.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,fields)),sql.SQL(',').join(sql.Placeholder() for _ in fields)),
              [Jsonb(v) if isinstance(v,(dict,list)) else v for v in row.values()])
    return row


def new_id(c,prefix):
    number=c.execute("SELECT nextval('runtime_ids') AS n").fetchone()['n']
    return prefix+f"{number:06d}"


def import_tables(tables):
    with connect() as c:
        if c.execute('SELECT count(*) AS n FROM customer').fetchone()['n']:raise ValueError('Database already contains customers; import requires an empty database')
        for t in TABLES:
            name=t['name']; cols=COLUMNS[name]
            with c.cursor().copy(sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(name),sql.SQL(',').join(map(sql.Identifier,cols)))) as copy:
                for row in tables[name]:copy.write_row([Jsonb(row[col]) if isinstance(row[col],(dict,list)) else row[col] for col in cols])


def dump_tables():
    with connect() as c:
        data={}
        from .common import iso
        from datetime import datetime
        for t in TABLES:
            rows=c.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(t['name']))).fetchall()
            data[t['name']]=[{k:iso(v) if isinstance(v,datetime) else v for k,v in row.items()} for row in rows]
        return data
