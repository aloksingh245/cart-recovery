"""Compose the locally stored visual plan from checked-in source contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(tag, identifier, **props):
    attrs = " ".join(f"{key}={{{json.dumps(value)}}}" for key, value in props.items())
    return f'<{tag} id="{identifier}" {attrs} />\n'


diagram = """<div class="layers">
<section class="diagram-panel" data-rough><h3>Inputs and people</h3>
<div class="diagram-node">Synthetic customer actions</div>
<div class="diagram-node">Operator / Analyst / Manager console</div>
<p class="diagram-muted">Source actions and read/review commands enter through authenticated APIs.</p></section>
<section class="diagram-panel" data-rough><h3>One application</h3>
<div class="diagram-card">FastAPI + server-rendered console</div>
<div class="diagram-card">Cart / Consent / Campaign / Order services</div>
<div class="diagram-card">Pure versioned policy + deterministic attribution</div>
<p class="diagram-muted">Verified customer identity spans devices; customer locks serialize contact decisions.</p></section>
<section class="diagram-panel" data-rough><h3>Durable execution</h3>
<div class="diagram-node">PostgreSQL facts, history and audit decisions</div>
<div class="diagram-node">Outbox worker + simulated email/SMS</div>
<div class="diagram-node">Callbacks, payments, settlement and metrics</div>
<p class="diagram-muted">Append history; retain stable dispatch keys, receipts and one order credit.</p></section>
</div><div class="diagram-box"><strong>Offline evaluation boundary</strong>
<p>Seeded generator → baseline facts and isolated challenge claims → detector findings.</p>
<p>Separate ground truth → evaluator only. Canonical CSV / JSON / SQL exports carry checksums.</p></div>"""
css = ".layers{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}.diagram-panel{padding:16px}.diagram-node,.diagram-card{padding:12px;margin-block:10px}.diagram-box{margin-top:16px;padding:16px}"

entities = []
for name, pk, fks in [
    ("Customer", "customer_id", []),
    ("Consent", "consent_id", [("customer_id", "Customer.customer_id")]),
    ("Session", "session_id", [("customer_id", "Customer.customer_id")]),
    ("Cart", "cart_id", [("customer_id", "Customer.customer_id")]),
    ("CartSession", "cart_session_id", [("cart_id", "Cart.cart_id"), ("session_id", "Session.session_id")]),
    ("CartLine", "cart_line_id", [("cart_id", "Cart.cart_id")]),
    ("Campaign", "campaign_id", [("cart_id", "Cart.cart_id")]),
    ("MessageTemplate", "template_id", [("cart_id", "Cart.cart_id")]),
    ("CampaignMessage", "dispatch_id", [("campaign_id", "Campaign.campaign_id"), ("template_id", "MessageTemplate.template_id")]),
    ("SendAttempt", "send_id", [("dispatch_id", "CampaignMessage.dispatch_id")]),
    ("Order", "order_id", [("cart_id", "Cart.cart_id")]),
    ("Attribution", "attribution_id", [("order_id", "Order.order_id"), ("send_id", "SendAttempt.send_id")]),
]:
    entities.append(dict(id=name, name=name, fields=[dict(name=pk, type="text", pk=True)] +
                         [dict(name=field, type="text", fk=target) for field, target in fks]))

relations = [{"from": f["fk"].split(".")[0], "to": e["id"],
              "kind": "1-1" if (f["fk"], e["id"]) in
              (("Cart.cart_id", "Order"), ("Order.order_id", "Attribution")) else "1-n"}
             for e in entities for f in e["fields"] if "fk" in f]

overview = """---
title: "Cart Recovery: architecture and implementation"
brief: "Consent-aware recovery, reproducible synthetic data and one-order conversion attribution."
kind: "plan"
localOnly: true
---

Build a working synthetic recovery application that explains every contact decision and
reconciles every credited order. A customer leaves a cart at 10:00; at 11:00 it may qualify
for recovery. Consent withdrawal before dispatch prevents the message. A permitted message's
click can earn the same cart's purchase once within seven days. Operators can inspect the
source events, suppression reasons and winning attribution.

The local application implements generation, validation, persistent recovery services, a simulated worker,
attribution, metrics and the responsive operations console. The milestones below map the delivered code
to verification evidence. Real provider integration and public production deployment are separate extensions. The latest
downloaded candidate guideline adds runnable code, a public repository, real timestamps
within a 72-hour window, prompt history and honest AI disclosure. The deadline start is unknown.

## Architecture and runtime boundaries

Choose one Python/FastAPI application, PostgreSQL 16 and a worker from the same codebase.
The operations console uses server-rendered HTML. Keep email and SMS simulated so the demo
is deterministic and cannot contact real customers. Customer/account identity spans devices;
permissions and frequency caps are independent by channel and shared across all customer carts.

"""

text = overview + ('<Diagram id="system-boundaries" frame="hide" '
                   'caption="Runtime layers and the separate evaluation boundary.">\n\n'
                   '```html\n' + diagram + '\n```\n\n```css\n' + css + '\n```\n\n</Diagram>\n')
text += """
The implemented simulator worker locks the customer first, then the pending job, and rechecks live
consent, purchase, inactivity, blocks, quiet hours and cap reservations. The simulated provider
acceptance commits with the audit decision and job completion. An uncertain future real-provider
acceptance needs idempotent reconciliation; a DB transaction cannot atomically control a third party.

Consent and business events retain effective/occurrence and recorded time. Facts are immutable;
job state is an operational projection with append-only transition history. Unique receipts stop
duplicate dispatch credit; unique order attribution stops campaign double counting. Technical
FKs do not replace service checks for lifecycle, time, totals or semantic eligibility.

