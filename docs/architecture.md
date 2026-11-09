# Implemented architecture

Cart Recovery is a modular Python application with FastAPI, PostgreSQL 16, a browser console and a
worker using the same services. `src/cart_recovery/` contains the complete implementation.

## Runtime boundaries

The browser loads local HTML/CSS/JavaScript; it uses authenticated JSON APIs. The console provides
an overview, filtered cart queue, single-cart event/decision trace, campaigns, exceptions and reviews,
data-quality downloads and a scenario studio. No external assets or provider services are required.

`services.py` owns business transactions. `repository.py` provides parameterized SQL and a
context-local connection so nested service calls participate in one transaction. `rules.py` is pure
policy; `queries.py` computes read models and metrics. PostgreSQL stores facts, events, decisions,
idempotency receipts, job projections, review history and the explicit simulation clock.

## Transaction and concurrency design

All cart/consent/purchase/dispatch mutations lock their customer row before any job locks. The worker
selects a candidate, locks its customer, locks/rechecks the job with `SKIP LOCKED`, re-evaluates policy,
and commits simulated acceptance, receipt, events, decision and job completion together. Competing
workers cannot spend one customer's cap concurrently. There is no network call inside this transaction;
the delivery provider is an in-process simulator. Accepted sends count once by logical dispatch.

Unlike a real network provider, this simulator needs no separate externally-held contact reservation.
The schema retains lease/unknown states for imported histories, but this worker performs each submission
atomically rather than using a two-transaction claim/lease protocol. Expired imported leases can be
rechecked. Unknown external acceptance reconciliation is outside the simulated adapter.

HTTP mutations require manager access, a custom request-protection header, same-origin checks when
Origin is supplied, and an Idempotency-Key. An advisory transaction lock serializes each request key;
request hash and response are stored in `ingest_receipt` in the same transaction as business effects.
A changed payload reusing the key returns 409. Callback and payment source keys add storage deduplication.

## Business execution

A scanner considers genuine activity across linked devices. At 60 minutes of inactivity it checks
cart contents, payment, expiry, consent, contact availability, quiet hours and customer-wide caps.
It records the decision and enrolls an eligible cart in a campaign with immutable personalized copy.
Repeated scanning retains the same episode. A quantity update recalculates totals, reopens the cart,
cancels obsolete queued work and allows a fresh episode after another inactivity window.

The worker rechecks everything at dispatch. Missing consent or completed purchase suppresses/cancels;
quiet/cap conflicts defer for one simulated hour and are rechecked. A consent withdrawal immediately
cancels pending contact on that channel, appending a suppressed first attempt when necessary. Purchase
cancels this cart's pending messages. A manager can pause dispatch or cancel a campaign. The transient
failure scenario fails once, retries after one minute and yields one logical acceptance.

Delivery/open/click events are append-only simulated callbacks. SMS never has open events. A successful
payment creates one Order and line snapshots; one paid order is allowed per cart. After 24 hours of
simulated ingestion settlement, attribution chooses the latest eligible same-customer/same-cart click
within seven days, breaking ties by event ID and send ID. A unique order constraint prevents double
credit. Refund events reduce net revenue without editing the original attribution.

The simulator records callbacks at the current clock. Arbitrary backdated provider ingestion and
post-finalization reassignment are outside this adapter. Effective/recorded timestamps remain in the
schema and pure rule tests cover known-time consent selection.

## Dataset/evaluation boundary

`generator.py` constructs parent records first, then dependent facts and time-based outcomes.
`validation.py` checks structural/compound joins, enums, revisions, arithmetic, lifecycle, dispatch
policy and independent attribution expectations. `exports.py` creates CSV/JSON/SQL and challenge claims.
The detector reads input only; separate truth goes only to the evaluator. The four anomaly classes are
sent-after-opt-out, abandonment-after-payment, double order credit and stale cart total.

Full and starter profiles share the generator. Canonical payload hashes and realized coverage/statistics
are exported. `scripts/check_full_import.py` tests representation equivalence against a temporary
PostgreSQL schema. No validation or evaluation figures are invented in the UI; it reads the generated
baseline reports and distinguishes them from live scenario state.

## Identity, history and access

Every core relation has immutable prefixed IDs, documented PK/FK relationships and a field dictionary.
Business and event tables reject update/delete. Mutable `outbox_job` is a queue projection with appended
transition events; `runtime_state` is operational clock/pause state. Migration 002 adds review, issue,
operation and receipt tables; migration 003 indexes settlement evidence. Application initialization is
idempotent and retains existing data. Schema changes use numbered migrations.

Manager, analyst and operator demo sessions use signed, expiring, HttpOnly/SameSite cookies. Analyst and
operator access is read-only. The default demo password is configurable; server-generated session
secrets invalidate sessions on restart unless SESSION_SECRET is configured. All demo roles share the
configured local password. This is a loopback synthetic-store environment, not multi-tenant production
authentication. A public deployment would need individual identities, HTTPS, credential management,
rate limits, provider integration and operational hardening.

## Technical references

- [FastAPI](https://fastapi.tiangolo.com/) for HTTP validation, responses and static serving.
- [PostgreSQL row locking](https://www.postgresql.org/docs/16/explicit-locking.html) and
  [constraints](https://www.postgresql.org/docs/16/ddl-constraints.html) for transaction/storage guarantees.

No real external email/SMS, payment, warehouse or storefront integration is configured. Synthetic
attribution measures credited recovery, not a causal sales effect.
