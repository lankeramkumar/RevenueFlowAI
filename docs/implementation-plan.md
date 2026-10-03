# RevenueFlow AI — Implementation Plan

This file is the live status tracker for the build. Read it first when
resuming work. Full approved plan (context, decisions, verification
strategy) is at the session plan file referenced in git history; this
document is the per-milestone source of truth going forward.

## Status (last updated: 2026-10-02)

**Current milestone: 1 — Foundation (verified end-to-end, real stack).**

**Docker Desktop installed and working.** `docker compose up --build` in
`infra/` brings up all 5 services (db, localstack, keycloak, backend,
worker, frontend) and all report healthy. Real verification performed
(not simulated) — see the checklist below.

**Deviations recorded (both documented, no silent scope changes):**
1. MinIO's Docker Hub and Quay images now deny anonymous pulls ("pull
   access denied... may require docker login") on this build date.
   Switched the local S3-compatible object store to **LocalStack**
   — already the documented fallback from the original stack-decision
   question. Only the `ObjectStore` adapter's concrete endpoint changed
   (`backend/src/revenueflowai/storage/s3_store.py`, generic boto3-based).
2. LocalStack's `:latest` tag now gates its S3 service behind a paid
   license token ("License activation failed"). Pinned
   `localstack/localstack:3.8` (pre-paywall community build), which works
   with no token.
3. Missing `.dockerignore` files in `backend/` and `frontend/` let the
   host's Windows-built `node_modules`/`.venv` leak into the Linux build
   context, breaking the frontend container build (`node.exe: not found`
   inside a Linux container). Added both — this was a real bug, not a
   policy workaround.

```bash
cd infra && docker compose up --build
```

## Milestones

### 1. Foundation — in progress

| Item | Status |
|---|---|
| Repo structure (backend/frontend/worker/infra) | ✅ done |
| Postgres schema + Alembic migration for all 12 CSV entities + import_jobs/dataset_versions/audit/tenancy | ✅ **verified**: `alembic upgrade head` ran for real inside the backend container against live Postgres 16; `\dt` confirms all 21 tables + `alembic_version` exist |
| Keycloak realm + 4 roles + demo users + audience mapper | ✅ **verified**: realm auto-imported on container start; `/.well-known/openid-configuration` resolves; **real login tested end-to-end in a browser** (demo-admin, full Authorization Code + PKCE flow, redirected back to the SPA authenticated) |
| FastAPI OIDC token validation + role/scope deps | ✅ written; the browser login proves Keycloak issues valid tokens the frontend can use — a protected-endpoint round trip is Milestone 2 (no business endpoints exist yet to test against) |
| Docker Compose (db, localstack, keycloak, backend, worker, frontend) | ✅ **verified**: `docker compose up --build` brings up all 5 services, all report healthy |
| `.env.example` | ✅ done |
| `/healthz`, `/readyz` | ✅ **verified** live: both return 200 from the running container (`{"status":"ok"}`, `{"status":"ready","database":"connected"}`) |
| CI workflow (lint/type-check/test backend+frontend, container build) | ✅ written (`.github/workflows/ci.yml`); container build steps are proven working since the same Dockerfiles were just built locally — not yet run on an actual GitHub Actions runner |
| Synthetic data generator CLI | ✅ working — `small` profile (S01, S09) implemented, byte-reproducibility verified by test and by manual double-run diff |
| S3-compatible storage adapter (LocalStack) | ✅ **verified**: backend's startup lifespan created both buckets for real — `awslocal s3 ls` inside the LocalStack container shows `raw-imports` and `exports` |
| Worker lease-claim loop skeleton | ✅ written and running as a container (`revenueflowai-worker-1`); no jobs exist yet to lease (ingestion UI is Milestone 2), so the claim path itself is still ⏳ untested against real contention — tracked for Milestone 2 |
| Frontend (Vite+React+TS, OIDC login, health check call) | ✅ **verified** live in a browser: loads, shows real backend health, completes a real Keycloak login, displays "Signed in as demo-admin@revenueflow.test" |

