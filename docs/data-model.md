# Data model and relationships

`db/catalog.py` is authoritative. `scripts/build_schema.py` renders
`db/001_initial.sql` and `docs/data-dictionary.csv`; `--check` fails on drift.
The CSV documents every field's type, required/optional status, allowed values, units,
uniqueness, foreign key, validation rule, SQL checks and compound table constraints.
Run its SQL migration against PostgreSQL, not SQLite.

## Core entity mapping

| Business entity | SQL relation | Primary key | Grain |
| --- | --- | --- | --- |
| Customer | customer | customer_id | one synthetic customer |
| Consent | consent | consent_id | one effective channel permission change |
| Session | session | session_id | one device visit |
| Cart | cart | cart_id | one checkout intent |
| CartLine | cart_line | cart_line_id | one SKU identity within a cart |
| Campaign | campaign | campaign_id | one cart's recovery episode |
| MessageTemplate | message_template | template_id | one immutable personalized copy version |
| SendAttempt | send_attempt | send_id | one evaluated dispatch attempt, possibly suppressed |
| Order | recovery_order | order_id | one purchase of a cart |
| Attribution | attribution | attribution_id | one credited order and winning click |

Campaign means a **per-cart campaign instance**, not a marketing program definition. This
lets the requested full profile contain 10,000 campaign IDs. Program name/version can later
be normalized separately. MessageTemplate follows the requested per-cart MSG naming; shared
copy blueprints belong to versioned generation configuration rather than these personalized rows.

## Cardinality and optionality

- DatasetRun 1:N Customer. A customer belongs to exactly one immutable generation run.
- Customer 1:N Consent, Session and Cart. A customer may have no consent for a channel;
  absence is denied. One channel may have many effective records over time.
- Cart N:M Session through CartSession. Both ends are required; the bridge verifies the same
  customer using composite foreign keys. A cart can be resumed on a second device.
- Cart 1:N CartLine. A temporarily empty cart may have zero lines; a removed line retains
  its identity and quantity-zero event. CartLine 1:N CartLineEvent; Cart 1:N CartEvent.
- Cart 1:N Campaign across reopened episodes; `(cart_id, episode)` is unique.
  Every campaign has one customer, one cart and one customer-stable variant.
- Campaign N:M MessageTemplate through CampaignMessage. Its `dispatch_id` identifies the
  logical message; its touch number is unique per campaign. Composite FKs prevent cart mixing.
- CampaignMessage 1:N SendAttempt; zero attempts until dispatch. Attempt numbers are unique
  within dispatch. Retries get new SEND IDs and retain the logical idempotency key.
- CampaignMessage 1:0..1 SendAcceptance. A unique dispatch receipt credits exactly one
  accepted attempt; rejected/unknown attempts cannot acquire an independent receipt.
- SendAttempt 1:N SendEvent. An accepted send may have zero delivery/open/click receipts.
  Event ID and provider event key are unique. Null provider event keys are allowed locally.
- Cart 1:0..1 Order. Customer 1:N Order. Checkout-source idempotency prevents a second order
  from a retry. Multi-order carts/split fulfillment are outside this version.
- Order 1:N OrderLine and OrderEvent. Each line links to its original CartLine. Cross-cart
  order lines are checked by the ingestion validator/service; a simple FK alone is insufficient.
- Order 1:0..1 Attribution. Each attribution requires one accepted SendAttempt and one of
  that send's click events. One send may have no attribution. Because this model has one
  order per cart, a same-cart send cannot earn multiple orders.
- Cart 1:N DecisionLog. Dispatch linkage is optional for decisions made before enrollment.
- Customer 1:N ContactBlockEvent. Channel-specific block/clear effective history is retained.
- CampaignMessage 1:0..1 OutboxJob. OutboxJob 1:N OutboxEvent. Only the job's operational
  projection can be updated; mutation of any business/event relation is rejected by triggers.

## Effective dating and lifecycle

Consent and block events have effective and recorded timestamps. Their effective interval
is derived as `[effective_at, next_effective_at)` using the version/tie ordering in
`domain-rules.md`; the last interval is open-ended. No old record's end time is overwritten.
Business events retain both business and arrival times. Current lifecycle state is a query
over valid events, not an independently generated status column.

MessageTemplate is immutable; changed copy creates another version and ID. Configuration and
manifest hashes bind facts to generation and policy versions. Existing SQL represents the
initial migration; once real data exists, changes require a new numbered migration instead
of rewriting the applied initial file.

## Database guarantees versus service checks

SQL guarantees PK/FK integrity, enum/range checks, immutable history, unique attribution per
order, one receipt per dispatch, key compound ownership relations and callback deduplication.
The implemented service/validator additionally enforces IANA zones, contact availability, date order
across relations, exact line/total arithmetic, revision transitions, same-cart order lines,
click type/eligibility, and order/consent timing. The core SQL migration supplies storage constraints; application services and validation implement
these business checks. Runtime migration 002 adds operational tables, and migration 003 indexes settlement.

Keep `issue_type`, expected decisions and outcome labels out of all production model tables.
Raw challenge claims and their finding/ground-truth files use the separate export format in
`generation.md`. Public seed data only contains synthetic values.
