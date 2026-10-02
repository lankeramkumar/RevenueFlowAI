# RevenueFlow AI — Product Intent and Acceptance Contract

## Intent

Build a deployable Order-to-Cash Exception Intelligence application that uses uploaded CSV data to help AR analysts, collectors, and order operations teams answer: **Where is cash or billing blocked, what evidence explains the exception, and what should happen next?**

This is a working application, with ingestion, relational data, deterministic calculations, AI investigations, authentication, tests, and deployment documentation. CSV files are the initial source; Oracle connectivity is outside this release. Supporting contracts are agent_architecture.md and synthetic_data_requirements.md. This file is authoritative for business scope; supporting files elaborate implementation and fixtures. Resolve conflicts explicitly rather than silently dropping requirements. Use synthetic data only for the supplied demonstration.

## Outcomes and boundaries

- Identify shipped quantities that remain unbilled beyond a configured threshold.
- Investigate overdue invoice balances and open disputes.
- Identify unapplied receipts and propose evidence-based invoice matches.
- Explain active order holds and connect related customer, shipment, invoice, and receipt records.
- Return evidence identifiers, dataset version, and data freshness with every investigation.
- Let authorized users create, assign, approve, reject, and resolve internal follow-up tasks. Approval records a decision; it does not post a payment or release an ERP hold.
- No ERP writes, outgoing emails, credit decisions, collection calls, or automatic financial transactions in this release.
- Never claim an order hold was caused by an overdue invoice unless a source record establishes that link. Show possible contributing conditions separately from recorded reasons.

## Delivery profile

Use a maintainable modular monolith: React + TypeScript frontend, Python FastAPI backend, PostgreSQL with migrations, and a durable database-backed ingestion worker. Use Docker Compose for reproducible local operation. Use an S3-compatible object-store adapter for raw files and exports, with a local development implementation. Pin tested dependency versions and commit lockfiles. Check current official documentation during implementation rather than inventing API signatures.

Use the Anthropic API behind a provider interface for live tool-calling investigations. Include an explicitly labeled deterministic demo provider that requires no API key. Do not make the UI or data workflows dependent on a live model.

Implement a supervisor that delegates to three specialist agents: Order, AR, and Cash Application. Specialists use typed read-only domain tools. This first release uses agent communication inside one application, not independently deployed A2A protocol services. Follow agent_architecture.md for routing, context, result contracts, budgets, and failure handling. Document an A2A protocol migration path without claiming protocol compliance. MCP hosting remains future scope.

The chatbot is a primary application feature: it must support persisted conversations, contextual follow-up questions, evidence drill-down, cancellation, and visible specialist progress. Use genuine specialist agent modules and live model/tool loops when configured; do not merely relabel one response as several agents. Demo mode uses the same routing and domain tools with deterministic decisions.

## Users and authorization

- Admin: users, configuration, imports, dataset activation, audit access.
- Analyst: read authorized data and investigations; create and update own tasks.
- Approver: analyst abilities plus approve/reject assigned recommendations.
- Viewer: read authorized dashboards and investigations only.

Use established OIDC integration for production authentication, including issuer/audience/signature/expiry validation. A local demo identity provider may be supplied in Compose. Never use a shared hardcoded password or an authentication bypass in production. Restrict data by organization and granted business units in the backend, including tools, exports, search, jobs, and object downloads. Cross-scope object identifiers must not disclose data.

## CSV contract

Provide template downloads and a machine-readable schema manifest. Accept UTF-8 CSV with documented handling for BOM, quoted fields, blanks, and line endings. Dates are ISO 8601 dates; event timestamps include time zones. IDs are strings, preserving leading zeros. Money is exact Decimal in code and NUMERIC in SQL; JSON money values are decimal strings. Currency is an uppercase ISO currency code. Reject unsupported currencies or precision rather than silently rounding. Never sum different currencies.

Every row belongs to an authorized organization and business unit, inherited from validated import metadata; users cannot grant themselves scope by editing a CSV. IDs below are scoped to that organization and dataset version. The manifest specifies required/nullable columns, enums, unique keys, foreign keys, and monetary/quantity precision.

