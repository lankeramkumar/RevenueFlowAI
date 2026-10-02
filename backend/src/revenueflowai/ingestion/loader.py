"""Loads a validated CSV bundle into the scoped entity tables for a new
dataset version. Assumes `validator.validate_bundle` already passed —
this module does not re-validate, it trusts the caller's ordering.
"""

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.models.entities import (
    CreditApplication,
    CreditMemo,
    Customer,
    Dispute,
    Invoice,
    InvoiceLine,
    Order,
    OrderHold,
    OrderLine,
    Receipt,
    ReceiptApplication,
    Shipment,
    ShipmentLine,
)


def _dec(row: dict[str, str], key: str) -> Decimal:
    return Decimal(row[key])


def _opt_dec(row: dict[str, str], key: str) -> Decimal | None:
    value = row.get(key, "")
    return Decimal(value) if value else None


def _opt_str(row: dict[str, str], key: str) -> str | None:
    value = row.get(key, "")
    return value or None


def _opt_int(row: dict[str, str], key: str) -> int | None:
    value = row.get(key, "")
    return int(value) if value else None


def _date(row: dict[str, str], key: str) -> date:
    return date.fromisoformat(row[key])


def _opt_date(row: dict[str, str], key: str) -> date | None:
    value = row.get(key, "")
    return date.fromisoformat(value) if value else None


@dataclass(frozen=True)
class FileLoader:
    model: type
    build_kwargs: Callable[[dict[str, str]], dict[str, Any]]


FILE_LOADERS: dict[str, FileLoader] = {
    "customers.csv": FileLoader(Customer, lambda r: {
        "external_id": r["customer_id"], "account_number": _opt_str(r, "account_number"),
        "customer_name": r["customer_name"], "payment_terms_days": _opt_int(r, "payment_terms_days"),
    }),
    "orders.csv": FileLoader(Order, lambda r: {
        "external_id": r["order_id"], "customer_external_id": r["customer_id"],
        "order_date": _date(r, "order_date"), "currency": r["currency"], "status": r["status"],
        "promised_ship_date": _opt_date(r, "promised_ship_date"),
    }),
    "order_lines.csv": FileLoader(OrderLine, lambda r: {
        "external_id": r["order_line_id"], "order_external_id": r["order_id"],
        "item_code": r["item_code"], "ordered_quantity": _dec(r, "ordered_quantity"),
        "cancelled_quantity": _opt_dec(r, "cancelled_quantity") or Decimal("0"),
        "unit_price": _dec(r, "unit_price"), "line_amount": _dec(r, "line_amount"),
    }),
    "shipments.csv": FileLoader(Shipment, lambda r: {
        "external_id": r["shipment_id"], "order_external_id": r["order_id"],
        "shipment_date": _date(r, "shipment_date"), "status": r["status"],
        "delivery_date": _opt_date(r, "delivery_date"),
    }),
    "shipment_lines.csv": FileLoader(ShipmentLine, lambda r: {
        "external_id": r["shipment_line_id"], "shipment_external_id": r["shipment_id"],
        "order_line_external_id": _opt_str(r, "order_line_id"),
        "shipped_quantity": _dec(r, "shipped_quantity"),
    }),
    "invoices.csv": FileLoader(Invoice, lambda r: {
        "external_id": r["invoice_id"], "customer_external_id": r["customer_id"],
        "order_external_id": _opt_str(r, "order_id"), "invoice_date": _date(r, "invoice_date"),
        "due_date": _date(r, "due_date"), "currency": r["currency"],
        "invoice_amount": _dec(r, "invoice_amount"), "status": r["status"],
    }),
    "invoice_lines.csv": FileLoader(InvoiceLine, lambda r: {
        "external_id": r["invoice_line_id"], "invoice_external_id": r["invoice_id"],
        "order_line_external_id": _opt_str(r, "order_line_id"),
        "shipment_line_external_id": _opt_str(r, "shipment_line_id"),
        "billed_quantity": _opt_dec(r, "billed_quantity"), "line_amount": _dec(r, "line_amount"),
    }),
    "receipts.csv": FileLoader(Receipt, lambda r: {
        "external_id": r["receipt_id"], "customer_external_id": r["customer_id"],
        "receipt_date": _date(r, "receipt_date"), "currency": r["currency"],
        "receipt_amount": _dec(r, "receipt_amount"), "status": r["status"],
        "remittance_reference": _opt_str(r, "remittance_reference"),
    }),
    "receipt_applications.csv": FileLoader(ReceiptApplication, lambda r: {
        "external_id": r["application_id"], "receipt_external_id": r["receipt_id"],
        "invoice_external_id": r["invoice_id"], "applied_amount": _dec(r, "applied_amount"),
        "application_date": _date(r, "application_date"), "status": r["status"],
    }),
    "credit_memos.csv": FileLoader(CreditMemo, lambda r: {
        "external_id": r["credit_memo_id"], "customer_external_id": r["customer_id"],
        "invoice_external_id": _opt_str(r, "invoice_id"), "currency": r["currency"],
        "credit_amount": _dec(r, "credit_amount"), "status": r["status"],
    }),
    "credit_applications.csv": FileLoader(CreditApplication, lambda r: {
        "external_id": r["credit_application_id"], "credit_memo_external_id": r["credit_memo_id"],
        "invoice_external_id": r["invoice_id"], "applied_amount": _dec(r, "applied_amount"),
        "application_date": _date(r, "application_date"), "status": r["status"],
    }),
    "disputes.csv": FileLoader(Dispute, lambda r: {
        "external_id": r["dispute_id"], "invoice_external_id": r["invoice_id"],
        "disputed_amount": _dec(r, "disputed_amount"), "reason": r["reason"], "status": r["status"],
        "opened_date": _date(r, "opened_date"), "closed_date": _opt_date(r, "closed_date"),
    }),
    "order_holds.csv": FileLoader(OrderHold, lambda r: {
        "external_id": r["hold_id"], "order_external_id": r["order_id"],
        "hold_reason": r["hold_reason"], "status": r["status"], "applied_date": _date(r, "applied_date"),
        "released_date": _opt_date(r, "released_date"),
        "linked_invoice_external_id": _opt_str(r, "linked_invoice_id"),
    }),
}