**Backend checks run and passing:**
- `ruff check .` — all checks passed
- `mypy src` — no issues found in 46 source files
- `pytest -v` — 40/40 passed
- `alembic upgrade head` — **applied for real** against live Postgres in the Compose stack (not just offline SQL rendering)

**Frontend checks run and passing:**
- `npx tsc --noEmit` — no errors
- `npm run build` — succeeds (both locally and inside the Docker build)
- `npm run lint` (oxlint) — no errors
- **Live browser verification**: real login round-trip against the containerized Keycloak, screenshot-confirmed

**Still open before Milestone 1 is fully closed:** seed demo `organizations`/
`business_units`/`app_users` rows linking Keycloak subjects to app-level
roles (currently `app_users` is empty, so no protected endpoint exists yet
to authorize against) — this naturally lands at the start of Milestone 2
alongside the first real import job.

### 2. Ingestion — in progress

| Item | Status |
|---|---|
| Machine-readable schema manifest (required columns, PKs, status vocab, currency rules, FK rules) for all 13 files | ✅ done (`backend/src/revenueflowai/ingestion/manifest.py`) |
| Pure CSV validator (schema/duplicate-PK/broken-FK/unknown-status/unsupported-currency/negative-amount) | ✅ done, no DB needed — unit-tested against the real generated `small` bundle (valid) and 6 deliberately broken fixtures (`tests/unit/test_ingestion_validator.py`, 7/7 passing) |
| Bundle hashing + idempotent import-job creation | ✅ **verified against live Postgres** (`ingestion/activation.py`: `compute_bundle_hash`, `get_or_create_import_job`) |
| Durable staging → transactional activation (supersede old version, create new, reject atomically on invalid) | ✅ **verified against live Postgres**: valid bundle activates and becomes the active `DatasetVersion`; invalid bundle is rejected (`status='rejected'`) with the *previous* active dataset confirmed unchanged; repeat upload with the same idempotency key replays without creating a duplicate dataset version |
| CSV row loader into scoped entity tables (all 13 files, Decimal/date-typed) | ✅ **verified against live Postgres**: generated `small` bundle's 3 invoices land correctly with exact `Decimal` amounts and full scope/lineage (`organization_id`, `business_unit_id`, `dataset_version_id`, `import_job_id`, `source_filename`, `source_row_number`) — `ingestion/loader.py` |
| Upload API (`POST /api/v1/imports`, admin-only, multipart) | ✅ **verified against the real running stack**: authenticated with a real Keycloak-issued token, uploaded the generated `small` bundle (13 files) over real HTTP, got back a `queued` job |
| Raw file storage in object store, keyed by org/job/filename | ✅ **verified**: all 13 files confirmed physically present in LocalStack via `awslocal s3 ls`, with `ImportJobFile` rows recording hash/size/key |
| Worker lease-claim loop processing real jobs end to end | ✅ **verified**: worker log shows `import_job.processed status=activated valid=True error_count=0` — claimed the job, pulled files back out of object storage, ran the full validate→activate pipeline |
| Worker crash recovery | ✅ **real bug found and fixed**: `claim_next_job`'s reclaim query only matched `status='queued'`, but a claimed job moves to `status='staging'` and nothing ever moves it back — a worker that crashed mid-job left it stuck at `staging` forever, never reclaimed even after its lease expired. Fixed by also matching `status='staging'` with an expired lease. 3 new integration tests against live Postgres (`test_worker_recovery.py`): crashed-job reclaim, live-lease-not-reclaimed, attempt-count cap |
| Status API (`GET /api/v1/imports/{id}`) | ✅ **verified**: polled after worker processing, returned `status=activated`, `activated_dataset_version_id` set, empty validation summary |
| End-to-end data correctness | ✅ **verified**: queried Postgres directly — the 3 invoices from the uploaded bundle are present under the new `dataset_version_id` with exact `Decimal` amounts (1000.00 USD, 100.00 USD, 200.00 EUR) |
| CSV template downloads (`GET /api/v1/templates`, `/{filename}`) | ✅ done — header-only CSVs generated from the same `ingestion/manifest.py` source of truth the validator uses, so a filled-in template always passes schema checks |
| Import UI (file picker, snapshot date, upload, poll status, show validation errors) | ✅ built and rendering correctly in the live browser session (`frontend/src/pages/ImportPage.tsx`), wired to the exact same `/api/v1/imports` endpoint already proven by the curl-based upload test — ⚠️ the actual click-and-select-a-file interaction is **not** verified by browser automation here: this tool cannot programmatically attach a local file to an `<input type=file>` (browsers block that for security). A human should click through it once; everything it calls has independently been proven to work. |
| Activation history (list of past import jobs, rollback) | 🔲 not started |
| Full `demo`/`invalid` generator profiles | 🔲 not started — `small` profile (S01, S09) remains the only one implemented |

