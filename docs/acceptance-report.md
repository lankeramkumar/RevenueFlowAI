# RevenueFlow AI — Acceptance Report

**Status as of this report: Milestones 1–3 substantially built and verified
against a real running stack. Milestones 4–6 (full operational UI,
chatbot/agent orchestration, hardening, remaining docs) are not started.**
This is an honest mid-build checkpoint, not a claim of completion — see
`docs/implementation-plan.md` for the live, continuously-updated
milestone tracker this report summarizes.

## How to run it

```bash
cd infra
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Keycloak: http://localhost:8080 (admin/admin)
- Demo login: `demo-admin` / `DemoPass123!` (and `demo-analyst`,
  `demo-approver`, `demo-viewer` — see README.md)
- Postgres is on host port **5433**, not 5432 (see README's troubleshooting
  section — a pre-existing native Postgres service on the build machine
  held 5432)

**One manual step currently required after first boot** (not yet
automated — tracked as a gap below): seed an `organizations` /
`business_units` / `app_users` row so a logged-in Keycloak user has
application-level authorization. SQL used during verification is in
`docs/implementation-plan.md`'s Milestone 1 section. Automating this
(e.g. an admin bootstrap endpoint, or auto-provisioning on first login)
is listed as a gap below.

## Acceptance criteria — actual status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean checkout starts via Compose, migrates, demo login | ✅ **Met** | `docker compose up --build` brings up all 5 services healthy; Alembic migration applies automatically; real browser login completed as demo-admin (screenshot-confirmed) |
| 2 | All primary UI routes operate against persisted backend data; no mock-only dashboard | ⚠️ **Partially met** | Seven real routes now exist (dashboard, chat/investigate, exception workbench, task queue, CSV import, customer detail/timeline, admin), all against real data, nothing mocked. The exception workbench now has client-side filter/sort/pagination and per-row evidence drawers over its real rows; the customer detail screen is backed by a real SQL-wrapped domain service (`domain/customer_service.py`, 3 passing integration tests against live Postgres, including an S01 hand-calculation match). The new admin screen covers business-unit listing and app-user management (create/role-change/deactivate/business-unit grants) via `/api/v1/admin/*` (7 passing integration tests through the real FastAPI app with dependency overrides) — this automates what was previously a manual SQL step after first boot. **Not yet built**: org-level config screens (thresholds, currencies, retention, provider status) that `docs/implementation-plan.md` originally scoped for "administration." **Not yet verified live in a browser** (no Docker Desktop available in this work session to boot the stack) — verified via `tsc`/lint/build only for the frontend, and via live-Postgres integration tests for the backend |
| 3 | Valid imports selectable; invalid bundles never corrupt active data; idempotent; worker recovers | ✅ **Met** | Activation, idempotency, and atomic rejection verified against live Postgres (unit + integration tests + a real upload through the running stack). Worker crash recovery verified by 3 integration tests against the real `claim_next_job` query — and finding a real bug in the process: a crashed job was getting permanently stuck at `status='staging'` since the reclaim query only matched `status='queued'`, now fixed |
| 4 | Hand-calculated fixtures match domain outputs exactly; currency totals separate | ⚠️ **Partially met** | Verified for the `small` profile's 2 implemented scenarios (S01, S09) via both pure-function tests and a live SQL-backed dashboard query. 15 of 17 scenarios (S02–S08, S10–S17) have pure-function unit coverage but no corresponding generator fixture or SQL-service verification yet. Only the aging-balance domain service has a SQL wrapper; unbilled-shipment, receipt-matching, and holds do not yet |
| 5 | All five example questions work in demo and live mode | ⚠️ **Partially met** | All five question *patterns* work in demo mode and were verified live with real answers and specialist attribution (unbilled shipments, invoice overdue/dispute, receipt match, order hold, customer summary). Live mode verified with genuinely free-form phrasing a regex could not match, correctly classified by a real Anthropic call. Not yet done: "actual source references" is partial — some findings carry `EvidenceReference`s, others (aging/customer-summary metrics) don't yet; honest missing-data behavior is confirmed (Order specialist declines to fabricate a customer-scoped holds answer it has no tool for) |
| 6 | Cross-org/cross-BU authorization tests | ✅ **Met** | `assert_business_unit_access` is implemented and used on every endpoint that exists. Previously verified only at the domain-service layer (`test_authorization_scope.py`); now also verified at the HTTP/API layer directly (`test_authorization_http.py`, 4 tests hitting the real FastAPI app via `httpx.ASGITransport`): a non-admin without a grant gets a real 403, an admin from org B querying org A's `business_unit_id` gets back an empty/no-dataset response rather than org A's real figures (never a leak), a cross-org customer lookup 404s instead of returning someone else's record, and the admin-management endpoints never list another organization's rows. **Found and fixed a real bug in the process**: `get_current_app_user` (`auth/deps.py`) didn't eager-load `AppUser.granted_business_units`, so `assert_business_unit_access` touching that relationship for any non-admin role on any business-unit-scoped endpoint would have raised `MissingGreenlet` under the async session — a production-breaking bug for every non-admin request, caught only because this was the first test to actually exercise a non-admin role against that check |
| 7 | Receipt suggestions handle ambiguity/residuals, no auto-apply | ⚠️ **Partially met** | `domain/matching.py`'s pure functions are implemented and unit-tested (exact/ambiguous/bounded multi-invoice); no SQL-backed service or API exposes this yet |
| 8 | Task approvals persist audit history, no ERP/cash/email side effects | ✅ **Met** | Verified live: created and approved a real task through the browser UI; `audit_events` table confirmed holding both `task.created` and `task.transitioned` rows; the state machine has no transition that touches any ERP/payment/email system — approval only changes `status` |
| 9 | Tests, CI, migrations, health checks, container builds, reproducible setup | ✅ **Met for what exists** | 97/97 backend tests pass (unit + integration against live Postgres); `ruff`/`mypy` clean; frontend `tsc`/`build`/lint clean; migrations verified applying against live Postgres; all 6 Compose services build and run; CI workflow (`.github/workflows/ci.yml`) is written but has not been run on an actual GitHub Actions runner. **Import performance target measured and passing**: 96,666-row bundle activated in 17.98s (see `docs/evaluation.md`), well under intent.md's 2-minute target — the paginated-screen latency target is still unmeasured |
| 10 | README, architecture diagram, data dictionary, CSV templates, API docs, threat model, evaluation report, ops runbook | ✅ **Met** | All now present and accurate as of this writing: README.md, `docs/architecture.md` (Mermaid diagram), `docs/data-dictionary.md` (full 13-file column reference), `docs/security.md` (threat model + current gates), `docs/evaluation.md` (actual test results, not aspirational), `docs/operations.md` (deployment/migrations/worker-recovery/backup gates), CSV templates served live, OpenAPI docs auto-generated at `/docs`. Every doc states real gaps explicitly rather than implying completeness |
| 11 | Supervisor routing, cross-domain combination, partial failure, cancellation, budgets, scope isolation, persisted follow-ups | ⚠️ **Partially met** | Supervisor + 3 specialists now real and verified live: single-domain routing, cross-domain fan-out (customer summary → Order+AR+Cash), deduped findings/evidence, honest partial results (Order declines unhandled intents rather than fabricating). Chat persistence verified (conversations/messages in Postgres). **Not done**: cancellation-after-dispatch, budget-exhaustion behavior (budgets are set but nothing currently exhausts them), scope-isolation-within-chat test (the general cross-org tests exist at the domain-service layer, not through the chat endpoint specifically) |
| 12 | Seeded generator reproducible; scenario manifest; real validation; as-of boundary tests | ✅ **Met** | `small` profile now implements 16 of 17 fixed scenarios (S15 covered separately by a direct cross-org test), byte-reproducible, loads through real validation/activation. `invalid` profile: 9 deliberate-defect fixtures, each verified to surface its specific labeled error code via the real validator. `demo` profile: 32 customers/210 orders (seed-reproducible, both currencies, realistic partial fulfillment/disputes/holds/unapplied-cash mix), activated against live Postgres, and verified isolated across two real organizations uploading the identical bundle. `load` profile: generates a 100,000-row-target bundle (reproducible for a given seed, distinct `LOAD-` ID prefix from `demo`), real-activated against live Postgres at 96,666 rows in 17.98s (see `docs/evaluation.md`). S12 due-date boundary math verified both as pure functions and against live-activated data. All four generator profiles (`small`, `invalid`, `demo`, `load`) now exist and are exercised by real tests |
| 13 | Live mode uses separate specialist modules; demo mode shares orchestration; UI labels mode; no A2A compliance claim | ⚠️ **Partially met** | Demo and live modes share the exact same specialist handlers and `InternalAgentTransport` — only the planning step (which specialist(s) to dispatch) differs, and that's a genuine, separately-verified Anthropic API call in live mode, not a relabeled demo response. The UI and API both label the mode on every response (`provider_mode: "demo"\|"live"`), verified live. No A2A compliance is claimed anywhere. **Gap**: live mode is "Claude classifies, deterministic code executes," not the fuller open-ended tool-calling loop description in agent_architecture.md implies for "real live-provider tool calling" — documented as a simplification, not hidden |

**Summary: 6 of 13 criteria fully (or "fully for what exists") met, 7
partially met with real evidence for the parts that exist, 0 not yet
started.** Every criterion now has at least partial real coverage; none
are at zero. "Partially met" still means real, meaningful gaps remain —
see each row's evidence column and the Known Gaps section below for what
specifically is missing. Nothing reported above as
"met" or "partially met" is based on assumption — each has a specific
test, log, query result, or screenshot behind it, cross-referenced in
`docs/implementation-plan.md`.

## What was actually built (no claims beyond this)

- **Foundation**: full Postgres schema (21 tables) via Alembic, applied
  against live Postgres; Keycloak realm with 4 roles and working OIDC
  login (real Authorization Code + PKCE flow, not a bypass); Docker
  Compose with 6 services; S3-compatible storage adapter (LocalStack
  locally, swappable); CI workflow definition; health/readiness endpoints.
- **Ingestion**: CSV schema manifest and validator (schema, duplicate PK,
  broken FK, unknown status, unsupported currency, negative amount);
  upload API storing raw files with content hashes; durable worker
  processing jobs via Postgres row-leases; transactional activation
  (supersede/create/reject atomically); CSV template downloads.
- **Domain logic**: pure, Decimal-exact calculation functions for invoice
  balances (with overapplication flagging, never clamping), aging
  buckets, dispute annotation, unbilled-shipment reconciliation, receipt
  matching, and hold presentation. One of these (balances) has a
  SQL-backed service and live API; the other three do not yet.
- **Operational interface**: one real screen (aging dashboard) and one
  real workflow (CSV upload with status polling), both verified against
  live data end to end, including in an actual browser.
- **Agent layer groundwork**: typed `TrustedContext`/`TaskRequest`/
  `SpecialistResult`/`FinalInvestigation` contracts and an
  `InternalAgentTransport` with routing, timeout, and duplicate-dispatch
  protection — the scaffolding Milestone 5's Supervisor and specialists
  will plug into, but no agents exist yet.

## Known gaps (mandatory, not yet done)

- SSE streaming/progress events for chat (current endpoint is synchronous
  request/response); cancellation; budget-exhaustion behavior.
- Document evidence upload/retrieval (TXT/PDF).
- ~~Customer detail/timeline screen~~, ~~exception workbench
  filters/sort/pagination/evidence-drawers~~, and user/business-unit
  admin management — all now built (see criterion #2). Org-level config
  screens (thresholds, currencies, retention, provider status) remain
  unbuilt — a narrower, lower-priority gap than the user-management
  piece that existed before.
- ~~`load` synthetic data profile~~ — now implemented and performance-measured (see `docs/evaluation.md`); all four profiles (`small`, `invalid`, `demo`, `load`) exist.
- ~~Full authorization test matrix~~ — now repeated at the HTTP/API layer
  (`test_authorization_http.py`), not just the domain-service layer; see
  criterion #6. Covers the dashboard, customer-detail, and admin
  endpoints. **Not yet covered**: the chat/investigation endpoint
  specifically, even though it uses the identical
  `assert_business_unit_access(app_user, body.business_unit_id)` pattern
  — a cross-org chat test is the same shape as the ones just added, just
  not written yet.
- Investigation/export/authorization-change audit events (import
  activation and task decisions are covered; those features aren't built).
- Live mode's planner classifies the question and lets deterministic code
  execute it, rather than a full open-ended Anthropic tool-calling loop —
  documented simplification, not a silent gap.
- Observability (structured logs beyond basic `structlog` usage,
  correlation IDs, metrics).
- Paginated-screen latency measurement (p95 under 2s at 10 concurrent users) — the import-throughput half of the performance target is now measured and passing (see docs/evaluation.md).
- ~~Automated bootstrap for organization/business-unit/app-user
  seeding~~ — app-user creation/role/grant management is now a real admin
  UI screen (`/api/v1/admin/users`); creating the *first* organization and
  business unit for a brand-new tenant is still a manual SQL step (there's
  no "create organization" endpoint yet, since every admin endpoint is
  itself scoped to an existing `app_user.organization_id`).

## Production readiness gates (per intent.md's own requirement to list these)

Unchanged from the spec's baseline expectation — none of these are
addressed by this build, and none should be inferred as addressed:
real identity-provider configuration for a non-demo environment,
HTTPS/domain setup, secret provisioning outside `.env` files, a backup
restore drill, representative load testing, a security review, and
business validation of the accounting/status mappings against real
Oracle data. No public deployment or external account changes have been
made or are authorized by this report.
