# Versioned domain rules

These are product defaults for a synthetic demonstration, not a claim of jurisdiction-specific
compliance. `config/policy.json` and `rules.Policy` define `recovery-v1`. Changes to live rules
require a new version, historical configuration retention, and replay verification.

## Time and identity

- All timestamps are aware UTC instants. Customer-local quiet hours use IANA timezone names.
- `occurred_at` / `effective_at` describe business time; `recorded_at` describes system knowledge.
  For replay at T, use only records whose business and recorded time are <= T.
- Customer IDs join sessions across devices using a known customer account; do not infer
  identity by similar email addresses. Guest carts without a resolved customer are rejected
  into a labelled ingest issue before recovery enrollment.
- Rule functions receive one customer's validated history. Repository methods enforce that
  scope and join to customer-owned carts. The pure functions do not perform database joins.
- Text IDs are immutable. Prefix year 2026 is fixed for this brief; other years require an
  explicit naming/schema version. Counters are at least six digits and never recycled.

## Cart facts and abandonment

CartLine holds identity; CartLineEvent holds absolute quantity and unit price at each revision.
Quantity zero removes a line without deleting it. The line amount is quantity * unit price
in integer INR paise. Cart amount is the sum of latest line revisions at that event time.
This demo excludes tax, shipping, discounts and currency conversion, so reconciliation is exact.
OrderLine captures the purchased values and does not change if a cart is later edited.

Qualifying activity is cart creation, a genuine line change or checkout start. A page view,
delivery/open/click, scanner event, or duplicate source update does not reset inactivity.
Last activity is calculated across all linked sessions/devices. Sort revisions deterministically;
require strictly increasing revision numbers and non-decreasing business times per aggregate.

A cart qualifies at T when it has positive quantity/value, has no successful paid order at or
before T, and inactivity is **at least 60 minutes and less than 14 days**. At exactly 60 minutes
it qualifies; at exactly 14 days it expires. The detector emits one `abandoned` event per
episode. A real cart update reopens it, resets the timer and cancels pending dispatches from
the old episode. A purchase closes it immediately. A cart purchased after an earlier valid
abandonment still counts among the 20,000 ever-abandoned carts. Report current abandoned
state separately from ever-abandoned population; repeated scans never inflate either count.

## Consent and blocks

Consent is append-only by customer and channel, with source, effective time, recorded time,
and a monotonically increasing revision. No consent means no contact. At a dispatch instant,
select the latest effective consent known then. For equal effective timestamps withdrawal
wins; revision is the final tie-breaker. A future effective grant does not authorize now.
Late recorded withdrawal is enforced as soon as known and creates a retrospective exception
if its effective time predates a prior send. Keep that exception distinct from a known-opt-out
violation; the system cannot act on an unreceived event.

Email and SMS permissions are independent. A granted channel also needs a synthetic contact
identifier. Hard bounce, complaint, invalid address and manual suppression block that channel
until an explicit clear event. Do not use consent as a proxy for contact deliverability.

Recheck at enrollment and at every dispatch/retry. A withdrawal cancels queued dispatches;
dispatch recheck covers any races or jobs already claimed. Store consent event ID and all
cap/reservation IDs in the audit evidence. Use the same customer lock for withdrawals,
cart/order changes and dispatch. Current code implements the pure decision, not these writes.

## Frequency, quiet hours and scheduling

- Email: at most 1 accepted or reserved logical dispatch in a rolling 24-hour interval.
- SMS: at most 1 in a rolling 72-hour interval.
- Any channel: at most 3 in a rolling seven-day interval, across all carts and campaigns.
- Count `(T-window, T]`. A send at the lower boundary has aged out. Deduplicate a dispatch's
  reservation and acceptance; count retries once, and exclude its own reservation at recheck.
- Known failed, permanently rejected provider calls release a reservation; unknown acceptance
  holds capacity until reconciled. Opens/deliveries do not consume extra capacity.
