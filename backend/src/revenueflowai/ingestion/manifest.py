"""Machine-readable schema manifest: required/optional columns, primary keys,
status vocabulary, and currency rules per CSV file — the single source of
truth the validator (this milestone) and the generator (seed/schema.py)
must both agree with.
"""

from dataclasses import dataclass

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "customers.csv": ["customer_id", "account_number", "customer_name"],
    "orders.csv": ["order_id", "customer_id", "order_date", "currency", "status"],
    "order_lines.csv": [
        "order_line_id", "order_id", "item_code", "ordered_quantity", "unit_price", "line_amount",
    ],
    "shipments.csv": ["shipment_id", "order_id", "shipment_date", "status"],
    "shipment_lines.csv": ["shipment_line_id", "shipment_id", "order_line_id", "shipped_quantity"],
    "invoices.csv": [
        "invoice_id", "customer_id", "invoice_date", "due_date", "currency", "invoice_amount", "status",
    ],
    "invoice_lines.csv": ["invoice_line_id", "invoice_id", "line_amount"],
    "receipts.csv": ["receipt_id", "customer_id", "receipt_date", "currency", "receipt_amount", "status"],
    "receipt_applications.csv": [
        "application_id", "receipt_id", "invoice_id", "applied_amount", "application_date", "status",
    ],
    "credit_memos.csv": ["credit_memo_id", "customer_id", "currency", "credit_amount", "status"],
    "credit_applications.csv": [
        "credit_application_id", "credit_memo_id", "invoice_id", "applied_amount",
        "application_date", "status",
    ],
    "disputes.csv": ["dispute_id", "invoice_id", "disputed_amount", "reason", "status", "opened_date"],
    "order_holds.csv": ["hold_id", "order_id", "hold_reason", "status", "applied_date"],
}

PRIMARY_KEY: dict[str, str] = {
    "customers.csv": "customer_id",
    "orders.csv": "order_id",
    "order_lines.csv": "order_line_id",
    "shipments.csv": "shipment_id",
    "shipment_lines.csv": "shipment_line_id",
    "invoices.csv": "invoice_id",
    "invoice_lines.csv": "invoice_line_id",
    "receipts.csv": "receipt_id",
    "receipt_applications.csv": "application_id",
    "credit_memos.csv": "credit_memo_id",
    "credit_applications.csv": "credit_application_id",
    "disputes.csv": "dispute_id",
    "order_holds.csv": "hold_id",
}

STATUS_COLUMN: dict[str, str] = {
    "orders.csv": "status",
    "shipments.csv": "status",
    "invoices.csv": "status",
    "receipts.csv": "status",
    "receipt_applications.csv": "status",
    "credit_memos.csv": "status",
    "credit_applications.csv": "status",
    "disputes.csv": "status",
    "order_holds.csv": "status",
}

SUPPORTED_STATUSES: dict[str, set[str]] = {
    "orders.csv": {"open", "fulfilled", "cancelled"},
    "shipments.csv": {"shipped", "delivered", "cancelled"},
    "invoices.csv": {"draft", "posted", "void"},
    "receipts.csv": {"posted", "cancelled"},
    "receipt_applications.csv": {"posted", "reversed"},
    "credit_memos.csv": {"posted", "void"},
    "credit_applications.csv": {"posted", "reversed"},
    "disputes.csv": {"open", "closed"},
    "order_holds.csv": {"active", "released"},
}

# Columns holding monetary/quantity amounts that intent.md requires to be
# nonnegative in this first release (reversals use explicit statuses, not
# negative amounts).
NONNEGATIVE_AMOUNT_COLUMNS: dict[str, list[str]] = {
    "order_lines.csv": ["ordered_quantity", "cancelled_quantity", "unit_price", "line_amount"],
    "shipment_lines.csv": ["shipped_quantity"],
    "invoices.csv": ["invoice_amount"],
    "invoice_lines.csv": ["billed_quantity", "line_amount"],
    "receipts.csv": ["receipt_amount"],
    "receipt_applications.csv": ["applied_amount"],
    "credit_memos.csv": ["credit_amount"],
    "credit_applications.csv": ["applied_amount"],
    "disputes.csv": ["disputed_amount"],
}

