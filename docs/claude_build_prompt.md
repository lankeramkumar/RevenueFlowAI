# Claude Code Build Prompt — RevenueFlow AI

Copy the text below into Claude Code after placing intent.md, agent_architecture.md, and synthetic_data_requirements.md in the repository root.

---

Build **RevenueFlow AI**, the CSV-first Order-to-Cash Exception Intelligence application specified in @intent.md, with the agent contracts in @agent_architecture.md and dataset requirements in @synthetic_data_requirements.md. Treat intent.md as the product intent, scope boundary, data contract, and acceptance contract.

Act as a senior full-stack engineer and application architect. Implement the application and verify it end to end. Do not stop after writing a plan, architecture, scaffolding, or mocked UI. Deliver a production-oriented release candidate, and report evidence for readiness rather than asserting “production ready.”

## First actions

1. Read repository instructions, AGENTS.md/CLAUDE.md when present, intent.md, agent_architecture.md, synthetic_data_requirements.md, existing code, and tests. Preserve unrelated work. If this is an existing application, adapt the implementation to its established stack unless that prevents the acceptance criteria; record necessary deviations.
2. For an empty repository, use React/TypeScript, FastAPI, PostgreSQL, a durable database-backed worker, Docker Compose, object storage adapters, and an Anthropic provider interface as specified in intent.md.
3. Inspect installed tools and verify relevant SDK/library APIs using current official documentation. Pin compatible versions and commit lockfiles. Never invent framework or provider APIs.
4. Write docs/implementation-plan.md with milestones, architectural decisions, risks, and requirement-to-test mapping. Proceed to implementation without waiting for approval on routine reversible choices. Ask only for information that is essential and cannot be safely represented by configuration. No paid resource creation, public deployment, or external messaging is requested.

## Implementation sequence

Complete each milestone as a functioning vertical slice, with meaningful verification before expanding it:

1. **Foundation:** repository structure, database migrations, authentication/authorization, Compose, environment templates, health checks, CI, sample data generator.
2. **Ingestion:** CSV contracts/templates, raw-file storage, durable import jobs, staging validation, errors, idempotency, atomic activation, lineage, rollback, and import UI.
3. **Domain logic:** exact balances, currency-separated aging, disputes, partial shipment/billing reconciliation, holds, receipt match proposals, deterministic fixtures, and APIs.
4. **Operational interface:** dashboard, exception workbench, customer timeline, evidence drawers, and action-review queue connected to persisted data.
5. **Investigation:** supervisor routing, separate Order/AR/Cash Application specialist modules, typed read-only tools, bounded agent execution, Anthropic integration, schema/citation validation, labeled credential-free demo provider, optional document evidence search, persisted chat with follow-ups, specialist progress, and cancellation.
6. **Hardening and handoff:** scope isolation tests, worker crash recovery, prompt-injection fixtures, observability, performance measurement, deployment/backup runbook, architecture documentation, and evaluation report.

## Non-negotiable implementation rules

- Read intent.md completely; implement its contracts rather than approximating them from this summary.
- Calculate money, aging, and exceptions in deterministic domain code/SQL. Use Decimal/NUMERIC and decimal strings at API boundaries. Never rely on LLM arithmetic or silently combine currencies.
- Preserve line-level shipment/invoice links so partial fulfillment is handled correctly. Abstain when the data cannot prove a linkage.
- A dispute does not reduce an invoice balance. Unapplied cash does not settle an invoice. Reversed applications do not count. Do not add overlapping exception measures into one financial total.
- Scope every API, tool, document lookup, export, object access, and job to authorized organization/business units. Authentication without data authorization is incomplete.
- Do not expose arbitrary SQL, shell commands, database credentials, or mutation tools to the model. Treat uploaded narrative content as untrusted evidence.
- Implement the supervisor and three specialists using the typed internal communication contract. Specialists cannot call other agents or recursively delegate. Do not claim A2A protocol compliance: independent protocol endpoints are future scope. Test routing and aggregation, including partial failures and authorization.
- Persist import jobs, dataset versions, task decisions, and audits. Do not use process-memory state for durable business workflows.
- Use real live-provider tool calling when configured. The credential-free demo provider must be labeled and derive responses from real domain services. No canned balance answers or fake citations.
- Validate final responses and evidence IDs. Handle unknown IDs, ambiguity, missing records, model refusal, timeout, provider outage, and truncated output visibly.
- Approval means an internal reviewed recommendation. Never imply a receipt was applied, a hold was released, or an email was sent.
- Document all simplified accounting/status assumptions. Do not fabricate Oracle compatibility or predictive accuracy.
- Use secure production defaults. Demo auth/configuration must fail closed outside the documented demo environment. No hardcoded secrets; no API key in browser code.
- Provide useful progress updates and maintain a checklist. Fix discovered defects and rerun affected checks. If a check cannot run, state why and provide the exact command; do not report it as passed.

