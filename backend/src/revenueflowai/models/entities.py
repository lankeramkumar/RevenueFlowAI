"""Order-to-Cash domain entities, one model per CSV file in intent.md's contract.

All money/quantity columns are `Numeric(18, 4)` and mapped to `decimal.Decimal`
in Python — never float — per intent.md's "exact Decimal/NUMERIC" rule.
Status values are free-text strings validated against the schema manifest at
ingestion time (see ingestion/manifest.py in Milestone 2), not DB enums, so
the manifest stays the single source of truth for supported vocabulary.
"""

from datetime import date

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from revenueflowai.db import Base
from revenueflowai.models.base import ScopedRecordMixin

Money = Numeric(18, 4)
Quantity = Numeric(18, 4)


class Customer(ScopedRecordMixin, Base):
    __tablename__ = "customers"

    account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(256), nullable=False)
    payment_terms_days: Mapped[int | None] = mapped_column(nullable=True)


class Order(ScopedRecordMixin, Base):
    __tablename__ = "orders"

    customer_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    promised_ship_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class OrderLine(ScopedRecordMixin, Base):
    __tablename__ = "order_lines"

    order_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    item_code: Mapped[str] = mapped_column(String(128), nullable=False)
    ordered_quantity: Mapped[object] = mapped_column(Quantity, nullable=False)
    cancelled_quantity: Mapped[object] = mapped_column(Quantity, nullable=False, default=0)
    unit_price: Mapped[object] = mapped_column(Money, nullable=False)
    line_amount: Mapped[object] = mapped_column(Money, nullable=False)


class Shipment(ScopedRecordMixin, Base):
    __tablename__ = "shipments"

    order_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    shipment_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class ShipmentLine(ScopedRecordMixin, Base):
    __tablename__ = "shipment_lines"

    shipment_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_line_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    shipped_quantity: Mapped[object] = mapped_column(Quantity, nullable=False)


class Invoice(ScopedRecordMixin, Base):
    __tablename__ = "invoices"

    customer_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    invoice_amount: Mapped[object] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class InvoiceLine(ScopedRecordMixin, Base):
    __tablename__ = "invoice_lines"

    invoice_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    order_line_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    shipment_line_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    billed_quantity: Mapped[object | None] = mapped_column(Quantity, nullable=True)
    line_amount: Mapped[object] = mapped_column(Money, nullable=False)


class Receipt(ScopedRecordMixin, Base):
    __tablename__ = "receipts"

    customer_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    receipt_amount: Mapped[object] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    remittance_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)


class ReceiptApplication(ScopedRecordMixin, Base):
    __tablename__ = "receipt_applications"

    receipt_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    applied_amount: Mapped[object] = mapped_column(Money, nullable=False)
    application_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class CreditMemo(ScopedRecordMixin, Base):
    __tablename__ = "credit_memos"

    customer_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    credit_amount: Mapped[object] = mapped_column(Money, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class CreditApplication(ScopedRecordMixin, Base):
    __tablename__ = "credit_applications"

    credit_memo_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invoice_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    applied_amount: Mapped[object] = mapped_column(Money, nullable=False)
    application_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class Dispute(ScopedRecordMixin, Base):
    __tablename__ = "disputes"

    invoice_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    disputed_amount: Mapped[object] = mapped_column(Money, nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    opened_date: Mapped[date] = mapped_column(Date, nullable=False)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class OrderHold(ScopedRecordMixin, Base):
    __tablename__ = "order_holds"

    order_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    hold_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    applied_date: Mapped[date] = mapped_column(Date, nullable=False)
    released_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    linked_invoice_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
