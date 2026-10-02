# RevenueFlow AI — Implementation Plan

This file is the live status tracker for the build. Read it first when
resuming work. Full approved plan (context, decisions, verification
strategy) is at the session plan file referenced in git history; this
document is the per-milestone source of truth going forward.

## Status (last updated: 2026-10-02)

**Current milestone: 1 — Foundation (in progress).**

**Environment blocker:** the primary dev machine has no Docker/Podman and
no local PostgreSQL. WSL2 install was run; Docker Desktop install is in
progress. Until `docker compose up` can actually run, the checks below
marked "⏳ pending Docker" are written/compiled/unit-tested but **not**
verified against a live Postgres/Keycloak/MinIO stack. Re-run them for real
as soon as Docker Desktop is confirmed working (`docker --version` and
`docker compose version` both succeed), starting with:
```bash
cd infra && docker compose up --build
```

## Milestones

### 1. Foundation — in progress

| Item | Status |
|---|---|
| Repo structure (backend/frontend/worker/infra) | ✅ done |
| Postgres schema + Alembic migration for all 12 CSV entities + import_jobs/dataset_versions/audit/tenancy | ✅ written, compiles offline (`alembic upgrade head --sql`) — ⏳ pending Docker for a real `alembic upgrade head` |
| Keycloak realm + 4 roles + demo users + audience mapper | ✅ written (`infra/keycloak/revenueflow-realm.json`, valid JSON) — ⏳ pending Docker to confirm Keycloak actually imports it and issues working tokens |
| FastAPI OIDC token validation + role/scope deps | ✅ written (`backend/src/revenueflowai/auth/`) — ⏳ pending Docker for a real token round-trip test |
| Docker Compose (db, minio, keycloak, backend, worker, frontend) | ✅ written (`infra/docker-compose.yml`) — ⏳ pending Docker to actually boot |
| `.env.example` | ✅ done |
| `/healthz`, `/readyz` | ✅ done; `/healthz` unit-tested with `TestClient` (no DB needed) — `/readyz` needs a live DB, ⏳ pending Docker |
| CI workflow (lint/type-check/test backend+frontend, container build) | ✅ written (`.github/workflows/ci.yml`) — not yet run on a real CI runner |
| Synthetic data generator CLI | ✅ working — `small` profile (S01, S09) implemented, byte-reproducibility verified by test and by manual double-run diff |
| MinIO storage adapter | ✅ written (`backend/src/revenueflowai/storage/`) — ⏳ pending Docker for a real put/get round trip |
| Worker lease-claim loop skeleton | ✅ written (`backend/src/revenueflowai/worker.py`) — real CSV processing logic is Milestone 2; ⏳ pending Docker for a real lease test |
| Frontend skeleton (Vite+React+TS, OIDC login, health check call) | ✅ builds clean (`npm run build`, `tsc --noEmit`, `oxlint` all pass) — ⏳ pending Docker/Keycloak for a real login round-trip |

**Backend checks actually run and passing on this machine (no DB needed):**
- `ruff check .` — all checks passed
- `mypy src` — no issues found in 35 source files
- `pytest -v` — 5/5 passed (generator reproducibility, S01/S09 scenario math, model registration, `/healthz`)
- `alembic upgrade head --sql` — migration renders valid SQL against the Postgres dialect offline

**Frontend checks actually run and passing:**
- `npx tsc --noEmit` — no errors
- `npm run build` — succeeds
- `npm run lint` (oxlint) — no errors

### 2. Ingestion — in progress

| Item | Status |
|---|---|
| Machine-readable schema manifest (required columns, PKs, status vocab, currency rules, FK rules) for all 13 files | ✅ done (`backend/src/revenueflowai/ingestion/manifest.py`) |
| Pure CSV validator (schema/duplicate-PK/broken-FK/unknown-status/unsupported-currency/negative-amount) | ✅ done, no DB needed — unit-tested against the real generated `small` bundle (valid) and 6 deliberately broken fixtures (`tests/unit/test_ingestion_validator.py`, 7/7 passing) |
| Raw file storage with content-hash + idempotency key | 🔲 not started — needs MinIO, ⏳ pending Docker |
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
| Object storage | MinIO behind an `ObjectStore` interface | LocalStack, filesystem-only | Most common local S3-compatible store; adapter interface keeps swapping to real S3 later cheap |
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
