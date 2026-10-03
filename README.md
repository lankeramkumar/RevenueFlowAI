# RevenueFlow AI

CSV-first Order-to-Cash Exception Intelligence application: upload CSV
data, investigate where cash or billing is blocked, and chat with a
Supervisor + Order/AR/Cash-Application agent team for evidence-based
answers. Full product spec: [docs/intent.md](docs/intent.md),
[docs/agent_architecture.md](docs/agent_architecture.md),
[docs/synthetic_data_requirements.md](docs/synthetic_data_requirements.md).
Build status and milestone tracking: [docs/implementation-plan.md](docs/implementation-plan.md).
Acceptance-criteria status: [docs/acceptance-report.md](docs/acceptance-report.md).

**Status:** Foundation, Ingestion, Domain logic, and the core of the
Investigation chat/agent layer are built and verified live. Document
evidence, SSE streaming, the `demo`/`load`/`invalid` generator profiles,
and several operational UI screens (customer timeline, administration)
are not yet built — see the implementation plan and acceptance report for
exactly what's done vs. pending.

## Documentation

| Doc | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System diagram, component responsibilities, request flow |
| [docs/data-dictionary.md](docs/data-dictionary.md) | Full CSV schema reference (all 13 files) |
| [docs/security.md](docs/security.md) | Threat model, auth/authz posture, current gates |
| [docs/evaluation.md](docs/evaluation.md) | Test results, dataset provenance, live-mode verification |
| [docs/operations.md](docs/operations.md) | Deployment, migrations, worker recovery, backup/retention gates |
| [docs/implementation-plan.md](docs/implementation-plan.md) | Live milestone tracker (read first when resuming work) |
| [docs/acceptance-report.md](docs/acceptance-report.md) | Status against every numbered acceptance criterion |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (WSL2 backend on Windows) — for the full stack (Postgres, LocalStack S3, Keycloak, backend, worker, frontend)
- Python 3.11+ and Node 22+ — only needed for running backend/frontend outside Docker

## Clean-checkout startup (once Docker Desktop is installed)

```bash
cd infra
docker compose up --build
```

This starts Postgres, LocalStack (S3-compatible object storage), Keycloak
(with a seeded demo realm), the FastAPI backend (migrations apply
automatically on container start), the import worker, and the frontend.

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Keycloak admin console: http://localhost:8080 (admin/admin)
- LocalStack S3 endpoint: http://localhost:4566 (credentials: test/test)

### Demo login

Seeded in the Keycloak realm (`infra/keycloak/revenueflow-realm.json`) — demo-only credentials, not valid outside this local Compose environment:

| Username | Password | Role |
|---|---|---|
| demo-admin | DemoPass123! | Admin |
| demo-analyst | DemoPass123! | Analyst |
| demo-approver | DemoPass123! | Approver |
| demo-viewer | DemoPass123! | Viewer |

## Running backend/frontend outside Docker (development)

Backend:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env   # then fill in DATABASE_URL etc. for your local setup
pytest
ruff check .
mypy src
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

## Generating synthetic sample data

```bash
cd backend
.venv\Scripts\python.exe -m revenueflowai.seed generate --profile small --seed 42 --as-of 2026-10-02 --output ../sample-data/small
```

Only the `small` profile (fixed scenarios S01, S09) is implemented so far;
`demo`/`load`/`invalid` profiles and the remaining S02–S17 scenarios land
in later milestones (see [docs/implementation-plan.md](docs/implementation-plan.md)).

## Troubleshooting

- **Postgres on a non-default port**: Compose maps the `db` service to
  **host port 5433**, not 5432 — a locally installed Postgres service can
  already be bound to 5432, and connecting to the wrong instance fails
  with a confusing "password authentication failed" rather than a clear
  "can't connect." `psql -h localhost -p 5433 -U revenueflow revenueflow`
  reaches the Compose database; the container's *internal* port is still
  5432 (only the host-side mapping changed).
