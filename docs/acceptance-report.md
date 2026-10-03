# RevenueFlow AI — Acceptance Report

Checked against the 13 numbered acceptance criteria in `docs/intent.md`.
Each criterion is **Passed**, **Failed**, or **Unverified**, with the evidence
behind it. "Failed" means a stated requirement is demonstrably not met.
"Unverified" means it was not checked here, or cannot be checked in this
environment. Nothing is marked Passed on an unrun check.

Last full verification: 2026-10-03, against the Compose stack (backend, worker,
frontend, demo-seed, Postgres 16, Keycloak 26.0, LocalStack 3.8) on Docker
Desktop.

## How to run it

```bash
cd infra
docker compose up --build
```

- Frontend: http://localhost:5173 · API docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics · Keycloak: http://localhost:8080
- Demo logins (password `DemoPass123!`): `demo-admin`, `demo-analyst`,
  `demo-approver`, `demo-viewer`. The `demo-seed` service loads the demo dataset.
- Postgres on host port **5433** (a native Postgres holds 5432 on the build machine)

## Verification run

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest -q` | **148 passed** (unit and integration against live Postgres) |
| `ruff check .` / `mypy src` | clean / no issues in 85 files |
| `frontend: npx tsc -b --noEmit`, `npm run lint`, `npm run build` | clean, clean, built |
| Eval suite, demo mode (`python -m revenueflowai.evals`) | 10/10 cases, citation validity 1.00 |
| Eval suite, live mode (`--live`, one run) | 10/10 cases, citation validity 1.00, p50 812 ms |
| `docker compose up` (all services) | healthy; demo-seed loaded 2,189 rows into a fresh org |

## Acceptance criteria

| # | Criterion (intent.md) | Status | Evidence |
|---|---|---|---|
| 1 | Clean checkout starts via documented Compose commands, applies migrations, offers demo login and a seeded dataset | **Passed** | Verified from empty volumes in a separate Compose project (`docker compose -p rfclean up --build`): migrations applied, backend ready (`/readyz` connected), `demo-seed` loaded 2,189 rows, and demo-admin signed in with the pre-provisioned account bound on first login. Screenshots in `docs/screenshots` were captured from that fresh stack. The clean project was then removed with its volumes. |
| 2 | All primary UI routes operate against persisted backend data; no mock-only dashboard or broken placeholder controls | **Passed** | Verified in the browser against live data: dashboard, exceptions (filter, sort, pagination, evidence drawer), customers, admin, investigate (cited answers, follow-up, history reload, evidence drawer), tasks. Import verified by API upload and worker; the file picker was not driven by automation. |
| 3 | Valid imports become selectable versions; invalid bundles never change active data; repeat uploads are idempotent; worker restart recovers jobs | **Passed** | Demo bundle activated with 0 errors. Activation is atomic and versioned. Idempotency and rejection tests pass. Worker recovery: 3 tests (a crashed job is reclaimed after lease expiry, a live lease is not reclaimed, attempts are capped). |
| 4 | Hand-calculated financial and partial-billing fixtures match domain outputs exactly; currency totals stay separate | **Passed** | `test_scenario_expectations.py` checks S01, S02, S03, S04, S07, S08, S10, S11, S12, S13, S17 against activated data, with expected values copied from the scenario builders. `test_all_scenarios.py` adds S06 and S14, `test_unbilled_exceptions.py` covers S05, and `test_dashboard_aging_summary.py` covers S09 (with S01). S16 (snapshot staleness) has no domain output to check, so it is noted, not claimed. S15 is covered by the cross-org tests. Currency totals are asserted separate (S09; `invoices_by_currency_bucket` tests). |
| 5 | All five example questions work in demo and live mode, with source references and honest missing-data behavior | **Passed** | Eval suite (10 cases, which include the example questions, follow-ups, ambiguity, unsupported and injection cases): demo 10/10, live 10/10, citation validity 1.00 in both. Aggregate aging findings now cite the invoices behind each bucket (up to 50 per bucket, with the full count stated). Caveat: live mode was measured in one run. |
| 6 | Authorization tests prevent cross-organization and cross-business-unit reads through API, tools, exports, object access, and background jobs | **Passed** | `test_authorization_http.py` (7 tests through the real app): dashboard, customers, chat, evidence drill-down, admin lists, import-job status (foreign job returns 404), and a non-admin without a grant gets 403. `test_authorization_scope.py`: specialist tools called with another organization's business unit return nothing. No exports exist; the criterion's export clause does not apply yet. |
| 7 | Receipt suggestions handle ambiguity and residuals without modifying financial records | **Passed** | Matching is in `domain/matching.py` and `domain/matching_service.py`. S04 ambiguity is reported and not silently chosen; S13 is an exact two-invoice match with zero residual. A grep of the matching, receipts, cash, and tools code found no session writes. |
| 8 | Task approvals persist audit history but cannot post cash, email customers, or release ERP holds | **Passed** | Live: a task moved `proposed` → `approved` through the API. `audit_events` holds `task.created` and `task.transitioned` for it. No transition calls an external system. |
| 9 | Tests, CI, migrations, health checks, container builds, and reproducible setup pass; report commands and results | **Unverified** | CI steps were replayed in clean python:3.12 and node:22 containers (`ci.yml` now runs Postgres and migrations; `REQUIRE_DATABASE_TESTS` prevents silent skips): backend 148 passed, none skipped; frontend lint, typecheck, and build pass. Locally: 148 backend tests, ruff, mypy, and frontend checks pass; containers build and run; health and metrics respond. **Not run:** `.github/workflows/ci.yml` has never run on a GitHub Actions runner. |
| 10 | README, architecture diagram, data dictionary, CSV templates, API documentation, threat model, evaluation report, and operations/deployment runbook are complete | **Passed** | Refreshed 2026-10-03: `README.md` (bootstrap, API surface), `docs/architecture.md` (new components), `docs/evaluation.md` (evals and observability), `docs/operations.md` (first start, bootstrap, metrics, quality gate), `docs/security.md` (new threat surface). Unchanged and still accurate: the data dictionary and CSV templates (no schema changes this round). OpenAPI at `/docs` is generated. |
| 11 | Supervisor routing (order-only, AR-only, cash-match, cross-domain without duplicate totals); tests for partial failure, cancellation, budgets, scope isolation, and persisted follow-ups | **Failed** | Passed: routing for each domain; customer summary fan-out without duplicate totals; partial failure (a crashing specialist yields `specialist_error` and the rest still return; tested); scope isolation; persisted follow-ups (`test_chat_followup_api.py`). **Not met:** cancellation is not implemented, because it needs a background job model. Budgets are set but never enforced; only the 3-dispatch cap and per-dispatch timeout are enforced. |
| 12 | Seeded generator reproducible; scenario manifest; generated records load through real validation; fixed as-of boundary tests pass | **Passed** | Four profiles (`small`, `invalid`, `demo`, `load`). Byte-reproducibility test. The `small` profile loads through real validation; each `invalid` fixture surfaces its labeled error. `load`: 96,666 rows activated in 17.98 s. Boundary test S12 checks all nine due-date buckets. |
| 13 | Live mode uses separate specialist modules with typed inputs and results and bounded provider calls; demo mode exercises the same orchestration without credentials; the UI labels the execution mode; no A2A claim | **Passed** | Demo and live share the specialist handlers and `InternalAgentTransport`; only planning differs. Live planning is one bounded, forced-tool call, and the output is validated against an allowlist and guarded (customer summaries need a customer ID). The UI badges DEMO or LIVE on every answer. No A2A claim. Documented simplification: live mode is classify-then-execute, not an open tool-calling loop. |

**Summary: 11 Passed (1–8, 10, 12, 13), 1 Failed (11), 1 Unverified (9).**

## Defects found and fixed while meeting the criteria

- **Live planner routed a non-data question** ("weather in Paris") to a customer summary. Fixed by the prompt's decline rule and a deterministic guard (customer summaries need a customer ID). Covered by `test_live_planner_guards.py`.
- **Live planner answered a prompt-injection request** with aging figures. Fixed by the prompt rule that instructions inside a question are data. Re-run: 10/10.
- **Organization name collision in the demo seed.** The name was a fixed string, and organization names are unique. Now derived from the slug.
- **Stale scenario test.** It queried disputes without scoping to its dataset version, so it broke once other tests committed the same bundle.
- **Earlier this pass:** fully billed lines reported as unbilled; raw decimals in finding text; follow-ups with no memory of prior turns; a crashing specialist failing the whole investigation; non-admin requests crashing on business-unit-scoped endpoints (`MissingGreenlet`).

## Known gaps

- Cancellation and budget enforcement (criterion 11).
- Document evidence (TXT/PDF) is not built.
- SSE streaming for chat (the endpoint is request/response).
- Admin config screens (thresholds, currencies, retention, provider status).
- The worker has no metrics endpoint. Investigation metrics come from the backend process only.
- Chat has been checked at desktop width only.
- The CI workflow has not run on a GitHub runner.

## Production readiness gates (not addressed by this build)

Per intent.md, none of these are addressed here: a real identity provider for
a non-demo environment (the realm is a development realm with demo users and
a dev-mode issuer); HTTPS and domain setup; secret provisioning outside `.env`;
a backup restore drill; load testing at the target concurrency, since the
paginated-screen p95 is still unmeasured; an independent security review; and
business validation of the accounting and status mappings against real data.
No public deployment or external account change has been made or is authorized
by this report.
