# RevenueFlow AI

CSV-first Order-to-Cash Exception Intelligence application. Full product
spec lives in `docs/intent.md`, `docs/agent_architecture.md`,
`docs/synthetic_data_requirements.md`; build instructions in
`docs/claude_build_prompt.md`. Live build status/milestones/decisions are
tracked in `docs/implementation-plan.md` — read that first when resuming
work here. Workspace-wide conventions live in the parent `CLAUDE.md`
(`C:\MyProjects\CLAUDE.md`).

## Layout

- `backend/` — FastAPI + SQLAlchemy/Alembic + worker (Python, `src/revenueflowai/`)
- `frontend/` — Vite + React + TypeScript SPA
- `infra/` — Docker Compose, Dockerfiles, Keycloak realm config
- `sample-data/` — generator output (gitignored except small fixtures)
- `docs/` — product spec contracts + generated deliverables

## Running things

Backend (from `backend/`, venv at `backend/.venv`):
- Tests: `.venv\Scripts\python.exe -m pytest -v`
- Lint: `.venv\Scripts\python.exe -m ruff check .`
- Type-check: `.venv\Scripts\python.exe -m mypy src`
- Generate sample data: `.venv\Scripts\python.exe -m revenueflowai.seed generate --profile small --seed 42 --as-of 2026-10-02 --output ../sample-data/small`

Frontend (from `frontend/`):
- Lint: `npm run lint`
- Type-check: `npx tsc -b --noEmit`
- Build: `npm run build`

Full stack (from `infra/`, requires Docker Desktop):
- `docker compose up --build`

## Notes

No Docker/PostgreSQL is installed on the primary dev machine as of this
writing — backend DB-dependent paths (migrations against a live DB, Compose
boot, Keycloak login) are verified once Docker Desktop is available; see
`docs/implementation-plan.md` for current verification status.
