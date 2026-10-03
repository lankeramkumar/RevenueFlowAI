# Evaluation

Status: covers what has actually been run and measured. No accuracy
claims beyond what's demonstrated below.

## Dataset provenance

The `small` generator profile (`backend/src/revenueflowai/seed/`) produces
two fixed scenarios from `synthetic_data_requirements.md`'s ledger:

- **S01 (partial payment)**: invoice 1,000 USD due D−45; effective receipt
  application 300; effective credit application 100 → expected open
  balance 600, 45 days overdue, bucket 31–60.
- **S09 (currency boundary)**: USD invoice 100 and EUR invoice 200, both
  due D−5 → expected separate per-currency totals, never combined.

Expected values are hand-transcribed directly from
`synthetic_data_requirements.md` into test assertions
(`tests/unit/test_seed_scenarios.py`,
`tests/integration/test_dashboard_aging_summary.py`) — not computed by
the code under test, per that document's own requirement. All names are
fictional; data is marked synthetic in `dataset_manifest.json`.

**Gap**: only 2 of the 17 specified scenarios (S01–S17) have a
corresponding generator fixture. The other 15 have pure-function unit
coverage with independently-authored expected values
(`tests/unit/test_domain_*.py`) but no CSV-bundle-level fixture. S03, S05,
and S07 additionally have direct-ORM-insert integration coverage
(`tests/integration/test_domain_sql_services.py`) that bypasses the CSV
generator. `demo`, `load`, and `invalid` profiles are now implemented
(see `tests/unit/test_load_profile.py`,
`tests/integration/test_demo_profile_activation.py`, and the `invalid`
fixture tests) and exercised against real validation/activation.

## Reproducibility

`tests/unit/test_generator_reproducibility.py` runs the generator twice
with identical arguments and asserts byte-identical CSV output across all
13 files — passing. Manually re-verified via a separate double-run diff
during the Foundation milestone.

## Automated test results (as of this writing)

Run from `backend/`:
```bash
.venv\Scripts\python.exe -m pytest -v
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src
```

- **148 backend tests pass (as of 2026-10-03)** (unit + integration against a live
  Postgres instance — the integration suite auto-skips if no database is
  reachable, so it degrades gracefully without Docker).
- `ruff check .` and `mypy src`: clean, 0 issues.
- Frontend: `npx tsc --noEmit`, `npm run lint` (oxlint), `npm run build` —
  all clean as of the last commit touching frontend code.

Test breakdown: 10 balance/aging, 4 shipment, 4 matching, 2 hold tests
(pure functions); 7 ingestion validator tests; 3 domain SQL-service
tests; 3 ingestion-activation integration tests; 2 aging-summary
integration tests; 4 chat-investigation integration tests; 4 entity-
extraction unit tests; 4 agent-contract tests; 4 agent-transport tests; 3
task-transition tests; 1 model-registration test; 1 health-check test; 1
reproducibility test; 2 S01/S09 scenario tests; 2 cross-org authorization
tests. (Counts will drift as the suite grows — see the live `pytest`
output for the current total.)

## Live-mode evaluation

The live Anthropic planner (`agents/providers/live.py`) was manually
verified against the real running stack with real API calls — not
automated in CI, since intent.md asks that live API tests stay opt-in
(they cost real tokens on every run). Verified cases:

| Question (verbatim) | Expected routing | Result |
|---|---|---|
| "What does our AR aging look like right now across currencies?" | ar / aging_summary | ✅ correct, matched demo-mode's regex result exactly |
| "I got a payment in from this customer, can you figure out what it should pay off? The receipt ID is S01-RCP." | cash / receipt_match | ✅ correctly extracted "S01-RCP" from unstructured prose (the demo regex could not have matched this phrasing) |

Both responses correctly labeled `provider_mode: "live"`, and the
underlying financial figures came from the same deterministic domain
services as demo mode — Claude only selected which specialist to
dispatch and extracted the entity ID; it did not compute or state a
number itself.

