"""Dashboard read endpoints — real queries over the active dataset version,
never LLM-computed. Any authenticated role with business-unit access may
view (intent.md: Viewer can "read authorized dashboards").
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from revenueflowai.auth.deps import assert_business_unit_access, require_role
from revenueflowai.db import get_session
from revenueflowai.domain.holds_service import compute_order_holds
from revenueflowai.domain.services import compute_aging_summary
from revenueflowai.domain.shipment_service import DEFAULT_AGE_THRESHOLD_DAYS, compute_unbilled_shipments
from revenueflowai.models.tenancy import AppUser

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


VIEW_ROLES = ("admin", "analyst", "approver", "viewer")


class AgingSummaryResponse(BaseModel):
    dataset_version_id: UUID | None
    snapshot_date: date | None
    as_of_date: date
    # {currency: {bucket: decimal-string}} -- money as strings over the wire, per intent.md
    totals_by_currency_bucket: dict[str, dict[str, str]]


@router.get("/aging-summary", response_model=AgingSummaryResponse)
async def get_aging_summary(
    business_unit_id: UUID,
    as_of: date = Query(default_factory=date.today),
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AgingSummaryResponse:
    assert_business_unit_access(app_user, business_unit_id)

    summary = await compute_aging_summary(session, app_user.organization_id, business_unit_id, as_of)

    return AgingSummaryResponse(
        dataset_version_id=summary.dataset_version_id,
        snapshot_date=summary.snapshot_date,
        as_of_date=summary.as_of_date,
        totals_by_currency_bucket={
            currency: {bucket: str(total) for bucket, total in buckets.items()}
            for currency, buckets in summary.totals_by_currency_bucket.items()
        },
    )


class UnbilledShipmentResponse(BaseModel):
    shipment_external_id: str
    shipment_line_external_id: str
    order_line_external_id: str | None
    shipped_quantity: str
    billed_quantity: str
    unbilled_quantity: str
    estimated_value: str
    sufficient_evidence: bool
    shipment_date: date


@router.get("/unbilled-shipments", response_model=list[UnbilledShipmentResponse])
async def get_unbilled_shipments(
    business_unit_id: UUID,
    as_of: date = Query(default_factory=date.today),
    age_threshold_days: int = Query(default=DEFAULT_AGE_THRESHOLD_DAYS, ge=0),
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[UnbilledShipmentResponse]:
    assert_business_unit_access(app_user, business_unit_id)

    rows = await compute_unbilled_shipments(
        session, app_user.organization_id, business_unit_id, as_of, age_threshold_days
    )
    return [
        UnbilledShipmentResponse(
            shipment_external_id=r.shipment_external_id,
            shipment_line_external_id=r.shipment_line_external_id,
            order_line_external_id=r.order_line_external_id,
            shipped_quantity=str(r.shipped_quantity),
            billed_quantity=str(r.billed_quantity),
            unbilled_quantity=str(r.unbilled_quantity),
            estimated_value=str(r.estimated_value),
            sufficient_evidence=r.sufficient_evidence,
            shipment_date=r.shipment_date,
        )
        for r in rows
    ]


class OrderHoldResponse(BaseModel):
    order_external_id: str
    hold_reason: str
    is_active: bool
    age_days: int | None
    linked_invoice_id: str | None


@router.get("/order-holds", response_model=list[OrderHoldResponse])
async def get_order_holds(
    business_unit_id: UUID,
    as_of: date = Query(default_factory=date.today),
    active_only: bool = Query(default=True),
    app_user: AppUser = Depends(require_role(*VIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[OrderHoldResponse]:
    assert_business_unit_access(app_user, business_unit_id)

    rows = await compute_order_holds(session, app_user.organization_id, business_unit_id, as_of, active_only)
    return [
        OrderHoldResponse(
            order_external_id=r.order_external_id, hold_reason=r.hold_reason,
            is_active=r.is_active, age_days=r.age_days, linked_invoice_id=r.linked_invoice_id,
        )
        for r in rows
    ]
