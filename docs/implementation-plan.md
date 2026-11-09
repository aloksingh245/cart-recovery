# Delivered implementation and handoff map

The original architecture scaffold has been implemented as a working local synthetic-store application.
The seven milestones below map the finished code to verification. This is a delivery map, not a claim
that public publishing, human review or real-provider integration has occurred.

## Milestone 1 - Data/storage contracts

Implemented immutable core tables, field dictionary, PK/FK/composite constraints, PostgreSQL initialization
and numbered runtime migrations. Pure rules define abandonment, consent/caps, variant assignment and
one-order attribution. SQL/schema and boundary tests exercise these contracts.

## Milestone 2 - Generator and evaluation

Implemented shared starter/full generation, exact baseline quotas, source-derived line/order totals,
channel events, recovered/organic/late orders, four isolated anomaly claims and separate truth.
CSV/JSON/SQL, manifests, validation/evaluation and two-run checksum commands are executable.

## Milestone 3 - Persistence and scanning

Implemented validated bulk import, persistent customer/cart/event histories, cart projections,
time-based scanning, traceable suppression/enrollment and idempotent campaign episodes. Quantity
updates reopen carts and reset activity across devices. API writes and source receipts commit together.

## Milestone 4 - Coordinated recovery

Implemented customer-serialized worker transactions, rechecked consent/purchase/caps/quiet hours,
withdrawal and purchase cancellation, pause/cancel controls, callbacks and a real retry path inside
the simulated provider. Concurrent-worker tests verify contact limits. The implemented atomic simulator
simplifies the initial proposed lease/reservation design; real network-provider coordination remains
an explicitly separate extension.

## Milestone 5 - Orders, attribution and metrics

Implemented paid order snapshots, 24-hour settlement, seven-day deterministic last click, unique
credit, partial refunds and reconciled channel/variant metrics. Detector/evaluator evidence records
all required anomaly classes and benign controls. Known-time consent is covered by policy tests;
arbitrary backdated external callback integration is outside the current simulator.

## Milestone 6 - Operations console

Implemented responsive overview, queue/filter/pagination, cart trace and actions, campaigns,
exception review, data-quality downloads and a scenario studio. Signed demo sessions enforce manager
writes and read-only analyst/operator access. Browser verification covers normal and suppressed recovery,
and narrow-screen navigation/account access. Review feedback fixed stale asynchronous route commits and
keyboard/navigation orientation.

## Milestone 7 - Verification and shareable release

Locked dependencies, Docker/Compose startup, fresh-database HTTP smoke, full-data validation,
CSV/JSON/SQL round-trip, reproducibility receipts and a verified archive support a friend running the
project. README documents startup, password, demo journey, regeneration and limitations.
The owner's public GitHub destination, complete AI-session transcript and personal review remain
candidate-submission responsibilities. No submission timestamps or human work have been invented.
