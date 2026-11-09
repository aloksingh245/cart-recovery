import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from cart_recovery.rules import Policy
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_and_generated_artifacts_do_not_drift():
    spec = importlib.util.spec_from_file_location("render", ROOT / "scripts/build_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path, content in module.render().items():
        assert path.read_text() == content
    assert json.loads((ROOT / "config/policy.json").read_text()) == asdict(Policy())


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL for PostgreSQL smoke")
def test_postgres_schema_integrity_and_history():
    name = "recovery_test_" + uuid4().hex
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        try:
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(name)))
            conn.execute((ROOT / "db/001_initial.sql").read_text())
            conn.execute("""INSERT INTO dataset_run VALUES
                ('RUN-20261022-test', 20261022, 'starter', '2026-10-01Z', '2026-11-01Z',
                 'recovery-v1', %s)""", ("a" * 64,))
            conn.execute("""INSERT INTO customer VALUES
                ('CUS-000001', 'RUN-20261022-test', 'one@example.test', NULL, 'Asia/Kolkata', '2026-10-01Z')""")
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute("INSERT INTO customer SELECT * FROM customer")
            with pytest.raises(psycopg.errors.RaiseException):
                conn.execute("UPDATE customer SET timezone='UTC'")
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute("INSERT INTO cart VALUES ('CART-2026-999999', 'CUS-999999', 'INR', '2026-10-01Z')")
            conn.execute("INSERT INTO cart VALUES ('CART-2026-000001', 'CUS-000001', 'INR', '2026-10-01Z')")
            conn.execute("""INSERT INTO campaign VALUES
                ('CMP-2026-000001','CART-2026-000001','CUS-000001',1,'A','2026-10-02Z','recovery-v1')""")
            conn.execute("""INSERT INTO message_template VALUES
                ('MSG-CART-2026-000001-01','CART-2026-000001','email','A',1,'Saved cart','Your items','2026-10-02Z')""")
            conn.execute("""INSERT INTO campaign_message VALUES
                ('DSP-2026-000001','CMP-2026-000001','MSG-CART-2026-000001-01','CART-2026-000001',1,
                 '2026-10-02T10:00Z','dispatch-one')""")
            conn.execute("""INSERT INTO send_attempt VALUES
                ('SEND-2026-000001','DSP-2026-000001',1,'2026-10-02T10:00Z','recovery-v1')""")
            conn.execute("""INSERT INTO send_acceptance VALUES
                ('DSP-2026-000001','SEND-2026-000001','sim-one','2026-10-02T10:00Z')""")
            conn.execute("""INSERT INTO send_event VALUES
                ('SE-000001','SEND-2026-000001','clicked','2026-10-02T11:00Z','2026-10-02T11:00Z','sim-click',NULL)""")
            conn.execute("""INSERT INTO recovery_order VALUES
                ('ORD-2026-000001','CART-2026-000001','CUS-000001','2026-10-02T12:00Z','INR',10000)""")
            conn.execute("""INSERT INTO attribution VALUES
                ('ATR-2026-000001','ORD-2026-000001','SEND-2026-000001','SE-000001',
                 'last_click_7d_same_cart_v1',10000,'2026-10-03T12:00Z','recovery-v1')""")
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute("""INSERT INTO attribution SELECT 'ATR-2026-000002', order_id,
                    send_id, click_event_id, model, revenue_minor, decided_at, policy_version FROM attribution""")
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute("INSERT INTO send_acceptance SELECT * FROM send_acceptance")
            assert conn.execute("SELECT count(*) FROM attribution").fetchone()[0] == 1
        finally:
            conn.execute("SET search_path TO public")
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
