"""SQL-backed wrapper around domain/matching.py's pure receipt-match logic.

intent.md: candidates are limited to open invoices for the same customer
and currency as the receipt — enforced here by the query, not by the
scoring function.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.domain.balances import (
    Application,
    compute_invoice_open_balance,
    compute_unapplied_receipt_amount,
)
from revenueflowai.domain.matching import InvoiceCandidate, MatchProposal, find_receipt_matches
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.models.entities import CreditApplication, Invoice, Receipt, ReceiptApplication


@dataclass(frozen=True)
class ReceiptMatchResult:
    receipt_external_id: str
    unapplied_amount: Decimal | None
    proposals: list[MatchProposal]
    is_ambiguous: bool
    reason: str | None = None  # set when no result could be computed (e.g. receipt not found)


async def compute_receipt_matches(
    session: AsyncSession, organization_id: UUID, business_unit_id: UUID, receipt_external_id: str
) -> ReceiptMatchResult:
    dataset_version = await get_active_dataset_version(session, organization_id, business_unit_id)
    if dataset_version is None:
        return ReceiptMatchResult(receipt_external_id, None, [], False, reason="no_active_dataset")

    receipt = (
        await session.execute(
            select(Receipt).where(
                Receipt.dataset_version_id == dataset_version.id,
                Receipt.external_id == receipt_external_id,
            )
        )
    ).scalar_one_or_none()
    if receipt is None:
        return ReceiptMatchResult(receipt_external_id, None, [], False, reason="receipt_not_found")

    receipt_apps = (
        (await session.execute(
            select(ReceiptApplication).where(
                ReceiptApplication.dataset_version_id == dataset_version.id,
                ReceiptApplication.receipt_external_id == receipt_external_id,
            )
        ))
        .scalars()
        .all()
    )
    unapplied = compute_unapplied_amount(receipt, list(receipt_apps))
    if unapplied is None or unapplied <= 0:
        return ReceiptMatchResult(receipt_external_id, unapplied, [], False)

    # Candidates: open invoices for the same customer + currency.
    invoices = (
        (await session.execute(
            select(Invoice).where(
                Invoice.dataset_version_id == dataset_version.id,
                Invoice.customer_external_id == receipt.customer_external_id,
                Invoice.currency == receipt.currency,
            )
        ))
        .scalars()
        .all()
    )
    all_receipt_apps = (
        (await session.execute(
            select(ReceiptApplication).where(ReceiptApplication.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )
    all_credit_apps = (
        (await session.execute(
            select(CreditApplication).where(CreditApplication.dataset_version_id == dataset_version.id)
        ))
        .scalars()
        .all()
    )
    receipts_by_invoice: dict[str, list[Application]] = defaultdict(list)
    for receipt_app in all_receipt_apps:
        receipts_by_invoice[receipt_app.invoice_external_id].append(
            Application(receipt_app.applied_amount, receipt_app.status)
        )
    credits_by_invoice: dict[str, list[Application]] = defaultdict(list)
    for credit_app in all_credit_apps:
        credits_by_invoice[credit_app.invoice_external_id].append(
            Application(credit_app.applied_amount, credit_app.status)
        )

    candidates: list[InvoiceCandidate] = []
    for invoice in invoices:
        balance = compute_invoice_open_balance(
            invoice.invoice_amount, invoice.status,
            receipts_by_invoice.get(invoice.external_id, []),
            credits_by_invoice.get(invoice.external_id, []),
        )
        if balance is not None and balance > 0:
            candidates.append(InvoiceCandidate(invoice.external_id, balance))

    remittance_referenced = (
        frozenset({receipt.remittance_reference}) if receipt.remittance_reference else frozenset()
    )
    result = find_receipt_matches(unapplied, candidates, remittance_referenced)

    return ReceiptMatchResult(receipt_external_id, unapplied, result.proposals, result.is_ambiguous)


def compute_unapplied_amount(receipt: Receipt, applications: list[ReceiptApplication]) -> Decimal | None:
    return compute_unapplied_receipt_amount(
        receipt.receipt_amount, receipt.status,
        [Application(a.applied_amount, a.status) for a in applications],
    )