**This closes the first genuine vertical slice** the build plan called
for: a real browser login → authenticated API upload → durable worker
processing → activated dataset → queryable rows in Postgres, with nothing
mocked at any layer. One more real bug found and fixed while wiring this:
Keycloak's dev-mode issuer is derived from the Host header of whoever
requests a token — since only the browser (via `localhost:8080`) ever
drives the login flow, tokens carry `iss=http://localhost:8080/...`, but
the backend container was validating against the Docker-network hostname
`http://keycloak:8080/...`, causing every real token to fail issuer
validation. Fixed by splitting the settings: `OIDC_ISSUER` now matches
what's actually in tokens (`localhost:8080`) while `OIDC_JWKS_URL` stays
on the container-reachable hostname (`keycloak:8080`) for fetching
signing keys — these were already independent settings in
`auth/oidc.py`, just misconfigured in Compose.

**New integration test suite** (`tests/integration/`, requires live Postgres,
auto-skips otherwise): `test_ingestion_activation.py` — 3/3 passing,
exercising the real activate/idempotency/rejection paths end to end. Fixed
two real bugs found while wiring this up: (1) `backend/src/revenueflowai/ingestion/loader.py`
was passing date strings straight to `Date`-typed columns, which asyncpg
rejects — added proper `date.fromisoformat` coercion; (2) a module-level
async engine singleton reused across pytest-asyncio's per-test event loops
breaks asyncpg on Windows ("attached to a different loop") — fixed by
pinning `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope`
to `"session"` in `pyproject.toml`.

**Infra fix (unrelated to this project, but blocking it):** a pre-existing
native PostgreSQL 18 Windows service on this machine was also bound to
port 5432, silently intercepting connections meant for the Compose
container (wrong credentials, very confusing error). Remapped the
Compose `db` service to host port **5433** rather than touching the
unrelated native service — see `infra/docker-compose.yml` and
`backend/.env.example`.

### 3. Domain logic — in progress

