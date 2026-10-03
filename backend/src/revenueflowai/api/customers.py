"""Customer detail/timeline endpoint -- a single real, SQL-backed view
(domain/customer_service.py) of one customer's orders, invoices, receipts,
credit memos, disputes, and order holds. Any authenticated role with
business-unit access may view, consistent with the other dashboard reads.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.db import get_session
from revenueflowai.domain.customer_service import compute_customer_detail
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

VIEW_ROLES = ("admin", "analyst", "approver", "viewer")


class InvoiceSummaryResponse(BaseModel):
    invoice_external_id: str
    invoice_date: date
    due_date: date
    currency: str
    invoice_amount: str
    status: str
    open_balance: str | None
    aging_bucket: str | None


class CreditMemoSummaryResponse(BaseModel):
    credit_memo_external_id: str
    invoice_external_id: str | None
    currency: str
    credit_amount: str
    status: str


class TimelineEventResponse(BaseModel):
    event_date: date
    event_type: str
    external_id: str
    description: str
    amount: str | None
    currency: str | None
    status: str


class CustomerDetailResponse(BaseModel):
    dataset_version_id: UUID | None
    customer_external_id: str
    customer_name: str | None
    account_number: str | None
    payment_terms_days: int | None
    invoices: list[InvoiceSummaryResponse]
    credit_memos: list[CreditMemoSummaryResponse]
    timeline: list[TimelineEventResponse]


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


@router.get("/{customer_external_id}", response_model=CustomerDetailResponse)
async def get_customer_detail(
    customer_external_id: str,
    business_unit_id: UUID,
    as_of: date = Query(default_factory=date.today),
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> CustomerDetailResponse:
    assert_business_unit_access(app_user, business_unit_id)

    detail = await compute_customer_detail(
        session, app_user.organization_id, business_unit_id, customer_external_id, as_of
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    return CustomerDetailResponse(
        dataset_version_id=detail.dataset_version_id,
        customer_external_id=detail.customer_external_id,
        customer_name=detail.customer_name,
        account_number=detail.account_number,
        payment_terms_days=detail.payment_terms_days,
        invoices=[
            InvoiceSummaryResponse(
                invoice_external_id=inv.invoice_external_id, invoice_date=inv.invoice_date,
                due_date=inv.due_date, currency=inv.currency, invoice_amount=str(inv.invoice_amount),
                status=inv.status, open_balance=_money(inv.open_balance), aging_bucket=inv.aging_bucket,
            )
            for inv in detail.invoices
        ],
        credit_memos=[
            CreditMemoSummaryResponse(
                credit_memo_external_id=cm.credit_memo_external_id,
                invoice_external_id=cm.invoice_external_id, currency=cm.currency,
                credit_amount=str(cm.credit_amount), status=cm.status,
            )
            for cm in detail.credit_memos
        ],
        timeline=[
            TimelineEventResponse(
                event_date=ev.event_date, event_type=ev.event_type, external_id=ev.external_id,
                description=ev.description, amount=_money(ev.amount), currency=ev.currency,
                status=ev.status,
            )
            for ev in detail.timeline
        ],
    )
