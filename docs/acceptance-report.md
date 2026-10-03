# RevenueFlow AI — Acceptance Report

Checked against the 13 numbered acceptance criteria in `docs/intent.md`.
Each criterion is marked **Passed**, **Failed**, or **Unverified**, with the
evidence behind it. "Failed" means a stated requirement is demonstrably not
met yet; "Unverified" means it was not checked here, or cannot be checked in
this environment. Nothing is marked Passed on the strength of an unrun check.

Verification date: 2026-10-03. Stack: `docker compose` in `infra/` (backend,
worker, frontend, Postgres 16, Keycloak 26.0, LocalStack 3.8), Docker Desktop
on the build machine.

## How to run it

```bash
cd infra
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Keycloak: http://localhost:8080 (admin console: admin / admin)
- Demo logins (password `DemoPass123!` for all): `demo-admin`, `demo-analyst`,
  `demo-approver`, `demo-viewer` (see README.md)
- Postgres on host port **5433** (a native Postgres service on the build
  machine holds 5432)
- Demo data: `python -m revenueflowai.seed generate --profile demo --seed 42
  --as-of 2026-10-02 --output ../sample-data/demo`, then upload the 13 CSVs on
  the Import screen as admin. Nothing is seeded automatically.

## Verification run (this session)

| Command | Result |
|---|---|
| `backend/.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| `backend/.venv/Scripts/python.exe -m mypy src` | Success: no issues in 77 source files |
| `backend/.venv/Scripts/python.exe -m pytest -q` | **130 passed** (unit + integration against live Postgres) |
| `frontend: npx tsc -b --noEmit` | clean |
| `frontend: npm run lint` | clean |
| `frontend: npm run build` | built |
| `docker compose up --build -d` (backend, worker, frontend) | all services healthy; `/healthz` returns ok |
| Demo CSV upload via `POST /api/v1/imports` + worker | job `activated`, 0 validation errors |

Live browser checks were run against the Compose stack (Keycloak login as
`demo-admin`): dashboard, exception workbench (filter, sort, pagination,
evidence drawer), customer detail, admin, investigate chat (question,
follow-up chip, reload from history, evidence drawer), and tasks.

## Acceptance criteria