| Item | Status |
|---|---|
| Pure calculation functions: open balance, overapplication flag, aging bucket/days-overdue, unapplied receipt, dispute annotation | ✅ done (`domain/balances.py`) |
| Unbilled-shipment reconciliation (partial/full/insufficient-evidence) | ✅ done (`domain/shipments.py`) |
| Receipt match proposals (exact/ambiguous/bounded multi-invoice) | ✅ done (`domain/matching.py`) |
| Order hold presentation (no asserted cause) | ✅ done (`domain/holds.py`) |
| Scenario coverage against hand-transcribed S01–S17 expected values | ✅ S01–S14, S16 covered (16/17); S15 (cross-org isolation) and S17 (prompt-injection) are integration/agent-layer concerns deferred to Milestones 2's authz tests and Milestone 5 respectively — tracked, not silently dropped |
| SQL-backed aging summary service (currency-separated, bucketed) | ✅ **verified end-to-end**: real query over `Invoice`/`ReceiptApplication`/`CreditApplication` for the active dataset version, wrapping the pure `domain/balances.py` functions (`domain/services.py::compute_aging_summary`) |
| `GET /api/v1/dashboard/aging-summary` API | ✅ **verified live**: called through a real browser session, returns per-currency-bucket decimal strings |
| `GET /api/v1/me` (role + accessible business units) | ✅ **verified live**: frontend uses this to discover which business unit to query rather than hardcoding one |
| Real dashboard screen rendering the above | ✅ **verified live in a browser**, screenshot-confirmed: EUR 200.00 in bucket 1-30, USD 100.00 in bucket 1-30, USD 600.00 in bucket 31-60 — exactly matching the S01/S09 hand-calculation, computed from real uploaded CSV data, not mocked |
| Unbilled-shipment SQL service + `GET /api/v1/dashboard/unbilled-shipments` | ✅ **verified against live Postgres**: `domain/shipment_service.py` joins Shipment/ShipmentLine/OrderLine/InvoiceLine by external_id and wraps the pure function; test matches S05's partial-billing math exactly (8 shipped − 5 billed = 3 unbilled, $300 estimated value) |
| Receipt-match SQL service + `GET /api/v1/receipts/{id}/matches` | ✅ **verified against live Postgres**: `domain/matching_service.py` scopes candidates to same customer+currency open invoices; test matches S03's exact-match-via-remittance-reference case |
| Order-holds SQL service + `GET /api/v1/dashboard/order-holds` | ✅ **verified against live Postgres**: `domain/holds_service.py`; test matches S07's recorded-reason-without-asserted-cause case |
| Exception-prioritization rules | 🔲 not started |

**Tests added this pass:** `tests/unit/test_domain_balances.py`,
`test_domain_shipments.py`, `test_domain_matching.py`, `test_domain_holds.py`
(20 pure-function tests) plus `tests/integration/test_dashboard_aging_summary.py`
(2 tests) and `tests/integration/test_domain_sql_services.py` (3 tests,
S03/S05/S07, inserting rows directly rather than through the CSV pipeline
to isolate the service layer) — all against live Postgres. 48/48 backend
tests pass; `ruff`/`mypy` clean. All four domain services now have SQL
wrappers and live APIs; S01, S03, S05, S07, S09 have end-to-end coverage
(generator or direct-insert fixture → SQL service → assertion). The
remaining scenarios (S02, S04, S06, S08, S10–S14, S16) still have only
pure-function coverage, not SQL-service coverage.

**Typing bug found and fixed:** the money/quantity columns in
`models/entities.py` were declared `Mapped[object]` instead of
`Mapped[Decimal]` — harmless at runtime (SQLAlchemy's `Numeric` still
returned real `Decimal`s) but mypy couldn't catch type errors in code that
consumed them, which is exactly how this class of column was supposed to
be protected. Fixed across all 12 affected columns.

### 4. Operational interface — in progress

| Item | Status |
|---|---|
| Real client-side routing (React Router), shared nav, `/me`-driven layout | ✅ **verified live**: `/`, `/workbench`, `/imports` all navigate correctly in the running browser session |
| Dashboard (aging) | ✅ done (Milestone 3) |
| Exception workbench (unbilled shipments + active holds tables) | ✅ **verified live**: real empty-state rendering confirmed against the current dataset (which has no shipment/hold data — only S01/S09); API wiring identical to the proven dashboard pattern |
| Import screen | ✅ done (previous commit) |
| Exception workbench: filters, sort, pagination, priority explanations, evidence drawers | 🔲 not started — current version is an unfiltered real-data table, not the full spec |
| Customer detail / timeline | 🔲 not started |
| Action/task queue (create, assign, approve/reject/resolve, comments, audit) | ✅ **verified live end-to-end**: created a real task through the browser UI, approved it (role-gated to admin/approver via `DECISION_ROLES`), and confirmed both `task.created` and `task.transitioned` rows landed in the real `audit_events` table in Postgres — this also closes the "audit event writing" gap the acceptance report flagged. Backed by `models/tasks.py` (new migration `e85aa0753f3f`), `api/tasks.py`, `frontend/src/pages/TaskQueuePage.tsx`. Assignment UI and per-task comment thread UI are not built yet (API supports comments; no screen for them) |
| Administration screens (scopes, thresholds, currencies, retention, provider status) | 🔲 not started |

