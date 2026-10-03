"""Customer detail/timeline: a single real, SQL-backed view of everything
on record for one customer in the active dataset version -- orders,
invoices (with computed open balance), receipts, credit memos, disputes,
and order holds, merged into one chronological timeline. Every entry is a
real row; nothing here is summarized or inferred by an LLM.
"""

from collections import defaultdict
from collections.abc import Sequence
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
from revenueflowai.domain.services import get_active_dataset_version
from revenueflowai.models.entities import (
    CreditApplication,
    CreditMemo,
    Customer,
    Dispute,
    Invoice,
    Order,
    OrderHold,
    Receipt,
    ReceiptApplication,
)


@dataclass(frozen=True)
class TimelineEvent:
    event_date: date
    event_type: str  # order | invoice | receipt | credit_memo | dispute | order_hold
    external_id: str
    description: str
    amount: Decimal | None
    currency: str | None
    status: str


@dataclass(frozen=True)
class InvoiceSummary:
    invoice_external_id: str
    invoice_date: date
    due_date: date
    currency: str
    invoice_amount: Decimal
    status: str
    open_balance: Decimal | None
    aging_bucket: str | None


@dataclass(frozen=True)
class CreditMemoSummary:
    credit_memo_external_id: str
    invoice_external_id: str | None
    currency: str
    credit_amount: Decimal
    status: str


@dataclass(frozen=True)
class CustomerDetail:
    dataset_version_id: UUID | None
    customer_external_id: str
    customer_name: str | None
    account_number: str | None
    payment_terms_days: int | None
    invoices: list[InvoiceSummary]
    # credit_memos.csv carries no date column in the CSV contract, so these
    # can't be placed on the dated `timeline` below -- listed separately
    # instead of fabricating a date for them.
    credit_memos: list[CreditMemoSummary]
    timeline: list[TimelineEvent]


async def compute_customer_detail(
    session: AsyncSession,
    organization_id: UUID,
    business_unit_id: UUID,
    customer_external_id: str,
    as_of: date,
) -> CustomerDetail | None:
    dataset_version = await get_active_dataset_version(session, organization_id, business_unit_id)
    if dataset_version is None:
        return None

    customer = (
        await session.execute(
            select(Customer).where(
                Customer.dataset_version_id == dataset_version.id,
                Customer.external_id == customer_external_id,
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        return None

    def _scoped(model):
        return select(model).where(
            model.dataset_version_id == dataset_version.id,
            model.customer_external_id == customer_external_id,
        )

    orders = (await session.execute(_scoped(Order))).scalars().all()
    invoices = (await session.execute(_scoped(Invoice))).scalars().all()
    receipts = (await session.execute(_scoped(Receipt))).scalars().all()
    credit_memos = (await session.execute(_scoped(CreditMemo))).scalars().all()

    invoice_ids = [inv.external_id for inv in invoices]

    receipt_apps: Sequence[ReceiptApplication] = []
    credit_apps: Sequence[CreditApplication] = []
    disputes: Sequence[Dispute] = []
    if invoice_ids:
        receipt_apps = (
            (await session.execute(
                select(ReceiptApplication).where(
                    ReceiptApplication.dataset_version_id == dataset_version.id,
                    ReceiptApplication.invoice_external_id.in_(invoice_ids),
                )
            ))
            .scalars()
            .all()
        )
        credit_apps = (
            (await session.execute(
                select(CreditApplication).where(
                    CreditApplication.dataset_version_id == dataset_version.id,
                    CreditApplication.invoice_external_id.in_(invoice_ids),
                )
            ))
            .scalars()
            .all()
        )
        disputes = (
            (await session.execute(
                select(Dispute).where(
                    Dispute.dataset_version_id == dataset_version.id,
                    Dispute.invoice_external_id.in_(invoice_ids),
                )
            ))
            .scalars()
            .all()
        )

    order_ids = [o.external_id for o in orders]
    order_holds: Sequence[OrderHold] = []
    if order_ids:
        order_holds = (
            (await session.execute(
                select(OrderHold).where(
                    OrderHold.dataset_version_id == dataset_version.id,
                    OrderHold.order_external_id.in_(order_ids),
                )
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

    invoice_summaries: list[InvoiceSummary] = []
    for inv in invoices:
        balance = compute_invoice_open_balance(
            inv.invoice_amount, inv.status,
            receipts_by_invoice.get(inv.external_id, []),
            credits_by_invoice.get(inv.external_id, []),
        )
        bucket = None
        if balance is not None:
            bucket = compute_aging_bucket(compute_days_overdue(as_of, inv.due_date))
        invoice_summaries.append(
            InvoiceSummary(
                invoice_external_id=inv.external_id, invoice_date=inv.invoice_date, due_date=inv.due_date,
                currency=inv.currency, invoice_amount=inv.invoice_amount, status=inv.status,
                open_balance=balance, aging_bucket=bucket,
            )
        )
    invoice_summaries.sort(key=lambda i: i.invoice_date)

    timeline: list[TimelineEvent] = []
    for o in orders:
        timeline.append(TimelineEvent(
            event_date=o.order_date, event_type="order", external_id=o.external_id,
            description=f"Order placed ({o.status})", amount=None, currency=o.currency, status=o.status,
        ))
    for inv in invoices:
        timeline.append(TimelineEvent(
            event_date=inv.invoice_date, event_type="invoice", external_id=inv.external_id,
            description=f"Invoice issued, due {inv.due_date.isoformat()}",
            amount=inv.invoice_amount, currency=inv.currency, status=inv.status,
        ))
    for r in receipts:
        timeline.append(TimelineEvent(
            event_date=r.receipt_date, event_type="receipt", external_id=r.external_id,
            description="Receipt received", amount=r.receipt_amount, currency=r.currency, status=r.status,
        ))
    for d in disputes:
        timeline.append(TimelineEvent(
            event_date=d.opened_date, event_type="dispute", external_id=d.invoice_external_id,
            description=f"Dispute opened: {d.reason}", amount=d.disputed_amount, currency=None,
            status=d.status,
        ))
        if d.closed_date is not None:
            timeline.append(TimelineEvent(
                event_date=d.closed_date, event_type="dispute", external_id=d.invoice_external_id,
                description=f"Dispute closed: {d.reason}", amount=d.disputed_amount, currency=None,
                status=d.status,
            ))
    for h in order_holds:
        timeline.append(TimelineEvent(
            event_date=h.applied_date, event_type="order_hold", external_id=h.order_external_id,
            description=f"Hold applied: {h.hold_reason}", amount=None, currency=None, status=h.status,
        ))
        if h.released_date is not None:
            timeline.append(TimelineEvent(
                event_date=h.released_date, event_type="order_hold", external_id=h.order_external_id,
                description=f"Hold released: {h.hold_reason}", amount=None, currency=None, status=h.status,
            ))

    timeline.sort(key=lambda e: e.event_date)

    credit_memo_summaries = [
        CreditMemoSummary(
            credit_memo_external_id=cm.external_id, invoice_external_id=cm.invoice_external_id,
            currency=cm.currency, credit_amount=cm.credit_amount, status=cm.status,
        )
        for cm in credit_memos
    ]

    return CustomerDetail(
        dataset_version_id=dataset_version.id,
        customer_external_id=customer.external_id,
        customer_name=customer.customer_name,
        account_number=customer.account_number,
        payment_terms_days=customer.payment_terms_days,
        invoices=invoice_summaries,
        credit_memos=credit_memo_summaries,
        timeline=timeline,
    )
