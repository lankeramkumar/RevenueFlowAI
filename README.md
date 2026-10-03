# RevenueFlow AI

**An Order-to-Cash exception investigator.** It finds where billing and cash
are blocked in CSV exports of orders, shipments, invoices, and receipts, and
answers questions about them. The numbers come from deterministic SQL code,
never from a language model. Every answer cites the stored records behind it,
and each citation opens to the underlying row.

[![Watch the 60-second walkthrough](docs/demo/poster.png)](docs/demo/walkthrough.mp4)

*60-second walkthrough: exceptions with evidence, a cited investigation with a follow-up, the evidence drawer, and a customer timeline.*

**Highlights**

- Deterministic finance: Decimal-exact aging, unbilled-shipment, and receipt-matching logic, with currencies never combined.
- Investigation with citations: a Supervisor routes questions to Order, AR, and Cash specialists. Demo and live modes share the same execution path.
- Evals and observability: a 10-case eval suite (10/10 in both modes, 100% citation validity) plus request IDs and Prometheus metrics.
- Production-minded auth: Keycloak OIDC, organization and business-unit scoping, and an append-only audit trail for approvals.

**Run it:** `cd infra && docker compose up --build`, then open http://localhost:5173 and sign in as `demo-admin` / `DemoPass123!`.

## What it does

- **CSV ingestion** with a schema manifest, row-level validation (types,
  precision, dates, duplicate keys, broken references, unknown statuses,
  cross-file rules such as "same customer and currency"), and atomic,
  versioned activation. An invalid bundle never changes active data.
- **Deterministic finance.** Open balances, aging buckets, unbilled
  shipments, holds, and receipt matching are Decimal-exact functions. Currencies
  are never combined. A disputed invoice is annotated, not reduced.
- **Investigation.** A Supervisor routes each question to the Order, AR, or
  Cash specialist, which runs allowlisted queries and returns findings with
  evidence. Results come back as structured findings, metrics, missing data,
  and specialist status.
- **Follow-ups.** "Is there a dispute on it?" resolves "it" from the prior
  turn's cited invoice. Conversations persist and reload with their citations.
- **Two modes, one code path.** Demo mode uses deterministic routing and needs
  no API key. Live mode uses a bounded Anthropic classification call. Only
  routing differs; the figures always come from the same SQL. The UI labels
  every answer DEMO or LIVE.
- **Authorization.** Organization and business-unit scoping on every query,
  authenticated with Keycloak (OIDC, PKCE in the browser, JWKS validation in
  the API). Four roles: admin, analyst, approver, viewer. Admins are
  pre-provisioned by email and bound to their identity on first verified sign-in.
- **Auditable actions.** Follow-up tasks move through an approval state
  machine. Every transition writes an append-only audit row. Approval changes
  only the task's status. It never posts cash, emails a customer, or releases
  an ERP hold.
- **Evals and observability.** An eval suite scores routing, entities,
  findings, abstention, and citation validity. Request IDs run through the
  logs, and Prometheus-format metrics are exposed at `/metrics`.

## Verified

| Check | Result |
|---|---|
| Backend tests (unit and integration against Postgres 16) | 149 passed, none skipped |
| Backend lint and types (`ruff`, `mypy`) | clean |
| Frontend (`oxlint`, `tsc`, production build) | clean |
| CI steps replayed in clean Python 3.12 and Node 22 containers | pass |
| Investigation evals, demo mode | 10/10 cases, citation validity 1.00 |
| Investigation evals, live mode (Anthropic, one run) | 10/10 cases, citation validity 1.00, p50 ≈ 0.8 s |
| Scenario fixtures (hand-calculated, checked against activated data) | S01–S17 except S16 (staleness display) |
| Clean start from empty volumes (migrations, demo seed, login) | verified |

Acceptance status against the 13 criteria in [docs/intent.md](docs/intent.md)
is tracked in [docs/acceptance-report.md](docs/acceptance-report.md), with
evidence for each.

## Screens

![Dashboard](docs/screenshots/01-dashboard.png)

| | |
|---|---|
| Investigation with citations | ![Cited answer](docs/screenshots/04-investigation-cited-answer.png) |
| Follow-up resolved from the prior turn | ![Follow-up](docs/screenshots/05-investigation-follow-up.png) |
| Evidence drill-down (stored record and linked rows) | ![Evidence](docs/screenshots/06-evidence-drill-down.png) |
| Exception workbench (filter, sort, paginate, evidence) | ![Workbench](docs/screenshots/02-exception-workbench.png) |
| Customer timeline (balances, aging, events) | ![Customer](docs/screenshots/03-customer-timeline.png) |
| Admin: business units and users | ![Admin](docs/screenshots/07-admin.png) |

## Quick start (Docker)

Requires Docker Desktop (WSL2 backend on Windows).

```bash
cd infra
docker compose up --build
```

This starts Postgres, LocalStack (S3-compatible storage), Keycloak with a demo
realm, the API (migrations apply on start), the import worker, the frontend,
and a one-shot `demo-seed` that loads 32 customers and about 2,200 rows.

- App: http://localhost:5173 · API docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics · Keycloak admin: http://localhost:8080 (admin / admin)

Sign in as a demo user. The password for all of them is `DemoPass123!`.