### 5. Investigation — core built and verified live

| Item | Status |
|---|---|
| Typed read-only tools (9 tools wrapping the SQL domain services) | ✅ done (`agents/tools.py`) |
| Order/AR/Cash specialist handlers (own tool allowlist, typed contract) | ✅ **verified live**: all three dispatch and return correct findings against real uploaded data |
| Demo planner (regex-based, no API key) | ✅ **verified live**, including a real bug found and fixed: initial regex only matched bare IDs (`RCP-2001`), not scenario-prefixed synthetic IDs (`S01-RCP`) — broadened to segment-based matching; 4 new unit tests |
| Live planner (real Anthropic call, forced tool-choice classification) | ✅ **verified live with real API calls** (not mocked): free-form phrasing the demo regex cannot match ("What does our AR aging look like right now across currencies?", "I got a payment in... The receipt ID is S01-RCP") was correctly classified and dispatched by Claude. Claude only selects domain/intent and extracts entity IDs — never computes a number or constructs a citation; `validate_plan` rejects anything outside the known domain/intent vocabulary before it reaches a specialist |
| Supervisor (dispatch, dedupe findings/evidence, aggregate) | ✅ **verified live**, including real cross-domain dispatch (customer-summary question correctly fanned out to Order+AR+Cash, Order honestly reported no handling rather than fabricating) |
| Chat API (`POST /api/v1/chat/investigate`, `GET /{id}/messages`) + persistence | ✅ **verified live**: conversations and messages (including specialist_status/evidence/missing_data) persist to Postgres |
| Chat UI | ✅ **verified live in a browser**: clicked a suggested question, got a correct real answer with specialist attribution, screenshot/text-confirmed |
| SSE streaming / progress events | 🔲 not started — current endpoint is synchronous request/response |
| Cancellation, per-turn budget enforcement (beyond the fixed defaults set per task) | 🔲 not started |
| Document evidence (TXT/PDF upload/retrieval) | 🔲 not started |
| Tests | 8 new tests: `tests/unit/test_demo_entity_extraction.py` (4) + `tests/integration/test_chat_investigation.py` (4, against live Postgres with real generated/activated data). The live Anthropic planner is verified manually against the running stack (shown above) rather than in automated tests, since it costs real tokens on every run — consistent with intent.md's "Keep live API tests opt-in." |

**A second real bug found while testing live**: the `aging_summary` and `customer_summary` specialist branches originally only produced `Metric` objects, not `Finding` statements — so a successful result with real numbers produced an empty-looking summary ("No findings were returned"). Fixed by adding a `Finding` alongside each `Metric`; re-verified live before and after (the before-state is a good example of why live verification catches things unit tests on handler logic alone would not).

### 6. Hardening & handoff — not started
Scope-isolation tests, worker crash recovery, prompt-injection fixtures,
observability, `load` profile + perf measurement, full `invalid` fixture
matrix, remaining doc deliverables, final `docs/acceptance-report.md`.

## Architectural decisions log

