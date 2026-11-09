# Validation and metrics

## Executed coverage

`tests/` exercises boundary times, independent channel consent, same-time withdrawal precedence,
known-time consent, customer-wide rolling caps, quiet hours, deterministic variant and attribution,
PK/FK/duplicate credit/immutability constraints, generation/export equivalence, tampered data detection,
normal recovery, withdrawal, retries, refunds, multi-device activity, reopening, late purchases,
role/request protection, idempotency and two concurrent workers competing for contact capacity.

The baseline validator checks required fields, primary keys, unique/composite keys, ordinary/composite
foreign keys, enum/type/ID values, aware timestamps, occurrence/recording order, IANA timezone validity,
line/cart revisions, session date order, ownership joins, line-total arithmetic, paid-order/refund
reconciliation, purchased-cart terminal behavior, valid abandonment and accepted-send policy. It
independently verifies every credited order's winning click and exact profile counts. Failures identify
check, offending record and detail; at most 100 sample errors are returned. PostgreSQL additionally
enforces SQL checks and append-only history at import/runtime.

All four required challenge classes have five labelled cases and benign controls. The detector never
receives expected labels; the evaluator reports per-class and aggregate TP/FP/FN, precision and recall.
These metrics describe fixture coverage and do not claim unseen production anomaly accuracy.

`artifacts/tests.xml`, `artifacts/http-smoke.json`, `artifacts/full-import.json` and
`artifacts/reproducibility.json` hold actual execution evidence. Generated baseline reports live with
the dataset. The console distinguishes those archived reports from current manual scenario state.

## Dashboard metric grain

One accepted logical dispatch is one SendAcceptance row; retries and callbacks cannot multiply it.
Counts use distinct send/dispatch/order IDs as appropriate. All money is integer INR paise in storage.

- Ever abandoned: distinct carts with a valid abandonment event, including later recovered carts.
- Current cart state: payment first, then empty/expired/inactive/active based on source facts.
- Delivered/clicked: accepted sends with distinct delivery/click receipts. No SMS opens are inferred.
- Credited conversion: settled credited orders / accepted dispatches, explicitly an observed-to-date
  funnel. Recently contacted cohorts may be censored; no causal-lift claim is made.
- Settled paid orders: payment at least 24 hours before the demo clock. Newer orders show as pending.
- Credited orders: one canonical attribution whose decision time has passed.
- Late orders: settled uncredited orders with a prior same-cart click more than seven days before payment.
- Organic orders: remaining settled uncredited orders. These classes are mutually exclusive.
- Gross credited revenue: sum of credited order totals. Net credited revenue subtracts their refund events.
- Net paid revenue: all paid totals minus valid refund events.
- Channel/variant totals use the winning send, and sum to the overall credited totals.
- Precision/recall use matched `(issue_type, offending_record_id)`, with null for a zero denominator.

```text
settled paid orders = credited + late + organic
all paid orders = settled paid orders + pending settlement
gross paid revenue = gross credited revenue + gross uncredited revenue
net credited revenue = gross credited revenue - credited-order refunds
accepted logical dispatches = SendAcceptance row count
credited orders = unique attributed order count
```

Full-profile volume checks require 50,000 carts / 20,000 ever-abandoned / 10,000 campaigns /
10,000 evaluated initial attempts. The reproducibility check requires all canonical file hashes to
match across two independent seeded generations. The import check requires every SQL-imported row to
match JSON and CSV, beyond just matching counts.

## Re-run verification

```bash
TEST_DATABASE_URL="$DATABASE_URL" uv run pytest
uv run python scripts/smoke_http.py --url http://localhost:8080
uv run recovery validate --input data/full
uv run recovery evaluate --input data/full
uv run recovery reproducibility --profile full --out artifacts/new-repro
uv run python scripts/check_full_import.py --input data/full
```

Use an empty output path for generation/reproducibility. HTTP smoke creates demonstration records and
advances simulated time. SQL round-trip and database tests use temporary schemas and leave app tables
alone. Live snapshots should have all candidate order settlements processed before validated export.