| User | Role | What to try |
|---|---|---|
| `demo-admin` | admin | Everything, including Import and Admin |
| `demo-analyst` | analyst | Investigate, exceptions, customers |
| `demo-approver` | approver | Approve follow-up tasks |
| `demo-viewer` | viewer | Read-only views |

Try in Investigate: *"Why is DEMO-ORD-000007-INV overdue?"*, then the follow-up
*"Is there a dispute on it?"*, then click a citation.

These credentials exist only in the local Keycloak realm
(`infra/keycloak/revenueflow-realm.json`). They are not production secrets.

### Live mode (optional)

Demo mode needs nothing else. To enable live routing, put a key in
`backend/.env` (copy `backend/.env.example`):

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Then choose **Live** in the Investigate screen's mode selector. Each live
question makes one bounded model call, which costs tokens.

### First tenant in a real deployment

```bash
cd backend
python -m revenueflowai.bootstrap --org-name "Acme" --org-slug acme --admin-email admin@acme.test
```

The admin is created pending and bound to their Keycloak identity on first
sign-in, but only when Keycloak reports that email as verified.

## Running the tests

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate      # Windows; use bin/activate elsewhere
pip install -e ".[dev]"
DATABASE_URL=postgresql+asyncpg://revenueflow:revenueflow@localhost:5433/revenueflow alembic upgrade head
pytest
```

Integration tests need a migrated Postgres. Without one they are skipped. Set
`REQUIRE_DATABASE_TESTS=1` to make a missing database fail the run instead.

Frontend:

```bash
cd frontend
npm ci
npm run lint && npx tsc -b --noEmit && npm run build
```

## Evals

```bash
cd backend
python -m revenueflowai.evals --organization-id <uuid> --business-unit-id <uuid> --actor-user-id <uuid>
```

Scores ten cases against an activated dataset: routing, entities, findings,
abstention, and whether every citation resolves to a stored record. Exits
non-zero below 100% pass rate or citation validity. Add `--live` for the
Anthropic planner.

## Architecture

```mermaid
flowchart LR
  UI[React SPA] -->|OIDC PKCE token| KC[Keycloak]
  UI -->|REST + bearer| API[FastAPI]
  API --> AUTH[JWT validation + org/BU scope]
  API --> SUP[Supervisor]
  SUP -->|validated plan| PLAN[Demo or live planner]
  SUP --> ORD[Order specialist]
  SUP --> ARS[AR specialist]
  SUP --> CASH[Cash specialist]
  ORD & ARS & CASH --> DOM[Deterministic domain services]
  DOM --> PG[(PostgreSQL)]
  API -->|upload| S3[(Object storage)]
  S3 --> WK[Import worker] -->|validate, activate| PG
```

Full description, including the request flow and the agent contracts, is in
[docs/architecture.md](docs/architecture.md).

## Documentation

| Doc | Contents |
|---|---|
| [docs/intent.md](docs/intent.md) | Product scope and the 13 acceptance criteria |
| [docs/architecture.md](docs/architecture.md) | Components, request flow, agent contracts |
| [docs/data-dictionary.md](docs/data-dictionary.md) | The 13 CSV files and their columns |
| [docs/security.md](docs/security.md) | Threat model, authorization, open gates |
| [docs/evaluation.md](docs/evaluation.md) | Test results, eval results, observability |
| [docs/operations.md](docs/operations.md) | Startup, bootstrap, metrics, runbook |
| [docs/acceptance-report.md](docs/acceptance-report.md) | Status against each acceptance criterion |
| [docs/implementation-plan.md](docs/implementation-plan.md) | Milestone tracker and decisions log |

## Known limitations

This is a working vertical slice, not a production deployment. In particular:

- Chat is request/response. Streaming, cancellation, and budget enforcement are not built.
- Document evidence (TXT, PDF) is not built.
- Aggregate aging figures cite the invoices behind them. Live-mode evals were measured in one run.
- The Keycloak realm is a development realm with demo users and a dev-mode issuer.
- No independent security review, rate limiting, HTTPS setup, or backup restore drill has been done.
- Paginated-screen latency has not been measured under concurrent load.

## Troubleshooting

- **Port 5432 is taken.** Compose maps Postgres to **host port 5433**. A local
  Postgres service often holds 5432, and connecting to it fails with a
  misleading "password authentication failed." Use
  `psql -h localhost -p 5433 -U revenueflow revenueflow`. The container's
  internal port is still 5432.
- **Login fails with an invalid token issuer.** Browser tokens carry the issuer
  `http://localhost:8080/realms/revenueflow`. The API validates against that
  issuer and fetches signing keys from the Docker-network hostname `keycloak:8080`.
  Don't point both at one host.
- **Builds fail with `node.exe: not found` or odd Python errors.** A host
  `node_modules` or `.venv` leaked into a Linux build context. The
  `.dockerignore` files exclude them; keep those in place.
- **Import sits in `queued`.** Check `docker compose logs worker`. The worker
  reclaims a job if its lease expires, so a crashed worker doesn't strand it.

## Repository layout

```
backend/    FastAPI API, worker, domain services, agents, evals, migrations, tests
frontend/   React + TypeScript SPA (Vite)
infra/      Docker Compose, Dockerfiles, Keycloak realm
docs/       Specs, architecture, evaluation, acceptance report, screenshots
```