**Not measured**: latency distribution, token usage per call, cost per
investigation, citation-validity rate against adversarial input, or
correct-abstention rate under live mode at scale. These require a larger
evaluation harness that doesn't exist yet (tracked as a Milestone 6 gap).

## Performance

**Import target: measured, passes.** intent.md: "a 100,000-row bundle
across files completes within two minutes." The `load` generator profile
produced a 96,666-row bundle (its sizing logic targets, not guarantees,
an exact row count — see `seed/load.py`) in 0.33s, and
`ingestion.activation.validate_and_activate` processed the full bundle
(validation + load into Postgres) in **17.98 seconds** (5,377 rows/sec)
— well under the 2-minute target. Measured directly against the real
`validate_and_activate` code path (not a simulation) on the build
machine: Windows 11, Postgres 16 in Docker via WSL2, no other load on
the system. Not yet measured through the full HTTP upload → worker →
activation path (this measurement calls the activation function
directly) or on a documented "reference machine" in the formal sense
intent.md implies — this is one real data point, not a calibrated
benchmark.

**Paginated-screen target: not measured.** intent.md's "p95 under 2
seconds at 10 concurrent users" requires a load-testing tool driving
concurrent HTTP requests against a running backend, which hasn't been
set up. Reporting this as unmeasured rather than asserting it passes.

## Known limitations

- Demo-mode routing is regex/keyword-based and can double-dispatch on
  compound questions (e.g. a question containing both "overdue" and
  "aging" triggers two AR tasks, one of which may return
  `needs_clarification` as harmless noise alongside a successful one).
  Observed directly during live verification; not yet a defect any test
  asserts against, since the resulting behavior is not incorrect — just
  imprecise classification by design (demo mode is deliberately simple).
- Live-mode planning is a single bounded classification call, not an
  open-ended tool-calling loop — see `docs/architecture.md` for why this
  is an explicit simplification, not a hidden gap.

## Investigation evals (2026-10-03)

`python -m revenueflowai.evals` runs ten hand-specified cases
(`backend/src/revenueflowai/evals/cases.py`) through the real Supervisor and
specialists against an activated dataset. Each case is scored on routing
(exact domain:intent set), entities, required finding text, abstention
(no fabricated findings, reason recorded), and citation validity (every
evidence reference resolves to a stored record). Exit status is 1 below the
thresholds, so the command can gate a pipeline.

| Mode | Cases | Pass rate | Citation validity | Notes |
|---|---|---|---|---|
| Demo (deterministic) | 10 | 1.00 | 1.00 | Enforced in CI by `tests/integration/test_evals_small_suite.py` |
| Live (Anthropic planner, one run) | 10 | 1.00 | 1.00 | p50 ≈ 812 ms per case; n=1 run, LLM output can vary |

Live mode initially failed two cases: a weather question dispatched a
customer summary, and a prompt-injection request produced aging figures. Both
are fixed (explicit decline and no-command rules in the planner prompt, plus a
deterministic guard that drops customer summaries without a customer ID), with
unit tests in `tests/unit/test_live_planner_guards.py`.

Not measured: abstention and routing over a larger, adversarial question set;
cost per investigation; and live-mode evals in CI (they are opt-in because
they spend tokens).

## Observability (2026-10-03)

- Every request has an `X-Request-ID` (kept if it is a safe token, otherwise
  generated) that is echoed back and bound to every log line for that request.
- One structured access log per request (method, route template, status,
  duration). Investigations log one `investigation.completed` event with mode,
  outcome, specialists, and counts.
- `GET /metrics` (Prometheus text): `http_requests_total`,
  `http_request_duration_seconds`, `investigations_total{mode,outcome}`,
  `investigation_duration_seconds`, `specialist_results_total{domain,status}`.
  Labels use route templates, not raw paths, so cardinality stays bounded.
- The worker has its own process and does not yet export metrics; job-level
  metrics are a gap.