Runtime role checks protect source and manager writes. No production data, credentials or real
provider calls enter this submission. Viewer access is read-only. Large data exports stay out
of git; publish only to a destination the user explicitly chooses.

## Entity and identity contracts

The diagram shows entity identities and joins, not every field. The generated
`docs/data-dictionary.csv` contains all columns, types, optionality, enums, units, uniqueness,
checks and FK contracts. Immutable event relations add effective dating and lifecycle history.
Campaign is one cart's recovery episode; MessageTemplate is an immutable personalized snapshot.
Cart/Session and Campaign/MessageTemplate use bridges. A cart has at most one order and an order
at most one credit. Text IDs follow CUS / CART-2026 / CMP-2026 / MSG-cart / SEND-2026 / ORD-2026.

"""
text += block("DataModel", "entity-identities", entities=entities, relations=relations)
text += """
## Business decisions

- Abandonment begins at 60 minutes of genuine inactivity across devices, and expires at 14
  days. Paid, empty or expired carts cannot qualify. Reopening begins a fresh episode;
  repeated scans cannot duplicate episodes. Report ever-abandoned and current state separately.
- Consent is known-effective at dispatch. Missing consent denies contact; equal-time withdrawal
  wins. Keep channel-specific block history and evidence references. Recheck after scheduling.
- Caps count accepted logical dispatches under the customer lock: email 1/24h, SMS 1/72h, all channels
  3/7d, using `(T-window, T]`. Retries/callbacks must not multiply contact counts.
- Both channels are quiet 21:00-09:00 in the customer's zone. Defer valid jobs to the next
  permitted time and recheck everything; permanent disqualifiers suppress/cancel.
- Stable SHA-256 customer assignment chooses A/B. No invented discounts. The baseline uses
  one initial email or SMS touch (80/20 target), with both channels represented; extended
  retry/two-touch scenarios report separate added row counts. Cancellations of unattempted
  baseline jobs append a first suppressed attempt, preserving the exact audit/count contract.
- Order time is successful payment time. Credit the latest valid click for the same customer
  and exact cart in `[purchase-7d, purchase)`.
  Break ties by event ID then send ID. Opens/deliveries earn no credit. Runtime settles after
  a 24h simulated-ingestion delay. Arbitrary backdated external ingestion is a separate adapter extension.
- Integer INR paise and source-derived line snapshots determine cart/order/revenue totals.
  Refund events reduce net credit. Observational attribution is not a causal-lift claim.

## Generation and truth isolation

Use seed 20261022 and the same parameterized pipeline for starter/full. Full creates 50,000 carts,
20,000 unique ever-abandoned carts, 10,000 per-cart campaign instances and 10,000 evaluated
SendAttempt rows. Accepted sends are separately reported and may be fewer. Starter uses
1,000 / 400 / 200 / 200. Generate parents, dependent facts and time-ordered recovery decisions,
then outcomes from those events. Never independently randomize outcome labels or bypass rules
to hit quotas. Reject infeasible configurations clearly.

Generate a valid baseline first. Then add isolated challenge claims for sent-after-opt-out,
abandoned-after-purchase, double attribution and stale cart totals. Challenge parents stay valid;
bad claims do not enter accepted production facts. Expected decisions and issue labels live
only in separate truth files. Detection cannot read truth; evaluation compares findings afterward.
Use an independently written reference oracle rather than copying production outputs as labels.

Export canonical CSV, JSON and dependency-ordered SQL plus README, schema, dictionary, policy,
configuration, provenance, validation report and SHA-256 manifest. Generate twice into separate
directories and compare every payload count/checksum. Report realized distributions and
normal/boundary/failure coverage. Exclude volatile runtime receipts from deterministic hashes.

## Implementation files worth reviewing

"""
code = (ROOT / "src/cart_recovery/rules.py").read_text()
start = code.index("def evaluate(")
end = code.index("    aware(now)", start)
snippet = code[start:end] + "    # Service validates ownership and supplies a customer-locked history.\n"
text += block("AnnotatedCode", "policy-boundary", filename="src/cart_recovery/rules.py", language="python",
              code=snippet, annotations=[dict(lines="1-5", label="Explicit decision inputs",
                  note="No wall clock, DB calls or hidden labels; all customer history is supplied by the service.")])
text += """
`db/catalog.py` renders the SQL and dictionary together. `config/policy.json` freezes policy;
`config/generation.json` freezes cohort targets. `api.py` exposes the authenticated operations APIs and serves the console.
The ordered milestones identify each new service, integration test and UI surface.

"""
implementation = (ROOT / "docs/implementation-plan.md").read_text()
text += implementation[implementation.index("## Milestone 1"):]
text += """

## Verification and handoff

Run foundation tests against PostgreSQL, then exercise a fresh-database starter workflow through
the actual console: generate/import, abandon, inspect consent, dispatch/deliver/click, purchase,
inspect single attribution and reconciled metrics. Repeat with opt-out before dispatch and
with two concurrent workers spending one customer's cap. Run all four anomaly claims and
benign controls through detection/evaluation. Re-import CSV/JSON/SQL and compare facts.

Final reports include PK/FK/temporal/lifecycle/arithmetic validation, per-class precision/recall,
expected decision agreement, realized distributions, exact volumes and two full checksum runs.
Orders reconcile as credited + late + organic; winning-channel/variant revenue reconciles to
the overall total. Show cohort cutoffs, censored counts and null denominators. Keep prompt
history and genuine timestamps, and distinguish AI-authored work from personal review.

All meaningful architecture choices have recommended defaults above. The organizer's deadline
and the user's public-repository destination are submission inputs, not blockers for local
implementation. Actual verification receipts and the completed dataset are included in the shareable release.
"""
(ROOT / "plans/cart-recovery/plan.mdx").write_text(text)
print("wrote plans/cart-recovery/plan.mdx")
