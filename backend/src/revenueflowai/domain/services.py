"""SQL-backed domain services: wrap the pure calculation functions in
domain/*.py with real queries against the active dataset version. Per
intent.md: "All calculations execute in tested domain services/SQL, never
in the language model."
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.domain.balances import (
    Application,
    compute_aging_bucket,
    compute_days_overdue,
    compute_invoice_open_balance,
)
from revenueflowai.models.entities import CreditApplication, Invoice, ReceiptApplication
from revenueflowai.models.ingestion import DatasetVersion


async def get_active_dataset_version(
    session: AsyncSession, organization_id: UUID, business_unit_id: UUID
) -> DatasetVersion | None:
    return (
        await session.execute(
            select(DatasetVersion).where(
                DatasetVersion.organization_id == organization_id,
                DatasetVersion.business_unit_id == business_unit_id,
                DatasetVersion.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


@dataclass(frozen=True)
class AgingSummary:
    dataset_version_id: UUID | None
    snapshot_date: date | None
    as_of_date: date
    # {currency: {bucket: total}}
    totals_by_currency_bucket: dict[str, dict[str, Decimal]]


async def compute_aging_summary(
    session: AsyncSession, organization_id: UUID, business_unit_id: UUID, as_of: date
) -> AgingSummary:
    dataset_version = await get_active_dataset_version(session, organization_id, business_unit_id)
    if dataset_version is None:
        return AgingSummary(None, None, as_of, {})

    invoices = (
        (await session.execute(
            select(Invoice).where(Invoice.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )

    receipt_apps = (
        (await session.execute(
            select(ReceiptApplication).where(ReceiptApplication.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )
    credit_apps = (
        (await session.execute(
            select(CreditApplication).where(CreditApplication.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )

    receipts_by_invoice: dict[str, list[Application]] = defaultdict(list)
    for app in receipt_apps:
        receipts_by_invoice[app.invoice_external_id].append(Application(app.applied_amount, app.status))

    credits_by_invoice: dict[str, list[Application]] = defaultdict(list)
    for credit_app in credit_apps:
        credits_by_invoice[credit_app.invoice_external_id].append(
            Application(credit_app.applied_amount, credit_app.status)
        )

    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))

    for invoice in invoices:
        balance = compute_invoice_open_balance(
            invoice.invoice_amount, invoice.status,
            receipts_by_invoice.get(invoice.external_id, []),
            credits_by_invoice.get(invoice.external_id, []),
        )
        if balance is None:
            continue  # draft/void invoice: no open balance to report
        days_overdue = compute_days_overdue(as_of, invoice.due_date)
        bucket = compute_aging_bucket(days_overdue)
        totals[invoice.currency][bucket] += balance

    return AgingSummary(
        dataset_version_id=dataset_version.id,
        snapshot_date=dataset_version.snapshot_date,
        as_of_date=as_of,
        totals_by_currency_bucket={cur: dict(buckets) for cur, buckets in totals.items()},
    )
