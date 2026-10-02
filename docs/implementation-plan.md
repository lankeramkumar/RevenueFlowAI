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
| Raw file storage with content-hash + idempotency key | 🔲 not started — needs the live object store, ⏳ pending Compose boot |
| Durable staging → admin activation (transactional, versioned, rollback) | 🔲 not started — needs Postgres, ⏳ pending Docker |
| Lineage fields wired end-to-end from upload to row | 🔲 not started |
| Import UI (upload, progress, row errors, activation history) | 🔲 not started |
| CSV templates for download, full `demo`/`invalid` generator profiles | 🔲 not started |

### 3. Domain logic — in progress

| Item | Status |
|---|---|
| Pure calculation functions: open balance, overapplication flag, aging bucket/days-overdue, unapplied receipt, dispute annotation | ✅ done (`domain/balances.py`) |
| Unbilled-shipment reconciliation (partial/full/insufficient-evidence) | ✅ done (`domain/shipments.py`) |
| Receipt match proposals (exact/ambiguous/bounded multi-invoice) | ✅ done (`domain/matching.py`) |
| Order hold presentation (no asserted cause) | ✅ done (`domain/holds.py`) |
| Scenario coverage against hand-transcribed S01–S17 expected values | ✅ S01–S14, S16 covered (16/17); S15 (cross-org isolation) and S17 (prompt-injection) are integration/agent-layer concerns deferred to Milestones 2's authz tests and Milestone 5 respectively — tracked, not silently dropped |
| SQL-backed services wrapping these pure functions with real dataset-version queries | 🔲 not started — needs Postgres, ⏳ pending Docker |
| Exception-prioritization rules | 🔲 not started |
| REST APIs exposing these calculations | 🔲 not started |

**Tests added this pass:** `tests/unit/test_domain_balances.py`,
`test_domain_shipments.py`, `test_domain_matching.py`, `test_domain_holds.py`
— 20 tests, all passing, pure Python (no DB). Combined with Milestones 1–2,
32/32 backend tests pass; `ruff`/`mypy` clean.

### 4. Operational interface — not started
Dashboard, exception workbench, customer timeline, evidence drawers,
action/task queue, admin screens.

### 5. Investigation — not started
Supervisor + Order/AR/Cash Application specialists, typed contracts,
Anthropic provider + demo provider, persisted chat/SSE, document evidence.

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
| 1. Clean checkout starts via Compose, migrates, demo login | `infra/docker-compose.yml`, `infra/keycloak/revenueflow-realm.json`, Dockerfiles | Manual: `docker compose up --build` | ⏳ pending Docker |
| 3 (partial). Valid imports become selectable versions; invalid bundles never change active data | `models/ingestion.py` schema, `ingestion/validator.py`, `worker.py` lease loop | `tests/unit/test_ingestion_validator.py` (7/7: valid bundle + 6 broken fixtures) | ⏳ validation logic done; staging/activation transaction needs Postgres (Milestone 2 continuation) |
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