## Repository deliverables

- Complete frontend, backend, worker, storage adapters, migrations, and Docker Compose setup.
- .env.example containing names and safe placeholders only, plus documented provider/auth configuration.
- intent.md, agent_architecture.md, and synthetic_data_requirements.md retained as contracts.
- Separate supervisor and specialist modules with typed schemas, routing tests, cancellation/budget tests, and scope propagation tests.
- A deterministic synthetic-data CLI, scenario manifest, small fixtures, realistic demo bundle, load profile, and independent expected-result tests.
- README.md with prerequisites, clean-checkout startup, login, seed/import workflow, sample questions, live-provider setup, and troubleshooting.
- docs/architecture.md with a concise Mermaid architecture and design decisions.
- docs/data-dictionary.md, machine-readable CSV schemas, downloadable templates, valid sample bundle, invalid fixtures, and deterministic generator.
- docs/security.md covering scope isolation, untrusted data, secrets, auth, and remaining environment-specific security gates.
- docs/operations.md with deployment, migrations, health/metrics, worker recovery, retention, backup/restore, and rollback procedures.
- docs/evaluation.md with dataset provenance, expected results, actual test results, live-model limitations, measured performance, and model usage when available.
- Automated tests and CI workflow. OpenAPI documentation and meaningful end-to-end browser coverage.
- docs/acceptance-report.md mapping every numbered acceptance criterion to implementation, evidence, and any unresolved gap.

## Verification before completion

Run the clean-start workflow and demonstrate these journeys:

1. Login; download CSV templates; import a valid bundle; review/activate it; see correct dashboard data.
2. Import an invalid bundle; inspect row errors; confirm previous active data is unchanged.
3. Repeat an import; confirm idempotency. Restart a worker during a job; confirm safe recovery.
4. Investigate an overdue disputed invoice, a partly billed shipment, an exact receipt match, an ambiguous match, and an active hold. Open cited evidence.
5. Create an internal follow-up task; approve/reject it with an authorized user; verify audit history and absence of external financial changes.
6. Attempt cross-scope access through API/tool/export/document/job paths; verify denial.
7. Run without a model API key in labeled demo mode; run optional live tests if a key is available; simulate provider failure.
8. Test routing, contextual follow-ups, partial agent failures, cancellation, and a new dataset activated during a conversation. Verify preserved scope/dataset/as-of context and total budgets.
9. Run calculation, integration, authorization, ingestion/recovery, orchestration, synthetic-data reproducibility, and browser tests; lint/type-check; build containers; measure the documented performance target.

Do not leave critical-path TODOs, disconnected screens, placeholder endpoints, fabricated test output, or unsupported “production ready” claims. Optional future features may be documented as out of scope. Record any unmet mandatory criteria explicitly.

## Final response

Report what was built, exact startup commands, verified journeys, actual check results, measured limitations, required environment configuration, and remaining production gates. Include the acceptance-report path and known gaps. If the repository is under version control, summarize the changes without committing or pushing unless separately authorized.

Start by inspecting the repository and reading all three contract files, then execute the plan through verification. Generate the synthetic CSV files yourself; the user does not need to provide Oracle access or business data.