# Every column that must parse as an ISO-8601 date (empty is fine for
# optional columns; required-ness is governed by REQUIRED_COLUMNS).
DATE_COLUMNS: dict[str, list[str]] = {
    "orders.csv": ["order_date", "promised_ship_date"],
    "shipments.csv": ["shipment_date", "delivery_date"],
    "invoices.csv": ["invoice_date", "due_date"],
    "receipts.csv": ["receipt_date"],
    "receipt_applications.csv": ["application_date"],
    "credit_applications.csv": ["application_date"],
    "disputes.csv": ["opened_date", "closed_date"],
    "order_holds.csv": ["applied_date", "released_date"],
}

# Money/quantity amounts beyond 4 decimal places exceed this release's
# NUMERIC(18,4) precision and must be rejected, not silently rounded.
MAX_DECIMAL_PLACES = 4

CURRENCY_COLUMN: dict[str, str] = {
    "orders.csv": "currency",
    "invoices.csv": "currency",
    "receipts.csv": "currency",
    "credit_memos.csv": "currency",
}

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP"}


@dataclass(frozen=True)
class ForeignKeyRule:
    file: str
    column: str
    references_file: str
    references_column: str
    required: bool = True


FOREIGN_KEYS: list[ForeignKeyRule] = [
    ForeignKeyRule("orders.csv", "customer_id", "customers.csv", "customer_id"),
    ForeignKeyRule("order_lines.csv", "order_id", "orders.csv", "order_id"),
    ForeignKeyRule("shipments.csv", "order_id", "orders.csv", "order_id"),
    ForeignKeyRule("shipment_lines.csv", "shipment_id", "shipments.csv", "shipment_id"),
    ForeignKeyRule(
        "shipment_lines.csv", "order_line_id", "order_lines.csv", "order_line_id", required=False
    ),
    ForeignKeyRule("invoices.csv", "customer_id", "customers.csv", "customer_id"),
    ForeignKeyRule("invoices.csv", "order_id", "orders.csv", "order_id", required=False),
    ForeignKeyRule("invoice_lines.csv", "invoice_id", "invoices.csv", "invoice_id"),
    ForeignKeyRule(
        "invoice_lines.csv", "order_line_id", "order_lines.csv", "order_line_id", required=False
    ),
    ForeignKeyRule(
        "invoice_lines.csv", "shipment_line_id", "shipment_lines.csv", "shipment_line_id", required=False
    ),
    ForeignKeyRule("receipts.csv", "customer_id", "customers.csv", "customer_id"),
    ForeignKeyRule("receipt_applications.csv", "receipt_id", "receipts.csv", "receipt_id"),
    ForeignKeyRule("receipt_applications.csv", "invoice_id", "invoices.csv", "invoice_id"),
    ForeignKeyRule("credit_memos.csv", "customer_id", "customers.csv", "customer_id"),
    ForeignKeyRule("credit_memos.csv", "invoice_id", "invoices.csv", "invoice_id", required=False),
    ForeignKeyRule("credit_applications.csv", "credit_memo_id", "credit_memos.csv", "credit_memo_id"),
    ForeignKeyRule("credit_applications.csv", "invoice_id", "invoices.csv", "invoice_id"),
    ForeignKeyRule("disputes.csv", "invoice_id", "invoices.csv", "invoice_id"),
    ForeignKeyRule("order_holds.csv", "order_id", "orders.csv", "order_id"),
    ForeignKeyRule(
        "order_holds.csv", "linked_invoice_id", "invoices.csv", "invoice_id", required=False
    ),
]