# Dependency order: files with no cross-file FKs first, so later files'
# references are visible (though we don't enforce DB-level FKs across the
# external_id string columns — the validator already proved referential
# integrity before we got here).
LOAD_ORDER = [
    "customers.csv", "orders.csv", "order_lines.csv", "shipments.csv", "shipment_lines.csv",
    "invoices.csv", "invoice_lines.csv", "receipts.csv", "receipt_applications.csv",
    "credit_memos.csv", "credit_applications.csv", "disputes.csv", "order_holds.csv",
]


async def load_bundle_into_dataset(
    session: AsyncSession,
    bundle_dir: Path,
    organization_id: UUID,
    business_unit_id: UUID,
    dataset_version_id: UUID,
    import_job_id: UUID,
) -> dict[str, int]:
    """Insert every row of every file into its scoped entity table.
    Returns a dict of filename -> row count loaded, for the activation summary.
    """
    row_counts: dict[str, int] = {}
    for filename in LOAD_ORDER:
        loader = FILE_LOADERS[filename]
        path = bundle_dir / filename
        count = 0
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for row_number, row in enumerate(csv.DictReader(fh), start=1):
                kwargs = loader.build_kwargs(row)
                instance = loader.model(
                    organization_id=organization_id,
                    business_unit_id=business_unit_id,
                    dataset_version_id=dataset_version_id,
                    import_job_id=import_job_id,
                    source_filename=filename,
                    source_row_number=row_number,
                    **kwargs,
                )
                session.add(instance)
                count += 1
        row_counts[filename] = count
    return row_counts