| # | Criterion (intent.md) | Status | Evidence |
|---|---|---|---|
| 1 | Clean checkout starts via documented Compose commands, applies migrations, offers demo login and a seeded dataset | **Failed** | Compose stack starts and migrations apply (the `backend` command runs `alembic upgrade head`). Demo login works. First-tenant creation is now a command (`python -m revenueflowai.bootstrap`, idempotent, covered by `test_bootstrap.py`), replacing manual SQL. **Not met:** the demo dataset is still not seeded automatically on first boot; it must be generated and uploaded. A from-empty-volume boot was not run because it would destroy the local demo data. |
| 2 | All primary UI routes operate against persisted backend data; no mock-only dashboard or broken placeholder controls | **Passed** | Routes verified in the browser against live data: dashboard (currency-separated aging), exceptions (paginated, filterable, evidence drawer), customers (`DEMO-CUST-000001`: real invoices, open balances, aging buckets, timeline), admin (business units, user role/active/grants), investigate (cited answers, history reload), tasks (create/approve, API-verified). Import verified by API upload + worker; the native file picker was not driven by automation. |
| 3 | Valid imports become selectable versions; invalid bundles never change active data; repeat uploads are idempotent; worker restart recovers jobs | **Passed** | Demo bundle activated with 0 errors (live). Activation is atomic and versioned (`ingestion/activation.py`). Idempotency and rejection covered by ingestion integration tests. Crash recovery: 3 tests in `test_worker_recovery.py` (a crashed job stuck at `staging` is reclaimed after lease expiry; live leases are not reclaimed; attempt count is capped). |
| 4 | Hand-calculated financial and partial-billing fixtures match domain outputs exactly; currency totals remain separate | **Failed** | Matches verified at SQL level for S01 (balance 600.00, bucket 31–60), S05 (3 units unbilled, 300.00), S06 (4 units, 200.00), S09 (USD and EUR separate), S02 (dispute does not reduce balance). S14 insufficient-evidence verified. **Not met:** the other scenarios (S03, S04, S07, S08, S10–S13, S16, S17) are verified only at pure-function level, not against activated data. Real defect fixed this session: fully billed shipment lines were reported as unbilled exceptions (see Defects below). |
| 5 | All five example questions work in demo and live mode, with source references and honest missing-data behavior | **Failed** | Demo verified: invoice overdue/dispute (cited, with metric); customer summary (`1,150.00 EUR`, matches stored balance); order hold without an order ID asks which order (honest). Receipt match covered by integration test. Live verified with free-form phrasing (`docs/evaluation.md`). **Not met:** aging and customer-summary **metrics carry no source references**, so answers built only from them are uncited. The live answer to "which customers are slowest to pay" returned aging buckets, not a per-customer ranking; there is no ranking intent. |
| 6 | Authorization tests prevent cross-org and cross-BU reads through API, tools, exports, object access, and background jobs | **Failed** | Passed for the API: `test_authorization_http.py` (6 tests through the real FastAPI app) covers dashboard, customer detail, chat, evidence drill-down, and admin lists. Denial path verified (403 `business_unit_not_granted`). Found and fixed a real bug: non-admin roles would raise `MissingGreenlet` on every business-unit-scoped request (`auth/deps.py`). Import-job status is now covered by a cross-organization HTTP test (another org's job ID returns 404). **Not met:** no cross-scope test for tool-level calls, and there are no exports to test. |
| 7 | Receipt suggestions handle ambiguity and residuals without modifying financial records | **Passed** | Matching is in `domain/matching.py` and `domain/matching_service.py`. Ambiguity and residuals are covered by unit and integration tests (S04 ambiguous match is not silently selected; cash specialist reports residuals). A grep of the matching, receipts, cash, and tools code found no session writes, so the path is read-only. |
| 8 | Task approvals persist audit history but cannot post cash, email customers, or release ERP holds | **Passed** | Live: created and approved a task through the API (`proposed` → `approved`); `audit_events` holds `task.created` and `task.transitioned` rows for it. The task state machine changes only `status`; no transition calls an ERP, payment, or email integration. |
| 9 | Tests, CI, migrations, health checks, container builds, and reproducible setup pass; report commands and results | **Unverified** | Local: 127 backend tests, ruff, mypy, frontend tsc/lint/build all pass (see table above). Containers build and run; health checks respond. **Unverified:** `.github/workflows/ci.yml` has never run on a GitHub Actions runner, so the CI half of this criterion is not established. |
| 10 | README, architecture diagram, data dictionary, CSV templates, API documentation, threat model, evaluation report, and operations/deployment runbook are complete | **Failed** | `README.md` now covers the bootstrap command and lists the API surface. **Not met:** `docs/evaluation.md`, `docs/operations.md`, and `docs/security.md` are still stale; they don't describe the follow-up behavior, the evidence endpoint, the admin screens, or the current threat surface. OpenAPI at `/docs` is generated and current. |
| 11 | Supervisor routing (order-only, AR-only, cash-match, cross-domain without duplicate totals); tests for partial failure, cancellation, budgets, scope isolation, persisted follow-ups | **Failed** | Passed: routing tests for order, AR, and cash questions; customer summary fans out to all three specialists without duplicate totals; **persisted follow-ups work**: `test_chat_followup_api.py` shows a pronoun follow-up ("Is there a dispute on it?") resolving to the prior turn's invoice, with history reloading in order. A specialist that raises now yields a `specialist_error` result instead of failing the investigation, tested in `test_agent_transport.py`. **Not met:** cancellation is not implemented (it needs a background job model); budgets are set but never enforced (only the 3-dispatch cap and the per-dispatch timeout are enforced); no chat-endpoint partial-failure test. |
| 12 | Seeded generator reproducible; scenario manifest; generated records load through real validation; fixed as-of boundary tests pass | **Passed** | Four profiles (`small`, `invalid`, `demo`, `load`). Byte-reproducibility test; scenario manifest; the `small` profile activates through real validation; `invalid` fixtures each surface their labeled error code; `load` profile: 96,666 rows activated in 17.98s (see `docs/evaluation.md`). Boundary tests (S12 due-date math) pass. |
| 13 | Live mode uses separate specialist modules with typed inputs/results and bounded provider calls; demo mode runs the same orchestration without credentials; UI labels execution mode; no A2A claim | **Passed** | Demo and live share the specialist handlers and `InternalAgentTransport`; only the planning step differs. Live planning is one bounded, forced-tool classification call, and `validate_plan` rejects anything outside the allowlist. The chat UI shows a **DEMO** or **LIVE** badge on every answer (verified in the browser). No A2A compliance is claimed. Documented simplification: live mode is classify-then-execute, not an open tool-calling loop. |

**Summary: 6 Passed (2, 3, 7, 8, 12, 13), 6 Failed (1, 4, 5, 6, 10, 11), 1 Unverified (9).**

## Defects found and fixed in this pass

- **Fully billed shipments reported as unbilled exceptions.** `domain/shipment_service.py` kept lines with `unbilled_quantity = 0`. The workbench and chat both showed them. Fixed; regression test `test_unbilled_exceptions.py` (includes hand-calculated S05/S06 values).
- **Zero and trailing-zero decimals printed raw** (`0E-8`, `1150.0000 EUR`) in finding statements. Fixed with `agents/format.py` (2-dp money with separators; quantities without trailing zeros). Unit tests in `test_order_formatting.py`.
- **Order-shipment findings were indistinguishable** (same wording per line, no line ID). Now include shipment and line IDs.
- **Follow-up questions had no memory.** Each turn planned in isolation, so "it" or "this invoice" failed. Fixed: the prior assistant turn's invoice, receipt, or customer IDs are carried into the next plan only when the question actually points back (`resolve_follow_up_entities`). Unit and API tests cover it.
- **Dispute questions without the word "invoice" did not route to AR.** Fixed in the demo classifier.
- **Chat answers were a flat summary string.** The API now returns structured findings (statement + evidence), metrics, specialist status, missing data, and mode; history reloads with the same structure.
- **Non-admin requests would crash** on business-unit-scoped endpoints (`MissingGreenlet`; `auth/deps.py`). Fixed with eager loading; covered by authorization tests.
- **Shared-database test interference:** an existing scenario test queried disputes by external ID without scoping to its dataset version, which failed once other tests committed the same bundle. Scoped to the fixture's dataset version.

## Known gaps (unresolved)

- Org and business-unit creation for a brand-new tenant is manual SQL; there is no "create organization" endpoint.
- Chat has no cancellation, no budget enforcement, and no SSE streaming (the endpoint is request/response).
- Aging and customer-summary metrics have no evidence references; live mode has no per-customer ranking intent.
- Document evidence (TXT/PDF upload and retrieval) is not built.
- Admin config screens (thresholds, currencies, retention, provider status) are not built.
- Observability is basic `structlog` only (no correlation IDs or metrics export).
- The chat UI has been checked at desktop width in the built-in browser only; mobile widths were not tested.
- Import file picker was not exercised by browser automation (the upload path was verified via the API).

## Production readiness gates (not addressed by this build)

Per intent.md, none of these are addressed, and none should be read as
addressed: real identity-provider configuration for a non-demo environment
(the Keycloak realm uses demo users and a dev-mode issuer), HTTPS and domain
setup, secret provisioning outside `.env` files, a backup restore drill,
representative load testing (paginated-screen p95 is unmeasured), a security
review, and business validation of the accounting and status mappings against
real data. No public deployment or external account changes have been made or
are authorized by this report.