| File | Required columns | Optional columns |
|---|---|---|
| customers.csv | customer_id, account_number, customer_name | payment_terms_days |
| orders.csv | order_id, customer_id, order_date, currency, status | promised_ship_date |
| order_lines.csv | order_line_id, order_id, item_code, ordered_quantity, unit_price, line_amount | cancelled_quantity |
| shipments.csv | shipment_id, order_id, shipment_date, status | delivery_date |
| shipment_lines.csv | shipment_line_id, shipment_id, order_line_id, shipped_quantity | — |
| invoices.csv | invoice_id, customer_id, invoice_date, due_date, currency, invoice_amount, status | order_id |
| invoice_lines.csv | invoice_line_id, invoice_id, line_amount | order_line_id, shipment_line_id, billed_quantity |
| receipts.csv | receipt_id, customer_id, receipt_date, currency, receipt_amount, status | remittance_reference |
| receipt_applications.csv | application_id, receipt_id, invoice_id, applied_amount, application_date, status | — |
| credit_memos.csv | credit_memo_id, customer_id, currency, credit_amount, status | invoice_id |
| credit_applications.csv | credit_application_id, credit_memo_id, invoice_id, applied_amount, application_date, status | — |
| disputes.csv | dispute_id, invoice_id, disputed_amount, reason, status, opened_date | closed_date |
| order_holds.csv | hold_id, order_id, hold_reason, status, applied_date | released_date, linked_invoice_id |

Define supported source statuses in the manifest; do not infer their meaning from arbitrary strings. Payment and credit applications must connect records for the same customer and currency. Validate header/line reconciliation, valid nonnegative quantities, cancelled quantity limits, and valid shipment/order links. Reject negative financial amounts in this first release; reversals are represented by explicit supported statuses and excluded from effective applications. Document this simplified model.

Use order and shipment lines to handle partial shipment/billing. If source links or billed quantities are absent, report insufficient evidence for shipment reconciliation instead of calling the whole order unbilled. Taxes, freight, and rounding may exist in invoice totals; use explicitly classified invoice lines and documented tolerance rules to reconcile them.

## Import lifecycle and data lineage

1. Upload a dataset bundle containing the declared CSV files; optional files may be omitted only where the schema allows it. Show unavailable analyses when evidence is missing.
2. Create a durable import job, store immutable raw files, calculate hashes, and stage rows outside the active dataset.
3. Validate format, schema, statuses, duplicate keys, relationships, currencies, totals, and authorization. Provide actionable row/column errors and downloadable error reports.
4. Present validation and reconciliation summaries for admin activation. Reject invalid bundles atomically; never partially overwrite the active dataset.
5. Activate a validated dataset version transactionally. Retain earlier versions for audit and rollback under a documented retention policy.

Use an idempotency key plus a bundle-content hash. Repeated uploads must not duplicate records or jobs. Worker crashes must be recoverable using leases, bounded retries, and persisted job states. A failed import leaves the previous active version intact. Investigations pin one dataset version so activation during a conversation cannot mix snapshots. Show snapshot date and import time distinctly. CSV snapshots support historical calculations only when their supplied event history is sufficient; otherwise say unavailable.

Retain file hash, import ID, original filename, row number, record ID, and dataset version for evidence. Prevent path traversal, oversized uploads, ZIP bombs if archive import is supported, and spreadsheet formula injection in CSV exports. Do not execute uploaded content.

## Deterministic business calculations

All calculations execute in tested domain services/SQL, never in the language model.

- Invoice open balance = posted invoice amount minus effective posted receipt applications minus effective posted credit applications. Draft/void invoices and reversed applications are excluded according to documented statuses. Disputes annotate a balance; they do not reduce it. Flag inconsistent overapplication; never hide it by clamping values.
- Unapplied receipt amount = effective receipt amount minus effective applications. Cancelled/reversed receipts do not contribute available cash. Unapplied receipt cash is not subtracted from invoice balances until applied.
- Past-due days = max(0, business as-of date minus due date). An invoice due today is not overdue. Aging buckets: not due/due today, 1–30, 31–60, 61–90, 91+ days. Scope all totals by currency, organization, business unit, and dataset.
- Open dispute amount = supported open dispute amounts, with overlapping/excess disputes flagged instead of silently subtracted or double counted.
- Shipped/unbilled exception: posted shipped quantity minus explicitly linked posted billed quantity, after the configurable age threshold. Separate fully unbilled and partially billed quantities. Label quantity × order unit price as an estimate, not recognized revenue or an invoice amount.
- Order holds: display active recorded hold reasons, age, owner if available, and related evidence. Differentiate released holds and cancelled orders.
- Exception prioritization: transparent configurable rules using amount, age, status, and evidence completeness. Label the output an operational priority, not a probability of default or a validated prediction.

