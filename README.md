# Cart Recovery

A working local application for abandoned-cart recovery: identify inactivity, respect email/SMS
consent and contact limits, coordinate personalized messages, and credit orders to a single click.
The operations console includes cart traces, campaigns, exception reviews, metrics and a scenario studio.
All customer data and delivery are synthetic.

## Start the app

Install Docker Desktop or Docker Engine with Compose, unzip this project, and run from its folder:

```bash
docker compose up --build -d
```

Open **http://localhost:8080**. Choose **Operations manager** and sign in with **`recovery-demo`**.
The first start generates/imports 1,000 starter carts, applies migrations and starts the worker.
Allow a minute for the initial image build. The service preserves its database and export volumes
between restarts. Set `DEMO_PASSWORD` before starting to change the local demo password.

```bash
docker compose logs -f app worker
docker compose down
```

`down` stops the application and preserves data. This application binds to loopback and uses demo
credentials. It is intended for a local synthetic-store demonstration, not a public production deployment.

## Try the complete workflow

1. Open **Scenario studio → Recover a saved cart**.
2. Open the cart; process due messages if the background worker has not already sent it.
3. Click **Deliver**, then **Simulate click (+1 min)**.
4. Click **Simulate purchase (+1 min)**, then **Advance 1 day & settle**.
5. Inspect the one winning send/click under **Conversion trace** and its decision evidence.
6. Create **Withdraw before dispatch**. Confirm the suppressed message and `NO_CONSENT` evidence.
7. Try SMS, a transient retry and a second-device update. Inspect **Exceptions** for all four
   injected anomaly types; append a review note. Download validation/evaluation reports.

The visible clock is simulated. Clock controls never change the computer's time. The worker processes
jobs automatically, but simulated delivery, click and purchase require explicit actions.
Analyst and operator roles can inspect data; only a manager can change it.

## Included datasets and evidence

The shareable archive includes `data/starter/` and `data/full/` with CSV, JSON and PostgreSQL seed
exports, schema, dictionary, policy, configuration, provenance, checksums and separate ground truth.
The full baseline contains **50,000 carts, 20,000 ever-abandoned carts, 10,000 per-cart campaign
instances and 10,000 evaluated send attempts**. Accepted sends are a separately measured subset.

`artifacts/reproducibility.json` records two independent full-volume runs. `artifacts/full-import.json`
records CSV/JSON equality and a row-for-row SQL import comparison. See [verification](docs/verification.md)
for executed checks and [generation](docs/generation.md) for the exact data contract.

Generated datasets and artifacts are ignored by git; they are explicitly included in the ZIP.
If working from a source checkout without them, use the commands below to regenerate them.

## Develop locally

Prerequisites: Python 3.13, [uv](https://docs.astral.sh/uv/), PostgreSQL 16 (the Compose database works).

```bash
uv sync --frozen
docker compose up -d --wait db
export DATABASE_URL=postgresql://recovery:recovery_local@localhost:55432/recovery
uv run recovery demo
uv run uvicorn cart_recovery.api:app --host 127.0.0.1 --port 8000
```

Run the worker in another terminal with the same `DATABASE_URL`:

```bash
uv run recovery worker
```

`demo` initializes an empty database and generates/imports starter data. It imports existing
validated starter exports when present and retains an existing database. You can also import
a specific dataset into an empty database:

```bash
uv run recovery init-db
uv run recovery import-data --input data/starter
```

## Generate, validate and test

Generation requires an empty output directory. Use a new directory to retain earlier runs.

```bash
uv run recovery generate --profile full --seed 20261022 --out data/new-full
uv run recovery validate --input data/new-full
uv run recovery evaluate --input data/new-full
uv run recovery reproducibility --profile full --out artifacts/new-repro
TEST_DATABASE_URL="$DATABASE_URL" uv run pytest
uv run python scripts/smoke_http.py --url http://localhost:8080
uv run python scripts/check_full_import.py --input data/full
```

Without `TEST_DATABASE_URL`, database integration tests are intentionally skipped. Tests create and
remove unique temporary schemas; they do not reset application tables. `check_full_import.py` needs
`psql` on PATH. The HTTP smoke creates scenarios and advances the demo clock, so run it on a demo database.
Use `recovery export --out data/snapshot` after advancing/settling pending purchases to export live facts.

API documentation: `/docs`. Health: `/healthz`; database readiness: `/readyz`.
Every mutation uses a signed manager session, request-protection header and idempotency key.

## Architecture and project map

```text
Browser console -> FastAPI services -> PostgreSQL facts, events and audit trail
                                            |
                                      queued dispatches
                                            |
                                     simulated worker
                                            |
                               receipts -> orders -> attribution

Seeded generator -> CSV / JSON / SQL -> validator
Challenge claims -> detector -> findings -> evaluator <- separate ground truth
```

- `src/cart_recovery/`: generator, exports, validator, domain rules, database services, worker,
  queries, API and static console.
- `db/`: generated core migration plus versioned runtime migrations.
- `config/`: policy and generation profiles; `docs/data-dictionary.csv`: every core column.
- `tests/`: boundaries, integrity, generation, export equivalence, HTTP/role/idempotency and concurrency.
- `scripts/`: schema rendering, HTTP smoke, full SQL round-trip and release packaging.
- `docs/`: [architecture](docs/architecture.md), [business rules](docs/domain-rules.md),
  [API](docs/api.md), [validation](docs/validation.md), [AI disclosure](docs/ai-usage.md).

## Scope and limits

One synthetic store; INR paise; UTC facts and customer-local quiet hours; 60-minute abandonment,
14-day expiry, email/SMS caps and seven-day same-cart last-click credit. Business history is append-only.
One order per cart; refunds reduce net credited revenue. Metrics label pending settlement and observed
cohorts. Attribution measures credited recovery, not causal lift.

Email/SMS providers and payments are simulated. Real storefront/provider integrations, public-hosting
hardening, inventory integration and a randomized lift experiment are outside this local app.
No real personal data, external datasets or live messages are used. Public GitHub publishing and the
candidate's complete session transcript/personal review remain submission tasks for the owner.
