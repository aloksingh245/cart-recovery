# Implemented synthetic data pipeline

## Commands and volumes

```bash
uv run recovery generate --profile starter --seed 20261022 --out data/new-starter
uv run recovery generate --profile full --seed 20261022 --out data/new-full
uv run recovery validate --input data/new-full
uv run recovery evaluate --input data/new-full
uv run recovery reproducibility --profile full --out artifacts/new-repro
```

Output directories must be empty. Starter and full use the same generator. Full produces 17,500
customers, 50,000 carts, exactly 20,000 unique ever-abandoned carts, 10,000 per-cart campaign instances
and 10,000 initial evaluated send attempts. Starter produces 350 / 1,000 / 400 / 200 / 200.
Suppressed evaluations and known provider failures remain attempts; accepted sends are a separate count.
Retries and manual scenarios append additional rows to live state without changing the baseline exports.

`--scale` scales integer profile counts and records profile `custom`; retain at least 100 campaigns
for five examples of each anomaly. Invalid target combinations fail before export. Both standard
profiles use the requested seed 20261022. No wall-clock value, external API or Python salted hash enters
generation. SHA-256 binds configuration and code to the run; customer SHA-256 assigns a stable A/B variant.

## Dependency and scenario construction

The generator creates DatasetRun, Customer and effective Consent records first. It then creates
Session/Cart/CartSession identities, CartLine and immutable line revisions, and matching CartEvent totals.
Cart IDs are assigned in numeric order; child counters are deterministic. Contacts use synthetic
`example.test` email and non-dialable SMS tokens. No public dataset or real personal data is used.

The first campaign cohort has one cart per customer. A second abandoned cart for each of those
customers exercises cross-cart caps and missing alternate-channel consent. Other carts are direct
checkouts or recently active at the observation cutoff. This constrained construction achieves exact
volumes through legitimate facts rather than forcing prohibited sends. Half of abandoned carts are
scheduled campaign instances; non-enrolled carts keep suppression evidence.

Baskets draw 1..8 lines with a skew toward 1..3 and clipped lognormal unit prices. Quantities mostly
fall in 1..3. Every seventh cart has an explicit quantity update, recomputed total and reset inactivity;
every sixth has a second device session. Activity is clustered in a safe daytime band so baseline sends
can exercise both channels. These are synthetic assumptions, not measured industry distributions.
Configuration records planning distribution targets; validation reports realized coverage and value
quantiles. The generator's actual weights and scenario schedules are explicit in `generator.py`.

A cart is abandoned only after 60 minutes of genuine activity inactivity and before a successful
payment. Campaign enrollment schedules one first touch; 80% use email and 20% SMS, with independent
permissions. Every seventeenth campaign customer withdraws before dispatch; every twenty-ninth attempt
has a known simulated provider failure. Delivery is conditional on acceptance; email opens are optional;
SMS has none. Clicks precede purchases. Ordinary clicked purchase delays are two hours; selected paths
purchase eight days later and therefore receive no credit. Organic purchases also occur without clicks.

Order lines snapshot quantities and unit prices at payment. Order totals and payment amounts derive
from lines. A controlled paid-order cohort receives partial refunds. Attribution uses the production
last-click function; an independently written oracle validates its selected click for every order.
Recovered, late, organic and current-cart outcomes derive from these histories, never from independent
random outcome labels. Generated timestamps cover October 2026 with a 2026-11-01 observation cutoff.

## Valid baseline, separate challenge and truth

The baseline is validated before export. The challenge builder then creates 20 bad claims and benign
lookalikes with valid referenced parents:

- `SEND_AFTER_OPT_OUT`: claimed acceptance after a known effective withdrawal.
- `ABANDONED_AFTER_PURCHASE`: claimed abandonment after paid checkout.
- `DOUBLE_ATTRIBUTION`: a second claimed campaign/send credit for an already-credited order.
- `STALE_CART_TOTAL`: a claimed snapshot retains the amount before a quantity revision.

A claim contains `claim_id`, `claim_type`, `entity_id`, occurrence/recording times and payload. It contains
no issue label, expected outcome or scenario name. Bad claims never enter canonical SQL facts. Ground
truth is stored separately. Detection reads only input tables/claims; evaluation receives findings and
truth afterward, comparing `(issue_type, offending_record_id)` and reporting class TP/FP/FN and precision/
recall. Ordinary expected order-credit decisions come from the independent oracle in `decisions.json`.

## Export layout and reproducibility

```text
data/full/
  input/baseline/csv/<table>.csv
  input/baseline/json/<table>.json
  input/baseline/seed.sql
  input/challenge/claims.jsonl
  ground_truth/anomalies.csv
  ground_truth/ground_truth.json
  ground_truth/decisions.json
  metadata/schema.sql
  metadata/data-dictionary.csv
  metadata/generation-config.json
  metadata/policy.json
  metadata/source-manifest.json
  metadata/run.json
  metadata/validation-summary.json
  metadata/evaluation.json
  metadata/findings.json
  metadata/checksums.json
  metadata/README.md
```

Rows sort by primary key; columns use schema order. JSON uses stable key ordering; CSV uses UTF-8/LF,
blank for null and integer money; SQL uses explicit columns, escaped literals, dependency order and
500-row statement batches. All instants use UTC `Z`. Empty business strings are disallowed.

Two independent full runs compare all 63 canonical payload hashes and every table count. The checksums
file does not include itself; verification timing and reproducibility receipts live outside the payload.
`scripts/check_full_import.py` compares CSV/JSON facts and SQL-imported rows in a unique temporary schema.
The shareable ZIP includes one full dataset, one starter dataset and the two-run report rather than two
redundant 300MB directories. Source provenance and license treatment are in `docs/source-manifest.json`.
