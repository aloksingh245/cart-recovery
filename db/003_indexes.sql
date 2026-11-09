BEGIN;
CREATE INDEX IF NOT EXISTS decision_order_idx ON decision_log ((input_refs->>'order_id')) WHERE decision_type='attribution';
INSERT INTO schema_version(version) VALUES (3) ON CONFLICT DO NOTHING;
COMMIT;
