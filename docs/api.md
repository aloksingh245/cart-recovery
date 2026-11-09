# Implemented API

Open `/docs` for the generated request/response schema and `/openapi.json` for the complete contract.
This application uses `/api/*` routes. Historical `/v1/*` proposals have been superseded.

## Access and mutation contract

`POST /api/login` accepts `{username: manager|analyst|operator, password: ...}` and sets a signed,
HttpOnly, SameSite=Strict session cookie valid for eight hours. Default local password is `recovery-demo`.
`GET /api/me` returns the role; `POST /api/logout` clears the cookie. All data reads require a session;
all business writes require manager access.

Every business write requires `Content-Type: application/json`, `X-Recovery-Request: 1` and an
`Idempotency-Key` of at most 160 characters. Retrying the same key/payload returns the original response;
a changed payload returns 409. Source effects and the receipt commit together. Cross-origin writes are
denied. Unknown request fields, invalid enums, negative amounts/clock changes and naive business inputs
are rejected. IDs remain text, times are UTC ISO-8601, money is integer INR paise.

## Reads

- `GET /healthz`: liveness and explicit simulated-delivery mode.
- `GET /readyz`: database/runtime-schema readiness; 503 if unavailable or DATABASE_URL is unset.
- `GET /api/policy`: versioned policy (public).
- `GET /api/metrics`: counts, observed funnel, settlement, channel/variant totals and reconciliation.
- `GET /api/carts?search=&state=&page=1`: filtered, 30-row pages ordered by immutable cart ID.
- `GET /api/carts/{cart_id}`: customer, consent, devices, lines, events, decisions, sends, order and credit.
- `GET /api/campaigns?page=1`: 30-row campaign/job pages.
- `GET /api/issues`: anomaly evidence and appended review status.
- `GET /api/quality`: generated baseline validation/evaluation/run reports.
- `GET /api/downloads/{name}`: validation-summary, evaluation, checksums, findings or run JSON.

## Manager writes

- `POST /api/scenarios`: `{kind: recovery|withdrawal|retry|multidevice, channel: email|sms}`.
- `POST /api/scan`: `{}` scans up to 200 candidates and records enrollment/suppression decisions.
- `POST /api/worker`: `{}` processes up to 30 due jobs; the background CLI worker runs continuously.
- `POST /api/clock`: `{minutes: 1..20160}` advances simulated time; cannot move backwards.
- `POST /api/settle`: `{}` settles paid orders at least 24 hours old.
- `POST /api/pause`: `{paused: true|false}` records pause/resume.
- `POST /api/campaigns/{id}/cancel`: `{}` cancels this campaign's pending cart dispatches.
- `POST /api/customers/{id}/consent`: `{channel, state: granted|withdrawn}` appends an effective change now.
- `POST /api/carts/{id}/quantity`: `{line_id, quantity: 0..100}` appends a revision and recomputes totals.
- `POST /api/carts/{id}/enroll?channel=email`: `{}` evaluates/reuses or creates a cart episode.
- `POST /api/sends/{id}/events`: `{kind: delivered|opened|clicked}` records a simulated callback now.
- `POST /api/carts/{id}/purchase`: `{}` creates the paid order and cancels pending cart recovery.
- `POST /api/orders/{id}/refund`: `{amount_minor: positive integer}` appends a refund within paid balance.
- `POST /api/issues/{id}/reviews`: `{note: 3..1000 characters}` appends a manager review.

The scenario studio simulates customer/store actions through these protected APIs. Bulk master/event
intake is the validated CLI `import-data`; no unauthenticated customer or arbitrary provider webhook is
exposed. Callback delivery is a simulator action, not an externally signed production webhook.

401 means sign-in required; 403 means role/request protection failure; 404 means missing resource;
409 means business/idempotency conflict; 422 means request validation failure; 503 means database failure.
Errors return a readable `detail` or `error` message, without exposing database credentials or SQL.