Do not combine orders on hold, unbilled shipments, overdue invoices, and unapplied receipts into a single additive “revenue at risk” metric. These can overlap and measure different things. Present separately with explicit definitions.

## Cash match suggestions

Limit candidates to authorized open invoices for the same customer and currency. Use remittance references, explicit invoice IDs, exact amounts, and documented date/tolerance rules. Support single-invoice and bounded multi-invoice combinations; cap candidate count and computational effort. Multiple equally plausible matches must be labeled ambiguous. Record the rule evidence and explain residual amounts. Scores describe rule-based match strength, not calibrated likelihood. No autonomous application of receipts.

## Investigation experience

Support these questions through real data tools:

- Which shipments have been unbilled for more than five days?
- Why is invoice INV-1003 overdue, and is there a dispute?
- Which invoices might match receipt RCP-2001?
- Why is order ORD-3001 on hold?
- Summarize this customer's outstanding invoices, available unapplied cash, disputes, and active holds.

Provide typed tools such as get_customer_summary, get_order_trace, get_invoice_details, list_exceptions, find_receipt_matches, and search_evidence. Tools accept validated IDs and filters, not arbitrary SQL. Apply authorization server-side to every call. Require JSON-schema validation and a structured final response containing summary, findings, evidence references, recommended actions, missing data, and dataset metadata. Evidence references must resolve to actual records or document passages from the pinned dataset; reject fabricated citations.

Use tool results as the source of truth. Explain missing or conflicting data. Distinguish recorded facts from suggestions. Treat CSV text and uploaded documents as untrusted data, including instructions embedded within them. The model has no secrets, shell access, network browsing, general database access, or mutation tool.

Use bounded turns, tool calls, tokens, per-call/overall timeouts, model concurrency, and per-user rate limits. Retry transient provider errors with bounded backoff/jitter; do not retry invalid requests indefinitely. Handle refusal, truncated output, schema failure, and provider outage explicitly. Log usage and tool timing without exposing personal or financial content. Demo answers must be visibly labeled and derived from the same domain services, not canned fabricated results.

## Document evidence

Provide optional TXT/PDF remittance and dispute-evidence upload linked to a customer and optionally invoice/receipt. Enforce file limits and safe parsing. Index by authorized scope and dataset version; return source file and page/section references. A local retrieval implementation is sufficient initially; a vector service is not required. Scanned/image-only PDFs are explicitly marked unsupported unless OCR is actually implemented and tested. Prefer invoice references as structured evidence; do not let narrative similarity override customer/currency restrictions.

## UI requirements

Deliver a polished responsive enterprise interface with:

- Dashboard: separate metrics by currency, aging chart, unbilled quantities/value estimates, unapplied cash, and active holds; visible as-of date and freshness.
- Import center: templates, progress, validation preview, row errors, activation history, and rollback.
- Exception workbench: filters, sort, pagination, priority explanations, and evidence drawers.
- Customer detail: connected order/fulfillment/billing/payment timeline with drill-down.
- Investigation chat: suggested questions, persisted conversations, contextual follow-ups, progress/cancel control, specialist activity summaries, cited findings, and explicit missing-data messages. Show Order/AR/Cash specialist routing without displaying private reasoning. Keep each conversation pinned to its dataset and as-of date; offer an explicit new investigation on a newer dataset. Recheck authorization on every turn and redact inaccessible history after scope changes.
- Action queue: assignment, proposed/approved/rejected/in-progress/resolved states, comments, and immutable audit history; no ERP execution implied.
- Administration: authorized scopes, thresholds, currencies, retention, and provider status.

Include accessible keyboard navigation, labels, focus handling, readable contrast, and complete loading/empty/error states. Keep API keys and provider configuration server-side.

## Operational and security requirements

