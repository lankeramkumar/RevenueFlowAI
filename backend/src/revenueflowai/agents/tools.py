"""Typed, read-only domain tools shared by the specialists.

agent_architecture.md: tools accept validated IDs/filters, not arbitrary
SQL, and independently enforce the trusted scope they're called with.
Every tool here takes (session, organization_id, business_unit_id, ...)
explicitly — there is no way to call one without a resolved scope, and
every tool queries only within the active dataset version for that scope.
Results are plain JSON-serializable dicts (decimal amounts as strings)
so they can be handed to a model tool-call result unchanged.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.domain.balances import (
    Application,
    annotate_dispute,
    compute_aging_bucket,
    compute_days_overdue,
    compute_invoice_open_balance,
)
from revenueflowai.domain.holds_service import compute_order_holds
from revenueflowai.domain.matching_service import compute_receipt_matches, compute_unapplied_amount
from revenueflowai.domain.services import compute_aging_summary, get_active_dataset_version
from revenueflowai.domain.shipment_service import compute_unbilled_shipments
from revenueflowai.models.entities import (
    CreditApplication,
    Dispute,
    Invoice,
    Order,
    Receipt,
    ReceiptApplication,
    Shipment,
)


@dataclass(frozen=True)
class ToolScope:
    organization_id: UUID
    business_unit_id: UUID
    as_of: date


def _money(value: Decimal) -> str:
    return str(value)


async def get_aging_summary(session: AsyncSession, scope: ToolScope) -> dict[str, Any]:
    summary = await compute_aging_summary(session, scope.organization_id, scope.business_unit_id, scope.as_of)
    return {
        "dataset_version_id": str(summary.dataset_version_id) if summary.dataset_version_id else None,
        "as_of_date": summary.as_of_date.isoformat(),
        "totals_by_currency_bucket": {
            cur: {bucket: _money(total) for bucket, total in buckets.items()}
            for cur, buckets in summary.totals_by_currency_bucket.items()
        },
    }


async def get_invoice_details(
    session: AsyncSession, scope: ToolScope, invoice_external_id: str
) -> dict[str, Any]:
    dataset_version = await get_active_dataset_version(session, scope.organization_id, scope.business_unit_id)
    if dataset_version is None:
        return {"found": False, "reason": "no_active_dataset"}

    invoice = (
        await session.execute(
            select(Invoice).where(
                Invoice.dataset_version_id == dataset_version.id,
                Invoice.external_id == invoice_external_id,
            )
        )
    ).scalar_one_or_none()
    if invoice is None:
        return {"found": False, "reason": "unknown_invoice_id"}

    receipt_apps = (
        (await session.execute(
            select(ReceiptApplication).where(
                ReceiptApplication.dataset_version_id == dataset_version.id,
                ReceiptApplication.invoice_external_id == invoice_external_id,
            )
        ))
        .scalars()
        .all()
    )
    credit_apps = (
        (await session.execute(
            select(CreditApplication).where(
                CreditApplication.dataset_version_id == dataset_version.id,
                CreditApplication.invoice_external_id == invoice_external_id,
            )
        ))
        .scalars()
        .all()
    )
    disputes = (
        (await session.execute(
            select(Dispute).where(
                Dispute.dataset_version_id == dataset_version.id,
                Dispute.invoice_external_id == invoice_external_id,
            )
        ))
        .scalars()
        .all()
    )

    balance = compute_invoice_open_balance(
        invoice.invoice_amount, invoice.status,
        [Application(a.applied_amount, a.status) for a in receipt_apps],
        [Application(a.applied_amount, a.status) for a in credit_apps],
    )
    days_overdue = compute_days_overdue(scope.as_of, invoice.due_date)
    dispute_info = annotate_dispute([(d.disputed_amount, d.status) for d in disputes])

    return {
        "found": True,
        "invoice_id": invoice.external_id,
        "customer_id": invoice.customer_external_id,
        "currency": invoice.currency,
        "invoice_amount": _money(invoice.invoice_amount),
        "status": invoice.status,
        "due_date": invoice.due_date.isoformat(),
        "open_balance": _money(balance) if balance is not None else None,
        "days_overdue": days_overdue,
        "aging_bucket": compute_aging_bucket(days_overdue),
        "open_dispute_amount": _money(dispute_info.open_dispute_amount),
        "has_overlapping_disputes": dispute_info.flagged_overlapping,
        "evidence": [
            {"source_type": "database_record", "record_type": "invoice", "record_id": invoice.external_id}
        ],
    }


async def get_disputes(
    session: AsyncSession, scope: ToolScope, invoice_external_id: str | None = None
) -> dict[str, Any]:
    dataset_version = await get_active_dataset_version(session, scope.organization_id, scope.business_unit_id)
    if dataset_version is None:
        return {"disputes": []}

    stmt = select(Dispute).where(Dispute.dataset_version_id == dataset_version.id)
    if invoice_external_id:
        stmt = stmt.where(Dispute.invoice_external_id == invoice_external_id)
    disputes = (await session.execute(stmt)).scalars().all()

    return {
        "disputes": [
            {
                "dispute_id": d.external_id, "invoice_id": d.invoice_external_id,
                "disputed_amount": _money(d.disputed_amount), "reason": d.reason, "status": d.status,
                "opened_date": d.opened_date.isoformat(),
            }
            for d in disputes
        ]
    }


async def get_order_trace(session: AsyncSession, scope: ToolScope, order_external_id: str) -> dict[str, Any]:
    dataset_version = await get_active_dataset_version(session, scope.organization_id, scope.business_unit_id)
    if dataset_version is None:
        return {"found": False, "reason": "no_active_dataset"}

    order = (
        await session.execute(
            select(Order).where(
                Order.dataset_version_id == dataset_version.id, Order.external_id == order_external_id
            )
        )
    ).scalar_one_or_none()
    if order is None:
        return {"found": False, "reason": "unknown_order_id"}

    shipments = (
        (await session.execute(
            select(Shipment).where(
                Shipment.dataset_version_id == dataset_version.id,
                Shipment.order_external_id == order_external_id,
            )
        ))
        .scalars()
        .all()
    )
    holds = await compute_order_holds(
        session, scope.organization_id, scope.business_unit_id, scope.as_of, active_only=False
    )
    order_holds = [h for h in holds if h.order_external_id == order_external_id]

    return {
        "found": True,
        "order_id": order.external_id,
        "customer_id": order.customer_external_id,
        "status": order.status,
        "currency": order.currency,
        "shipments": [
            {"shipment_id": s.external_id, "status": s.status, "shipment_date": s.shipment_date.isoformat()}
            for s in shipments
        ],
        "holds": [
            {
                "hold_reason": h.hold_reason, "is_active": h.is_active, "age_days": h.age_days,
                "linked_invoice_id": h.linked_invoice_id,
            }
            for h in order_holds
        ],
    }


async def list_unbilled_shipments(
    session: AsyncSession, scope: ToolScope, age_threshold_days: int = 5
) -> dict[str, Any]:
    rows = await compute_unbilled_shipments(
        session, scope.organization_id, scope.business_unit_id, scope.as_of, age_threshold_days
    )
    return {
        "unbilled_shipments": [
            {
                "shipment_id": r.shipment_external_id, "shipment_line_id": r.shipment_line_external_id,
                "shipped_quantity": str(r.shipped_quantity), "billed_quantity": str(r.billed_quantity),
                "unbilled_quantity": str(r.unbilled_quantity), "estimated_value": str(r.estimated_value),
                "sufficient_evidence": r.sufficient_evidence, "shipment_date": r.shipment_date.isoformat(),
            }
            for r in rows
        ]
    }


async def get_order_holds_tool(session: AsyncSession, scope: ToolScope) -> dict[str, Any]:
    rows = await compute_order_holds(session, scope.organization_id, scope.business_unit_id, scope.as_of)
    return {
        "active_holds": [
            {
                "order_id": r.order_external_id, "hold_reason": r.hold_reason, "age_days": r.age_days,
                "linked_invoice_id": r.linked_invoice_id,
            }
            for r in rows
        ]
    }


async def get_receipt_details(
    session: AsyncSession, scope: ToolScope, receipt_external_id: str
) -> dict[str, Any]:
    dataset_version = await get_active_dataset_version(session, scope.organization_id, scope.business_unit_id)
    if dataset_version is None:
        return {"found": False, "reason": "no_active_dataset"}

    receipt = (
        await session.execute(
            select(Receipt).where(
                Receipt.dataset_version_id == dataset_version.id, Receipt.external_id == receipt_external_id
            )
        )
    ).scalar_one_or_none()
    if receipt is None:
        return {"found": False, "reason": "unknown_receipt_id"}

    apps = (
        (await session.execute(
            select(ReceiptApplication).where(
                ReceiptApplication.dataset_version_id == dataset_version.id,
                ReceiptApplication.receipt_external_id == receipt_external_id,
            )
        ))
        .scalars()
        .all()
    )
    unapplied = compute_unapplied_amount(receipt, list(apps))

    return {
        "found": True,
        "receipt_id": receipt.external_id,
        "customer_id": receipt.customer_external_id,
        "currency": receipt.currency,
        "receipt_amount": _money(receipt.receipt_amount),
        "status": receipt.status,
        "unapplied_amount": _money(unapplied) if unapplied is not None else None,
        "remittance_reference": receipt.remittance_reference,
    }


async def find_receipt_matches_tool(
    session: AsyncSession, scope: ToolScope, receipt_external_id: str
) -> dict[str, Any]:
    result = await compute_receipt_matches(
        session, scope.organization_id, scope.business_unit_id, receipt_external_id
    )
    return {
        "receipt_id": result.receipt_external_id,
        "unapplied_amount": _money(result.unapplied_amount) if result.unapplied_amount is not None else None,
        "is_ambiguous": result.is_ambiguous,
        "reason": result.reason,
        "proposals": [
            {
                "invoice_ids": list(p.invoice_ids), "total": _money(p.total), "residual": _money(p.residual),
                "is_exact": p.is_exact, "evidence": p.evidence,
            }
            for p in result.proposals
        ],
    }


async def get_customer_summary(
    session: AsyncSession, scope: ToolScope, customer_external_id: str
) -> dict[str, Any]:
    dataset_version = await get_active_dataset_version(session, scope.organization_id, scope.business_unit_id)
    if dataset_version is None:
        return {"found": False, "reason": "no_active_dataset"}

    invoices = (
        (await session.execute(
            select(Invoice).where(
                Invoice.dataset_version_id == dataset_version.id,
                Invoice.customer_external_id == customer_external_id,
            )
        ))
        .scalars()
        .all()
    )
    receipts = (
        (await session.execute(
            select(Receipt).where(
                Receipt.dataset_version_id == dataset_version.id,
                Receipt.customer_external_id == customer_external_id,
            )
        ))
        .scalars()
        .all()
    )
    disputes = (
        (await session.execute(
            select(Dispute).where(Dispute.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )
    invoice_ids = {inv.external_id for inv in invoices}
    customer_disputes = [d for d in disputes if d.invoice_external_id in invoice_ids]

    outstanding_by_currency: dict[str, Decimal] = {}
    for invoice in invoices:
        receipt_apps = (
            (await session.execute(
                select(ReceiptApplication).where(
                    ReceiptApplication.dataset_version_id == dataset_version.id,
                    ReceiptApplication.invoice_external_id == invoice.external_id,
                )
            ))
            .scalars()
            .all()
        )
        credit_apps = (
            (await session.execute(
                select(CreditApplication).where(
                    CreditApplication.dataset_version_id == dataset_version.id,
                    CreditApplication.invoice_external_id == invoice.external_id,
                )
            ))
            .scalars()
            .all()
        )
        balance = compute_invoice_open_balance(
            invoice.invoice_amount, invoice.status,
            [Application(a.applied_amount, a.status) for a in receipt_apps],
            [Application(a.applied_amount, a.status) for a in credit_apps],
        )
        if balance is not None:
            outstanding_by_currency[invoice.currency] = (
                outstanding_by_currency.get(invoice.currency, Decimal("0")) + balance
            )

    unapplied_by_currency: dict[str, Decimal] = {}
    for receipt in receipts:
        apps = (
            (await session.execute(
                select(ReceiptApplication).where(
                    ReceiptApplication.dataset_version_id == dataset_version.id,
                    ReceiptApplication.receipt_external_id == receipt.external_id,
                )
            ))
            .scalars()
            .all()
        )
        unapplied = compute_unapplied_amount(receipt, list(apps))
        if unapplied is not None:
            unapplied_by_currency[receipt.currency] = (
                unapplied_by_currency.get(receipt.currency, Decimal("0")) + unapplied
            )

    return {
        "found": True,
        "customer_id": customer_external_id,
        "outstanding_balance_by_currency": {k: _money(v) for k, v in outstanding_by_currency.items()},
        "unapplied_cash_by_currency": {k: _money(v) for k, v in unapplied_by_currency.items()},
        "open_dispute_count": sum(1 for d in customer_disputes if d.status == "open"),
        "open_dispute_amount_total": _money(
            sum((d.disputed_amount for d in customer_disputes if d.status == "open"), Decimal("0"))
        ),
    }
