# Runtime schema additions

`db/catalog.py` and `docs/data-dictionary.csv` describe the 24 core/data-export relations. Migration
002 adds six runtime-only relations; migration 003 adds the settlement evidence index. Runtime tables
are deliberately not synthetic input features or ground-truth exports.

## schema_version

- `version`: integer, required PK, unique migration number.
- `applied_at`: timestamptz, required, default database now; UTC migration application time.

## runtime_state

- `id`: integer, required PK, exactly 1 (one simulation singleton).
- `clock`: timestamptz, required; explicit UTC simulation instant, advances only forward through API.
- `paused`: boolean, required, default false; current operational dispatch pause projection.

## operation_event

- `operation_id`: bigint generated identity, required unique PK.
- `actor`: text, required; demo role/source performing the action.
- `action`: text, required; operation name (scenario creation, clock advance, pause, consent, purchase, cancel).
- `entity_id`: optional text; related cart/customer/campaign ID, or null for a global operation.
- `details`: jsonb object, required, default `{}`; action parameters, never credentials or ground truth.
- `occurred_at`: timestamptz, required; UTC simulation time.

## ingest_receipt

- `source_key`: text, required PK; HTTP Idempotency-Key, at most 160 characters at API boundary.
- `request_hash`: text, required; SHA-256 of actor/path/canonical payload.
- `response`: jsonb, required; original business result for exact retry replay.

## issue

- `issue_id`: bigint generated identity, required unique PK.
- `issue_type`: text, required; one of the four detector issue codes in this app.
- `offending_record_id`: text, required; challenge claim ID.
- `entity_id`: text, required; referenced business entity.
- `supporting_ids`: jsonb string array, required; fact/decision evidence references.
- `created_at`: timestamptz, required; UTC simulation time when imported.
- `(issue_type, offending_record_id)` is unique; repeated detection cannot create duplicate findings.

## issue_review

- `review_id`: bigint generated identity, required unique PK.
- `issue_id`: bigint, required FK to issue.issue_id; Issue 1:N Review, review always has one issue.
- `actor`: text, required; manager role, verified at API boundary.
- `note`: text, required, 3..1000 characters at API boundary.
- `created_at`: timestamptz, required; UTC simulation review time.

Operation events, receipts, issues and review histories reject update/delete. Reviews append rather
than overwriting issue facts. Operational clock/pause state is mutable. `runtime_ids` is a PostgreSQL
sequence beginning at 1,000,000 to avoid collisions with the deterministic baseline identifiers.
