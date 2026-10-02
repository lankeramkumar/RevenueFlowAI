"""CSV column order for each supported file, per intent.md's CSV contract.

Single source of truth for the generator (Milestone 1+) and the ingestion
validator (Milestone 2) — both must agree on required/optional columns.
"""

CSV_COLUMNS: dict[str, list[str]] = {
    "customers.csv": [
        "customer_id", "account_number", "customer_name", "payment_terms_days",
    ],
    "orders.csv": [
        "order_id", "customer_id", "order_date", "currency", "status", "promised_ship_date",
    ],
    "order_lines.csv": [
        "order_line_id", "order_id", "item_code", "ordered_quantity", "cancelled_quantity",
        "unit_price", "line_amount",
    ],
    "shipments.csv": [
        "shipment_id", "order_id", "shipment_date", "status", "delivery_date",
    ],
    "shipment_lines.csv": [
        "shipment_line_id", "shipment_id", "order_line_id", "shipped_quantity",
    ],
    "invoices.csv": [
        "invoice_id", "customer_id", "order_id", "invoice_date", "due_date", "currency",
        "invoice_amount", "status",
    ],
    "invoice_lines.csv": [
        "invoice_line_id", "invoice_id", "order_line_id", "shipment_line_id",
        "billed_quantity", "line_amount",
    ],
    "receipts.csv": [
        "receipt_id", "customer_id", "receipt_date", "currency", "receipt_amount", "status",
        "remittance_reference",
    ],
    "receipt_applications.csv": [
        "application_id", "receipt_id", "invoice_id", "applied_amount", "application_date",
        "status",
    ],
    "credit_memos.csv": [
        "credit_memo_id", "customer_id", "invoice_id", "currency", "credit_amount", "status",
    ],
    "credit_applications.csv": [
        "credit_application_id", "credit_memo_id", "invoice_id", "applied_amount",
        "application_date", "status",
    ],
    "disputes.csv": [
        "dispute_id", "invoice_id", "disputed_amount", "reason", "status", "opened_date",
        "closed_date",
    ],
    "order_holds.csv": [
        "hold_id", "order_id", "hold_reason", "status", "applied_date", "released_date",
        "linked_invoice_id",
    ],
}

REQUIRED_FILES = tuple(CSV_COLUMNS.keys())
