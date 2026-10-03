# Data Dictionary

The machine-readable source of truth is
`backend/src/revenueflowai/ingestion/manifest.py` (required columns, primary
keys, status vocabulary, currency rules, foreign-key rules) — this document
is a human-readable mirror of it, plus the full column set each entity
table stores (including optional columns the manifest doesn't require but
the loader populates). If this document and the manifest ever disagree,
the manifest is authoritative; it's also what `GET /api/v1/templates/{file}`
serves as downloadable CSV templates.

All money and quantity columns are `NUMERIC(18,4)` in Postgres and
`decimal.Decimal` in Python — never `float`. Money is a decimal string at
every API boundary. IDs are strings, preserving leading zeros. Dates are
ISO 8601.

## Status vocabulary

| File | Status column | Supported values |
|---|---|---|
| orders.csv | status | `open`, `fulfilled`, `cancelled` |
| shipments.csv | status | `shipped`, `delivered`, `cancelled` |
| invoices.csv | status | `draft`, `posted`, `void` |
| receipts.csv | status | `posted`, `cancelled` |
| receipt_applications.csv | status | `posted`, `reversed` |
| credit_memos.csv | status | `posted`, `void` |
| credit_applications.csv | status | `posted`, `reversed` |
| disputes.csv | status | `open`, `closed` |
| order_holds.csv | status | `active`, `released` |

Only `posted` invoices/receipts/applications are "effective" for balance
calculations; `draft`/`void`/`reversed` never contribute. Negative amounts
are rejected at ingestion — reversals use the `reversed` status, not a
negative value.

## Supported currencies

`USD`, `EUR`, `GBP` (see `SUPPORTED_CURRENCIES` in `manifest.py`). An
unsupported currency code is a validation error, not a silent pass-through.

## CSV files

### customers.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| customer_id | yes | string | primary key |
| account_number | no | string | |
| customer_name | yes | string | |
| payment_terms_days | no | integer | |

### orders.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| order_id | yes | string | primary key |
| customer_id | yes | string | FK → customers.customer_id |
| order_date | yes | date | |
| currency | yes | string(3) | |
| status | yes | string | see vocabulary above |
| promised_ship_date | no | date | |

### order_lines.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| order_line_id | yes | string | primary key |
| order_id | yes | string | FK → orders.order_id |
| item_code | yes | string | |
| ordered_quantity | yes | decimal | ≥ 0 |
| cancelled_quantity | no | decimal | ≥ 0, default 0 |
| unit_price | yes | decimal | ≥ 0 |
| line_amount | yes | decimal | ≥ 0 |

### shipments.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| shipment_id | yes | string | primary key |
| order_id | yes | string | FK → orders.order_id |
| shipment_date | yes | date | |
| status | yes | string | see vocabulary above |
| delivery_date | no | date | |

### shipment_lines.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| shipment_line_id | yes | string | primary key |
| shipment_id | yes | string | FK → shipments.shipment_id |
| order_line_id | no | string | FK → order_lines.order_line_id; absence means "insufficient evidence" for billing reconciliation, not "fully unbilled" |
| shipped_quantity | yes | decimal | ≥ 0 |

### invoices.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| invoice_id | yes | string | primary key |
| customer_id | yes | string | FK → customers.customer_id |
| order_id | no | string | FK → orders.order_id |
| invoice_date | yes | date | |
| due_date | yes | date | |
| currency | yes | string(3) | |
| invoice_amount | yes | decimal | ≥ 0 |
| status | yes | string | see vocabulary above |

### invoice_lines.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| invoice_line_id | yes | string | primary key |
| invoice_id | yes | string | FK → invoices.invoice_id |
| order_line_id | no | string | FK → order_lines.order_line_id |
| shipment_line_id | no | string | FK → shipment_lines.shipment_line_id |
| billed_quantity | no | decimal | ≥ 0 |
| line_amount | yes | decimal | ≥ 0 |

### receipts.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| receipt_id | yes | string | primary key |
| customer_id | yes | string | FK → customers.customer_id |
| receipt_date | yes | date | |
| currency | yes | string(3) | |
| receipt_amount | yes | decimal | ≥ 0 |
| status | yes | string | see vocabulary above |
| remittance_reference | no | string | free text, often an invoice ID; used as match evidence only, never trusted blindly |

### receipt_applications.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| application_id | yes | string | primary key |
| receipt_id | yes | string | FK → receipts.receipt_id |
| invoice_id | yes | string | FK → invoices.invoice_id |
| applied_amount | yes | decimal | ≥ 0 |
| application_date | yes | date | |
| status | yes | string | see vocabulary above |

### credit_memos.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| credit_memo_id | yes | string | primary key |
| customer_id | yes | string | FK → customers.customer_id |
| invoice_id | no | string | FK → invoices.invoice_id |
| currency | yes | string(3) | |
| credit_amount | yes | decimal | ≥ 0 |
| status | yes | string | see vocabulary above |

### credit_applications.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| credit_application_id | yes | string | primary key |
| credit_memo_id | yes | string | FK → credit_memos.credit_memo_id |
| invoice_id | yes | string | FK → invoices.invoice_id |
| applied_amount | yes | decimal | ≥ 0 |
| application_date | yes | date | |
| status | yes | string | see vocabulary above |

### disputes.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| dispute_id | yes | string | primary key |
| invoice_id | yes | string | FK → invoices.invoice_id |
| disputed_amount | yes | decimal | ≥ 0 |
| reason | yes | string | free text, treated as untrusted narrative data, never as instructions |
| status | yes | string | see vocabulary above |
| opened_date | yes | date | |
| closed_date | no | date | |

A dispute **annotates** an invoice's balance; it never reduces it
(`domain/balances.py::annotate_dispute`).

### order_holds.csv
| Column | Required | Type | Notes |
|---|---|---|---|
| hold_id | yes | string | primary key |
| order_id | yes | string | FK → orders.order_id |
| hold_reason | yes | string | |
| status | yes | string | see vocabulary above |
| applied_date | yes | date | |
| released_date | no | date | |
| linked_invoice_id | no | string | FK → invoices.invoice_id; only set when a source record explicitly establishes the link — never inferred |

## Lineage and scope columns (every table above)

| Column | Type | Notes |
|---|---|---|
| id | UUID | surrogate primary key |
| organization_id | UUID | tenant scope |
| business_unit_id | UUID | tenant scope |
| dataset_version_id | UUID | which activated snapshot this row belongs to |
| import_job_id | UUID | which upload produced this row |
| source_filename | string | which CSV file within the bundle |
| source_row_number | integer | 1-based row number within that file |
| created_at / updated_at | timestamp | |