- Both channels are quiet from local 21:00 inclusive until 09:00 exclusive. Schedule using the
  customer's zone at the due instant; timezone validation and DST-aware next-allowed time are
  service responsibilities. A queued message must pass all rules again at its deferred time.

Touch 1 selects email or SMS at last activity + 60 minutes using the configured channel mix,
only with that channel's independent eligibility. Starter and full require accepted sends and
consent/cap boundary coverage for both channels. Optional touch 2 uses the other permitted
channel at +24 hours for an unrecovered, still-inactive cart; it is outside baseline
generation's one-attempt-per-campaign quota and runs in extended scenarios.
Variant A is a concise reminder; B highlights the saved items. No discounts are invented.
Choose A/B with SHA-256 of seed and customer ID, consistently across devices. Template IDs
are immutable personalized snapshots `MSG-<cart-id>-01`, `-02`, etc.; version copy separately.

Evaluation records every failing reason in stable order. Dispatch service maps quiet/cap
failures to deferral if a valid future slot exists, otherwise suppression. Once purchased,
expired, blocked or without consent, a dispatch does not automatically resume; a later valid
cart episode requires fresh enrollment. No forced sends are used to meet volume quotas.

## Attribution

1. Require a paid, non-cancelled order and a valid provider-accepted send. In this demo
   `Order.ordered_at` is exactly the successful paid event's occurrence time; uncompleted
   checkout is cart activity, not an Order. Use that same payment instant for suppression
   and the attribution purchase time.
2. Match the order's customer and exact cart; cross-device sessions may share that identity.
3. Consider unique click events in `[ordered_at - 7 days, ordered_at)`. Delivery and open are
   diagnostics, not attribution touches. Filter callbacks that predate acceptance.
4. Pick max `(clicked_at, event_id, send_id)` using a documented lexical ordering.
5. Create one Attribution row for the order; SQL `UNIQUE(order_id)` prevents double credit.
6. Credit order-line-derived paid amount. Refunds reduce net credited revenue through order
   events; they do not erase or multiply the original order credit.

An order more than seven days after its final click is late/unattributed. An abandoned cart
may be purchased organically with no campaign or click. Generate these outcomes from events,
then derive labels; never independently assign a "recovered" flag. Credited revenue is
observational attribution, not incremental revenue. A causal lift claim requires a separately
randomized holdout and a powered experiment; neither is a submission acceptance criterion.

## Lifecycle transition contracts

| Aggregate | Allowed sequence / branches |
| --- | --- |
| Cart | created -> updated/checkout_started -> abandoned -> reopened or purchased or expired |
| Cart reopen | reopened -> updated/checkout_started -> abandoned; purchased is terminal |
| Campaign | scheduled -> running -> completed; scheduled/running -> suppressed/cancelled |
| Dispatch | pending -> leased -> done; leased -> retry -> leased; any live -> cancelled/dead |
| Send | submitted -> delivered -> opened/clicked; submitted -> failed; local -> suppressed/unknown |
| Order | paid -> refunded (partial/full); pre-payment cancellation prevents recovery credit |

Cart updates may repeat and checkout can purchase directly without abandonment. Receipt order
is not business order: click may arrive before delivery callback; validate occurrence times
and required accepted send, not arrival order. Opens are optional; a click need not have an
open. Repeated opens/clicks are permitted as separate genuine events; duplicate callback IDs
are not. SMS does not produce opens. Invalid transitions are quarantined with specific issues.

## Exceptions

`SEND_AFTER_OPT_OUT`, `ABANDONED_AFTER_PURCHASE`, `DOUBLE_ATTRIBUTION`, and
`STALE_CART_TOTAL` are detector findings. Each finding identifies the offending event/row,
expected result, actual result and supporting record IDs. A malicious or bad upstream claim
does not become an accepted business record merely because a challenge fixture contains it.
Challenge input is untrusted; expected anomaly labels live only in the separate truth export.