| Decision | Choice | Alternatives considered | Why |
|---|---|---|---|
| Backend framework | FastAPI + Pydantic v2 | Django REST, Flask | Async-native, OpenAPI docs built in, matches SSE streaming need in Milestone 5 |
| DB/migrations | PostgreSQL 16, SQLAlchemy 2.x async + Alembic | Raw SQL + lighter migration tool, Django ORM | Explicit Decimal/NUMERIC typing, mature async support, standard pairing |
| Worker | Postgres `SELECT...FOR UPDATE SKIP LOCKED` lease loop | Celery, RQ, Arq | Spec already mandates durable DB-tracked job state with leases/retries; an external broker would duplicate that durability model without adding capability at this scale |
| Object storage | ~~MinIO~~ → **LocalStack** behind an `ObjectStore` interface | MinIO (originally chosen, but Docker Hub/Quay now deny anonymous pulls as of this build), filesystem-only | Adapter interface (`storage/base.py`) made the swap a one-line Compose/env change, not a code change; LocalStack was the documented fallback from the original stack-decision question |
| Auth | Keycloak (self-hosted OIDC) + real JWT validation (issuer/audience/signature/expiry) | Demo-stub JWT issuer, external paid IdP (Auth0/Okta) | User explicitly asked for production-grade auth; self-hosted avoids "no paid resource creation"; still documented as needing a real production realm/HTTPS/domain before go-live |
| Frontend | Vite + React 18/19 + TypeScript, TanStack Query, react-oidc-context | Next.js | Pure SPA talking to a separate FastAPI backend; no SSR requirement |
| CSV generator | Stdlib csv/decimal + Typer CLI, no randomness in `small` profile | Faker-driven random generation | `small` profile scenarios are fixed/hand-specified per synthetic_data_requirements.md — determinism is simpler without a RNG for this profile; `demo`/`load` profiles (Milestone 2/6) will need seeded randomness for the additional ~30+ customers/200+ orders requirement |

## Requirement → test mapping (updated as milestones complete)

| Acceptance criterion (intent.md #) | Implementing component(s) | Test(s) | Status |
|---|---|---|---|
| 1. Clean checkout starts via Compose, migrates, demo login | `infra/docker-compose.yml`, `infra/keycloak/revenueflow-realm.json`, Dockerfiles | Manual: `docker compose up --build` + browser login | ✅ verified live (screenshot-confirmed demo-admin login) |
| 3. Valid imports become selectable versions; invalid bundles never change active data; repeat uploads idempotent | `api/imports.py`, `ingestion/activation.py`, `ingestion/loader.py`, `worker.py` | `tests/unit/test_ingestion_validator.py` (7/7) + `tests/integration/test_ingestion_activation.py` (3/3) + a real HTTP upload through the running stack | ✅ verified end-to-end (real upload → worker → activated dataset → queried rows); worker crash-restart recovery still ⏳ untested (Milestone 2 continuation) |
| 4. Hand-calculated fixtures match domain outputs exactly; currency totals stay separate | `domain/balances.py`, `domain/shipments.py`, `domain/matching.py`, `domain/holds.py` | `tests/unit/test_domain_*.py` (20 tests, S01-S14+S16) | ✅ pure-function layer verified; SQL-backed service wrapping real dataset-version rows is ⏳ pending Docker |
| 12 (partial). Seeded generator produces repeatable bundles | `seed/cli.py`, `seed/scenarios.py` | `tests/unit/test_generator_reproducibility.py` | ✅ passing for `small` profile |
| All other criteria (2, 5–11, 13) | — | — | 🔲 not started — tracked against later milestones |

## Risks and open questions

- **No Docker/Postgres on this machine** (see Status above) — the single
  biggest verification risk right now. Every "✅ written" item above needs
  a real-stack pass once Docker Desktop is confirmed working.
- Keycloak realm JSON has not been imported into a real Keycloak instance
  yet — JSON schema is valid, but Keycloak's own import validation (client
  scopes, protocol mapper config shape) is unverified until Docker is up.
- `demo`/`load` generator profiles will need a seeded-random approach not
  yet designed (Milestone 2/6) — the `small` profile's pure-fixed-scenario
  approach won't scale to "30+ customers, 200+ orders."

## Future scope (restated from intent.md, unchanged)

Oracle/OIC ingestion, CDC/incremental imports, approved ERP writeback,
multi-currency conversion with auditable FX, predictive payment models,
independently deployed A2A protocol agents, advanced OCR.