- Parameterized SQL, strict request/response validation, restricted CORS, secure headers, and documented CSRF protection where cookies are used.
- Authenticated object access, least-privilege database roles, secrets from environment/secret management, log redaction, and no committed credentials.
- Append-only audit events for import activation, investigations, task decisions, authorization changes, and exports. Record actor, time, scope, outcome, and evidence IDs; avoid raw sensitive payloads.
- Structured logs, correlation IDs, health/readiness endpoints, and metrics for job latency/failure, exception counts, tool latency, provider errors, token use, and estimated model cost.
- Database migrations, worker recovery, backup/restore documentation, retention cleanup, and safe rollback procedures.
- CI runs lint/type checks, unit/integration/end-to-end tests, dependency checks, and container builds. Document discovered vulnerabilities and actual remediation status.
- Performance target: on a documented reference machine, a 100,000-row bundle across files completes within two minutes and common paginated SQL-backed screens respond within two seconds at p95 under ten concurrent users. Report measured results; do not claim targets passed without measurement. Live-model latency is measured separately.

## Demo and evaluation data

Follow synthetic_data_requirements.md. Supply a reproducible seeded dataset generator, valid CSV samples, invalid-input fixtures, and independently authored expected outputs. Dates are relative to an explicit --as-of date, not the machine clock. The same seed and arguments must generate identical files/hashes. Include small readable fixtures, a realistic demo bundle, and a 100,000-row load bundle. Synthetic business data must be loaded through the real import pipeline; do not substitute mocked application APIs. Include normal records and at least these cases: partial shipment/invoicing, overdue disputed invoice, exact receipt match, ambiguous match, partial payment, credit application, reversed application, inactive hold, broken foreign key, duplicate row, mixed currency, stale snapshot, insufficient links, and malicious instructions in narrative text.

Include automated evaluation cases with expected balances, exception IDs, valid evidence references, and tool-route expectations. For live AI tests, measure fact support, citation validity, correct abstention, tool selection, latency, and usage. Do not assert exact prose or invent accuracy improvements. Keep live API tests opt-in; deterministic tests run without credentials.

## Acceptance criteria

1. A clean checkout starts via documented Docker Compose commands, applies migrations, and offers a clear demo login and seeded dataset.
2. All primary UI routes operate against persisted backend data; no mock-only dashboard or broken placeholder controls.
3. Valid imports become selectable versions; invalid bundles never change active data; repeat uploads are idempotent; worker restart recovers jobs.
4. Hand-calculated financial and partial-billing fixtures match domain outputs exactly; currency totals remain separate.
5. All five example questions work in demo mode and through the live provider when configured, with actual source references and honest missing-data behavior.
6. Authorization tests prevent cross-organization and cross-business-unit reads through API, tools, exports, object access, and background jobs.
7. Receipt suggestions handle ambiguity and residuals without modifying financial records.
8. Task approvals persist audit history but cannot post cash, email customers, or release ERP holds.
9. Tests, CI, migrations, health checks, container builds, and reproducible setup pass; report the commands and results.
10. README, architecture diagram, data dictionary, CSV templates, API documentation, threat model, evaluation report, and operations/deployment runbook are complete.
11. Supervisor routing sends order-only, AR-only, and cash-match questions to the expected specialists; cross-domain questions combine relevant specialist evidence without duplicate financial totals. Test partial specialist failure, cancellation, budgets, scope isolation, and persisted follow-ups.
12. The seeded generator produces repeatable bundles and a scenario manifest with independently specified expected results; generated records load through real validation. Fixed-as-of boundary tests pass.
13. Live mode uses separate specialist modules with typed inputs/results and bounded provider calls; demo mode exercises the same orchestration contracts without credentials. The UI accurately labels the execution mode. No A2A protocol compliance claim is made for internal transport.

## Production readiness claim

Deliver a production-oriented release candidate. Local tests do not establish production approval. List remaining environment-specific gates: real identity-provider configuration, HTTPS/domain setup, secret provisioning, backup restore drill, representative load tests, security review, and business validation of mappings/rules. No public deployment or external account changes are authorized by this file.

## Future scope

Oracle/OIC ingestion, CDC/incremental imports, approved ERP writeback, multi-currency conversion with auditable FX rates, predictive payment models validated against history, independently deployed A2A protocol agents, and advanced OCR are later releases. Do not let these delay the functioning CSV-first release.
